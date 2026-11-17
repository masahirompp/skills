#!/usr/bin/env python3
"""PR のレビューループの1試行を、始める前と終えたあとに確かめて、PR の状態コメントに記録する。

    review_loop.py begin <worktree の絶対パス> [--new-run]
    review_loop.py end   <worktree の絶対パス> [--failed 理由]

レビュー役は起動しない。観点スキルは、呼び出し元(親)が begin と end の間に呼ぶ。

begin: 前提(作業ディレクトリが worktree のトップ、作業ツリーがクリーン、ローカルの HEAD と PR の head が一致、
       自分のオープンな PR)と上限を確かめ、ロックを取り、作業ディレクトリを作る。試行の記録(PR 番号、SHA、ブランチ、
       ロックの nonce、作業ディレクトリ)を git の管理ディレクトリに置き、標準出力に `pr=`、`sha=`、`attempt=`、
       `workdir=` の行を出す。
end:   試行の記録を読み、begin のあとに作業ツリー、HEAD、ブランチ、PR の head が変わっていないかを確かめる。
       作業ディレクトリの `review-<役の名前>.md` を、役の名前の区切りでつないで `reviews.md` を作り、試行の結果を
       記録してロックを解く。レビュー役が失敗したときは、--failed に理由を付けて呼ぶ。

終了コード:
  0  begin: 試行を始めた。end: 試行を completed として記録した
  1  試行の失敗を記録した(begin: 作業ディレクトリを作れない。end: 混入、PR の head の変化、--failed)
  2  何も記録していない(前提を満たさない、ロックを取れない、上限に達した、gh や git の失敗、閉じる試行が無い)。
     ただし begin は、残っていた古いロックを interrupted として片付けた記録を残すことがある。
     end がこれで終わったときにロックが残っているかは、stderr の理由による(SKILL.md の手順3)
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import uuid

# --- 設定 ------------------------------------------------------------------
SAFETY_MAX_ITER = 10          # シリーズあたりの反復の上限
MAX_CONSECUTIVE_FAILURES = 3  # 連続失敗の上限
STALE_LOCK_AFTER = 55 * 60    # begin から end までの長さの上限。ロックに stale_after として記録し、読む側はその値で古さを決める
# stale_after を記録していない旧版のロックを、古いとみなすまでの長さ(旧版がロックを持ちうる最長)
LEGACY_STALE_LOCK_AFTER = 75 * 60
STALE_LOCK_MAX = 120 * 60     # 記録された stale_after を信じる上限(手で大きな値に書き換えられても、永久には止まらない)
LOCK_SETTLE_SECONDS = 3       # nonce を書いてから読み直すまで
COMMAND_TIMEOUT = 60          # git や gh の1回の呼び出し

MARKER = "review-loop-state"
FAILED_REASON_CHARS = 100     # 状態コメントに載せる、--failed の理由の文字数
TABLE_REASON_CHARS = 130      # 状態コメントの表に出す、失敗の種類と理由の文字数(reviewer_failed: と理由が収まる長さ)
ATTEMPT_FILE = "review-loop-attempt.json"  # 試行の記録。git の管理ディレクトリ(worktree ごと)に置く
ROLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")  # レビュー役の名前(review-<名前>.md の <名前>)
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}$")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
TOKEN_KEYS = {"input", "cache_read", "output"}  # 旧版が試行ごとに記録していたトークン数の形(読むだけ)


class Precondition(Exception):
    """前提を満たさない、または git や gh が失敗した。何も記録せず、終了コード2で終わる。"""


class AttemptFailed(Exception):
    """試行の失敗。kind を状態コメントに載せ、detail は stderr と作業ディレクトリに残す。"""

    def __init__(self, kind, detail=""):
        super().__init__(kind)
        self.kind, self.detail = kind, detail


class Interrupted(Exception):
    """シグナルで止められた。"""


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(t):
    return t.isoformat().replace("+00:00", "Z")


def parse_iso(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def run(args, cwd, input=None, check=True):
    """git や gh を実行する。止まっても抜けられるよう制限時間を付ける。"""
    try:
        r = subprocess.run(args, cwd=cwd, input=input, capture_output=True, text=True,
                           stdin=None if input is not None else subprocess.DEVNULL, timeout=COMMAND_TIMEOUT)
    except OSError as e:
        raise Precondition(f"{args[0]} を起動できない: {e}")
    except subprocess.TimeoutExpired:
        raise Precondition(f"`{' '.join(args[:4])} …` が {COMMAND_TIMEOUT} 秒で終わらなかった")
    if check and r.returncode != 0:
        raise Precondition(f"`{' '.join(args[:4])} …` が失敗した(終了コード {r.returncode}): {r.stderr.strip()}")
    return r


def ignore_signals():
    """後片付けの途中で2回目のシグナルに割り込まれないようにする。以後は終了するだけなので戻さない。"""
    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(s, signal.SIG_IGN)


# --- 前提 --------------------------------------------------------------------
def check_tools():
    if sys.version_info < (3, 9):
        raise Precondition("Python 3.9 以降が必要")
    missing = [c for c in ("git", "gh") if shutil.which(c) is None]
    if missing:
        raise Precondition(f"コマンドが見つからない: {', '.join(missing)}")


def normalize_worktree(path):
    if not os.path.isabs(path):
        raise Precondition(f"worktree は絶対パスで指定する: {path}")
    real = os.path.realpath(path)
    if not os.path.isdir(real):
        raise Precondition(f"ディレクトリがない: {path}")
    top = run(["git", "rev-parse", "--show-toplevel"], cwd=real).stdout.strip()
    if os.path.realpath(top) != real:
        raise Precondition(f"worktree のトップではない: {real}(トップは {top})")
    return real


def git_status(wt):
    return run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=wt).stdout


def pr_view(wt):
    r = run(["gh", "pr", "view", "--json", "number,headRefOid,state,author,url"], cwd=wt, check=False)
    if r.returncode != 0:
        raise Precondition(f"このブランチの PR を取得できない: {r.stderr.strip()}")
    return json.loads(r.stdout)


def local_refs(wt):
    """(HEAD の SHA, ブランチ名) を返す。detached HEAD ならブランチ名は空。"""
    return (run(["git", "rev-parse", "HEAD"], cwd=wt).stdout.strip(),
            run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=wt, check=False).stdout.strip())


def repo_slug(pr):
    m = re.match(r"https?://[^/]+/([^/]+)/([^/]+)/pull/", pr.get("url") or "")
    return f"{m.group(1)}_{m.group(2)}" if m else "unknown"


# --- 状態コメント ------------------------------------------------------------
def valid_tokens(t):
    return t is None or (isinstance(t, dict) and set(t) == TOKEN_KEYS and all(isinstance(v, int) for v in t.values()))


def valid_sha(v):
    return v is None or (isinstance(v, str) and bool(SHA_RE.match(v)))


def valid_state(s):
    """状態コメントの JSON が、このスクリプト(旧版を含む)の書いた形をしているか。render、begin、end が読むものを全て見る。
    旧版が試行に記録していた観点、指示を渡した観点、モデル、トークン数は、あっても読まない(形だけ確かめる)。"""
    try:
        lock, prev = s["lock"], s.get("previous_run")
        if lock["running"]:
            parse_iso(lock["started_at"])
        return (bool(RUN_ID_RE.match(s["run_id"]))
                and isinstance(s["iter"], int) and isinstance(s["consecutive_failures"], int)
                and isinstance(lock["running"], bool) and valid_sha(lock.get("sha"))
                and (not lock["running"] or isinstance(lock.get("sha"), str))  # 実行中のロックは、end が sha を読む
                and isinstance(lock.get("branch") or "", str)
                and all(isinstance(a["result"], str) and isinstance(a["at"], str)
                        and valid_sha(a.get("sha")) and isinstance(a.get("reason") or "", str)
                        and valid_tokens(a.get("tokens")) and isinstance(a.get("model") or "", str)
                        and isinstance(a.get("iter") or 0, int)
                        and all(isinstance(a.get(k) or [], list) and all(isinstance(n, str) for n in a.get(k) or [])
                                for k in ("perspectives", "instructed", "roles"))
                        for a in s["attempts"])
                and (prev is None or (bool(RUN_ID_RE.match(prev["run_id"])) and isinstance(prev["iterations"], int)
                                      and valid_tokens(prev.get("tokens")))))
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


class StateComment:
    def __init__(self, wt, pr_number, me):
        self.wt = wt
        self.pr = pr_number
        self.me = me
        self.id = None
        self.created = None  # このプロセスが作ったコメントの id
        self.unreadable = False  # 状態コメントはあるが、読めない形だった

    def read(self):
        """状態を返す。コメントがない、または読めない形なら None(読めないときは unreadable を立てる)。"""
        r = run(["gh", "api", "--paginate", f"repos/{{owner}}/{{repo}}/issues/{self.pr}/comments",
                 "--jq", ".[] | {id, login: .user.login, created_at, body}"], cwd=self.wt)
        found = []
        for line in r.stdout.splitlines():
            if line.strip():
                c = json.loads(line)
                if c["login"] == self.me and (c["body"] or "").startswith(f"<!-- {MARKER} "):
                    found.append(c)
        self.unreadable = False
        if not found:
            self.id = None
            return None
        found.sort(key=lambda c: (c["created_at"], c["id"]))
        if len(found) > 1:
            log(f"warn: 状態コメントが {len(found)} 件ある。最も古いもの({found[0]['id']})を使う")
        self.id = found[0]["id"]
        m = re.search(rf"<!-- {MARKER} (.*?) -->", found[0]["body"], re.S)
        try:
            state = json.loads(m.group(1))
        except (AttributeError, ValueError):
            state = None
        if not valid_state(state):
            self.unreadable = True
            return None
        return state

    def write(self, state):
        payload = json.dumps({"body": render(state)}, ensure_ascii=False)
        if self.id is None:
            r = run(["gh", "api", "-X", "POST", f"repos/{{owner}}/{{repo}}/issues/{self.pr}/comments",
                     "--input", "-", "--jq", ".id"], cwd=self.wt, input=payload)
            self.id = self.created = int(r.stdout.strip())
        else:
            run(["gh", "api", "-X", "PATCH", f"repos/{{owner}}/{{repo}}/issues/comments/{self.id}",
                 "--input", "-", "--jq", ".id"], cwd=self.wt, input=payload)

    def discard_created(self):
        """自分が作ったコメントが採用されなかったとき(同時に作った場合)に消す。"""
        if self.created is not None and self.created != self.id:
            run(["gh", "api", "-X", "DELETE", f"repos/{{owner}}/{{repo}}/issues/comments/{self.created}"],
                cwd=self.wt, check=False)


UNLOCKED = {"running": False, "started_at": None, "sha": None, "nonce": None}


def new_state(previous=None):
    run_id = now().strftime("%Y%m%dT%H%M%S")
    if previous and previous["run_id"] == run_id:  # 同じ秒に始め直すと作業ディレクトリが重なる
        time.sleep(1)
        run_id = now().strftime("%Y%m%dT%H%M%S")
    return {
        "run_id": run_id,
        "iter": 0,
        "safety_max": SAFETY_MAX_ITER,
        "consecutive_failures": 0,
        "attempts": [],
        "previous_run": previous,
        "lock": dict(UNLOCKED),
    }


def cell(text):
    """表のセルに入れる値を、表を壊さず(| と改行)、HTML として解釈されず(<)、メンションにならない(@)形にする。"""
    return text.replace("|", "\\|").replace("\n", " ").replace("<", "&lt;").replace("@", "@\u200b")


def render(state):
    raw = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    # HTML コメントを閉じないよう、また @ がメンションにならないようにエスケープする(JSON としては等価)
    raw = raw.replace(">", "\\u003e").replace("@", "\\u0040")
    lock = state["lock"]
    status = (f"実行中(開始 {lock['started_at']}、SHA {(lock['sha'] or '')[:7]})" if lock["running"]
              else "実行中ではない")
    lines = [f"<!-- {MARKER} {raw} -->",
             f"**review-loop** run {state['run_id']} — 反復 {state['iter']} — {status}", ""]
    prev = state.get("previous_run")
    if prev:
        lines += [f"直前のシリーズ: run {prev['run_id']}(反復 {prev['iterations']})", ""]
    if state["attempts"]:
        lines += ["| SHA | 時刻 | 結果 |", "|---|---|---|"]
        for a in state["attempts"]:
            result = a["result"] + (f"(反復 {a['iter']})" if a.get("iter") else "")
            if a.get("reason"):
                result += f": {a['reason'][:TABLE_REASON_CHARS]}"
            lines.append(f"| {cell((a['sha'] or '')[:7])} | {cell(a['at'])} | {cell(result)} |")
        lines.append("")
    lines.append("<sub>review-loop のスクリプトが更新するコメント。手で編集しても上書きされる。</sub>")
    return "\n".join(lines)


def lock_stale_after(lock):
    """ロックを古いとみなすまでの秒数。ロックに記録した stale_after を使う。

    状態コメントは手で編集されうるので、値は信じすぎない。数でなければ、記録の無い旧版のロックと同じ長さで
    見る。数でも、STALE_LOCK_AFTER より短くはしない(実行中のロックを奪わない)し、STALE_LOCK_MAX より長くも
    しない(永久に止まらない)。"""
    v = lock.get("stale_after", LEGACY_STALE_LOCK_AFTER)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:  # v != v は NaN
        v = LEGACY_STALE_LOCK_AFTER
    return min(max(v, STALE_LOCK_AFTER), STALE_LOCK_MAX)


def acquire_lock(sc, head, branch, new_run):
    """ロックを取り、状態と nonce を返す。

    誤って二重に始めたことを検出するためのもので、厳密な排他制御ではない。ループを回す親は1つだけなので、
    gh の書き込みが遅れて両方が通る程度の取りこぼしは許容する。"""
    state = sc.read()
    if sc.unreadable:
        if not new_run:
            raise Precondition(f"状態コメント {sc.id} を読めない(手で編集された可能性がある)。反復回数と連続失敗の"
                               "上限を黙って外さないよう、ここで止める。利用者の指示があれば --new-run で始め直す")
        log(f"warn: 状態コメント {sc.id} を読めないので、新しいシリーズとして上書きする")
    if state is not None and state["lock"]["running"]:
        age = (now() - parse_iso(state["lock"]["started_at"])).total_seconds()
        # 古さは、ロックを書いた版が持ちうる長さで決める。版ごとに長さが違うので、自分の値で決めると、
        # 長く持つ版の実行中のロックを奪ってしまう
        if age < lock_stale_after(state["lock"]):
            raise Precondition(f"別の試行が実行中(開始 {state['lock']['started_at']})。ほかのセッションが同じ PR で"
                               "試行中の可能性がある。終わるのを待つか、利用者に報告する")
        log(f"warn: 古いロックが残っていた(開始 {state['lock']['started_at']})。前回の試行を interrupted として記録する")
        state["attempts"].append({"sha": state["lock"].get("sha"), "at": state["lock"]["started_at"],
                                  "result": "interrupted", "reason": "stale_lock"})
        state["consecutive_failures"] += 1
    if state is None:
        state = new_state()
    elif new_run:
        state = new_state({"run_id": state["run_id"], "iterations": state["iter"]})
    nonce = uuid.uuid4().hex
    state["lock"] = {"running": True, "started_at": iso(now()), "sha": head, "branch": branch, "nonce": nonce,
                     "stale_after": STALE_LOCK_AFTER}
    try:
        sc.write(state)
        time.sleep(LOCK_SETTLE_SECONDS)
        again = sc.read()
    except BaseException:
        ignore_signals()
        release_lock(sc, state, nonce)
        raise
    if not again or again["lock"].get("nonce") != nonce:
        sc.discard_created()
        raise Precondition("ロックの取得で競合した(二重に始めた可能性がある)。撤退する")
    return state, nonce


def release_lock(sc, state, nonce):
    """ロックを解除し、状態を書き込めたかを返す。書き込めなくても例外にはせず、結果は返す。"""
    try:
        current = sc.read()
        if current is None or current["lock"].get("nonce") != nonce:
            log("warn: ロックが自分のものではなくなっていた(古いロックとして奪われた可能性がある)。状態コメントは更新しない")
            return False
        state["lock"] = dict(UNLOCKED)
        sc.write(state)
        return True
    except Exception as e:
        log(f"warn: 状態コメントを更新できなかった(次回、古いロックとして扱われる): {e}")
        return False


# --- 作業ディレクトリ --------------------------------------------------------
def workdir_path(repo, pr_number, run_id, attempt_no):
    """<一時ディレクトリ>/review-loop/<owner>_<repo>/<PR番号>/<run_id>/<試行>/"""
    return os.path.join(tempfile.gettempdir(), "review-loop", repo, str(pr_number), run_id, str(attempt_no))


def make_workdir(path):
    """作業ディレクトリを新しく作る。

    共有の一時ディレクトリ(TMPDIR のない Linux の /tmp)で他人に先回りされたり、レビューの出力を
    読まれたりしないよう、起点は自分が所有するディレクトリに限り、権限を 0700 に絞って使う。
    試行のディレクトリが既にあれば、前の出力と混ざるので失敗にする。"""
    top = os.path.join(tempfile.gettempdir(), "review-loop")
    try:
        os.makedirs(top, mode=0o700, exist_ok=True)
        st = os.lstat(top)
        if stat.S_ISLNK(st.st_mode) or st.st_uid != os.getuid():
            raise AttemptFailed("workdir_error", f"{top} が自分の所有するディレクトリではない")
        if st.st_mode & 0o077:  # umask などで広い権限で作られていたら絞る
            os.chmod(top, 0o700)
        os.makedirs(path)
    except FileExistsError:
        raise AttemptFailed("workdir_error", f"作業ディレクトリが既にある: {path}")
    except OSError as e:
        raise AttemptFailed("workdir_error", f"作業ディレクトリを作れない: {e}")


# --- 試行の記録 --------------------------------------------------------------
def attempt_file(wt):
    """試行の記録の置き場。git の管理ディレクトリの中なので、作業ツリーを汚さず、worktree ごとに分かれる。"""
    return os.path.join(run(["git", "rev-parse", "--absolute-git-dir"], cwd=wt).stdout.strip(), ATTEMPT_FILE)


def read_attempt(path):
    """試行の記録を返す。無ければ None。読めない形なら Precondition。"""
    try:
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise Precondition(f"試行の記録 {path} を読めない: {e}")
    ok = (isinstance(rec, dict) and isinstance(rec.get("pr"), int) and valid_sha(rec.get("sha")) and rec.get("sha")
          and all(isinstance(rec.get(k), str) for k in ("branch", "nonce", "workdir", "started_at")))
    if not ok:
        raise Precondition(f"試行の記録 {path} が、begin の書いた形をしていない")
    return rec


# --- 混入の検査 --------------------------------------------------------------
def local_changes(wt, rec):
    """begin のあとに、作業ツリー、HEAD、ブランチが変わっていないかを、git だけで確かめる(gh は、ブランチが
    切り替わっていると別の PR を引くので使わない)。変わっていれば詳細を、なければ None を返す。"""
    problems = []
    status = git_status(wt)
    if status.strip():
        problems.append("作業ツリーがクリーンでない:\n" + status.rstrip())
    head, branch = local_refs(wt)
    if head != rec["sha"]:
        problems.append(f"HEAD が変わった: {rec['sha']} → {head}")
    if branch != rec["branch"]:
        problems.append(f"ブランチが変わった: {rec['branch'] or '(detached)'} → {branch or '(detached)'}")
    return "\n".join(problems) + "\n(変更は元に戻していない)" if problems else None


def pr_head_change(wt, rec):
    """PR の head が begin のときから動いていれば詳細を、なければ None を返す。PR は番号で引く。"""
    r = run(["gh", "pr", "view", str(rec["pr"]), "--json", "headRefOid"], cwd=wt)
    pr_head = json.loads(r.stdout)["headRefOid"]
    if pr_head == rec["sha"]:
        return None
    # 外からの push と、レビュー役がローカルを変えずに直接 push したものは区別できない
    return (f"試行中に PR の head が変わった: {rec['sha']} → {pr_head}。"
            "自分で push したのでなければ、レビュー役が禁じられた push をした可能性がある。"
            "取り込む前に、新しいコミットの作者と内容を確かめる")


# --- レビュー役の出力 --------------------------------------------------------
def collect_reviews(workdir):
    """作業ディレクトリの review-<役の名前>.md を読み、[(役の名前, 本文)] を名前の順で返す。"""
    found = []
    try:
        names = sorted(os.listdir(workdir))
    except OSError as e:
        raise Precondition(f"作業ディレクトリ {workdir} を読めない: {e}")
    for n in names:
        if not (n.startswith("review-") and n.endswith(".md")):
            continue
        role = n[len("review-"):-len(".md")]
        if not ROLE_RE.match(role):
            raise Precondition(f"レビュー役の出力のファイル名を、役の名前として読めない: {n}"
                               "(review-<役の名前>.md。名前は英数字と _ . : - で、80文字まで)")
        try:
            with open(os.path.join(workdir, n), encoding="utf-8") as f:
                text = f.read()
        except (OSError, ValueError) as e:
            raise Precondition(f"{n} を読めない: {e}")
        if not text.strip():
            raise Precondition(f"{n} が空。そのレビュー役が失敗したなら、--failed を付けて閉じる")
        found.append((role, text))
    return sorted(found)  # ファイル名の順ではなく、役の名前の順(code-review、code-review-2 の順になる)


def write_reviews(workdir, reviews):
    """レビュー役の出力を、役の名前の区切りでつないで reviews.md に書く。"""
    joined = "\n\n".join(f"===== 観点: {role} =====\n{text.rstrip()}" for role, text in reviews) + "\n"
    try:
        with open(os.path.join(workdir, "reviews.md"), "w", encoding="utf-8") as f:
            f.write(joined)
    except OSError as e:
        raise Precondition(f"reviews.md を書けない: {e}")


# --- 本体 --------------------------------------------------------------------
def begin(worktree, new_run):
    """試行を始める。標準出力に出す行の辞書を返す。"""
    check_tools()
    wt = normalize_worktree(worktree)
    if os.path.realpath(os.getcwd()) != wt:
        # レビュー役は、呼び出し元(親)の作業ディレクトリで動く。ここが worktree でなければ、別のツリーをレビューする
        raise Precondition(f"作業ディレクトリ({os.getcwd()})が worktree のトップ({wt})ではない。"
                           "レビュー役はあなたの作業ディレクトリで動くので、worktree の中から実行する")
    record = attempt_file(wt)
    if read_attempt(record) is not None:
        raise Precondition("前の試行を end で閉じていない。end を呼んで閉じてから始める"
                           "(レビュー役の結果を受け取れていなければ --failed を付ける)")
    if git_status(wt).strip():
        raise Precondition("作業ツリーがクリーンでない。コミットしてから実行する")
    me = run(["gh", "api", "user", "--jq", ".login"], cwd=wt).stdout.strip()
    pr = pr_view(wt)
    author = (pr.get("author") or {}).get("login")
    head, branch = local_refs(wt)
    if pr.get("state") != "OPEN":
        raise Precondition(f"PR #{pr['number']} はオープンではない({pr.get('state')})")
    if author != me:
        raise Precondition(f"PR #{pr['number']} の作成者({author})が自分({me})ではない")
    if head != pr["headRefOid"]:
        raise Precondition(f"ローカルの HEAD({head[:7]})が PR の head({pr['headRefOid'][:7]})と"
                           "一致しない。push してから実行する")

    sc = StateComment(wt, pr["number"], me)
    state, nonce = acquire_lock(sc, head, branch, new_run)
    try:  # ロックを取ったあとは、試行を始められなければ解除する
        if state["iter"] >= SAFETY_MAX_ITER:
            raise Precondition(f"反復が安全上限({SAFETY_MAX_ITER} 回)に達した")
        if state["consecutive_failures"] >= MAX_CONSECUTIVE_FAILURES:
            raise Precondition(f"連続失敗が {MAX_CONSECUTIVE_FAILURES} 回に達した。原因を取り除いてから、利用者の指示で --new-run する")
        attempt_no = len(state["attempts"]) + 1
        workdir = workdir_path(repo_slug(pr), pr["number"], state["run_id"], attempt_no)
        make_workdir(workdir)
        try:
            with open(record, "w", encoding="utf-8") as f:
                json.dump({"pr": pr["number"], "sha": head, "branch": branch, "nonce": nonce, "workdir": workdir,
                           "started_at": state["lock"]["started_at"]}, f)
        except OSError as e:
            raise AttemptFailed("workdir_error", f"試行の記録 {record} を書けない: {e}")
    except BaseException as e:
        ignore_signals()
        if isinstance(e, AttemptFailed):
            state["attempts"].append({"sha": head, "at": state["lock"]["started_at"], "result": "failed", "reason": e.kind})
            state["consecutive_failures"] += 1
        if not release_lock(sc, state, nonce) and isinstance(e, AttemptFailed):
            log("warn: この試行の失敗を状態コメントに記録できなかった(連続失敗にも数えられていない)")
        raise
    return {"pr": pr["number"], "sha": head, "attempt": attempt_no, "workdir": workdir}


def end(worktree, failed_reason):
    """試行を閉じる。completed なら反復の番号を返す。失敗として記録したら AttemptFailed を投げる。"""
    check_tools()
    wt = normalize_worktree(worktree)
    record = attempt_file(wt)
    rec = read_attempt(record)
    if rec is None:
        raise Precondition("閉じる試行が無い(この worktree で begin した試行の記録が無い。既に閉じたか、begin していない)")
    # git で分かる混入を先に見る。ブランチが切り替わっていても、PR は記録の番号で引くので、取り違えない
    changed = local_changes(wt, rec)
    me = run(["gh", "api", "user", "--jq", ".login"], cwd=wt).stdout.strip()
    sc = StateComment(wt, rec["pr"], me)
    state = sc.read()
    if state is None or not state["lock"]["running"] or state["lock"].get("nonce") != rec["nonce"]:
        # 自分の試行のロックではない。ほかの試行のロックを閉じないよう、何も書かない
        os.remove(record)
        raise Precondition("この試行のロックが、状態コメントに無い"
                           + ("(状態コメントを読めない)" if sc.unreadable else "")
                           + "。既に閉じたか、古いロックとして片付けられた。試行の記録は消した。"
                           "状態コメントの最後の試行を見て、この試行が記録済みかを確かめる")
    workdir = rec["workdir"]
    error = None
    if changed:
        error = AttemptFailed("contamination", changed)
    else:
        moved = pr_head_change(wt, rec)
        if moved:
            error = AttemptFailed("head_changed", moved)
    if error and failed_reason:
        # 混入があれば、レビュー役の失敗より優先して記録する(放っておくと、親がレビュー役の変更を自分の修正としてコミットしかねない)
        error.detail += f"\n\n(この試行は、もともと --failed で閉じようとした: {failed_reason})"
    elif failed_reason:
        error = AttemptFailed("reviewer_failed: " + " ".join(failed_reason.split())[:FAILED_REASON_CHARS], failed_reason)

    attempt = {"sha": rec["sha"], "at": rec["started_at"], "result": "failed"}
    if error:
        attempt["reason"] = error.kind
        state["consecutive_failures"] += 1
    else:
        reviews = collect_reviews(workdir)
        if not reviews:
            raise Precondition(f"レビュー役の出力が無い({workdir} に review-<役の名前>.md が1つも無い)。"
                               "出力を置いてから呼ぶ。レビュー役が失敗したなら、--failed を付けて閉じる")
        write_reviews(workdir, reviews)
        attempt["roles"] = [role for role, _ in reviews]
        previous = [a["roles"] for a in state["attempts"] if a.get("roles")]
        if previous and sorted(previous[-1]) != sorted(attempt["roles"]):
            log(f"warn: 直前の試行とレビュー役が違う(直前: {', '.join(previous[-1])}、今回: {', '.join(attempt['roles'])})。"
                "利用者の指示で変えたのでなければ、呼び忘れか、出力の置き忘れを確かめる")
        state["iter"] += 1
        state["consecutive_failures"] = 0
        attempt.update(result="completed", iter=state["iter"])
    state["attempts"].append(attempt)
    state["lock"] = dict(UNLOCKED)
    ignore_signals()  # ここから先は記録だけなので、中断させない
    sc.write(state)  # 書けなければ Precondition。ロックも試行の記録も残るので、もう一度 end を呼べる
    try:
        os.remove(record)
    except OSError as e:
        log(f"warn: 試行の記録 {record} を消せなかった(次の begin が止まる。手で消す): {e}")
    if error:
        try:
            with open(os.path.join(workdir, "failure.txt"), "w", encoding="utf-8") as f:
                f.write(f"{error.kind}\n{error.detail}\n")
        except OSError:  # 詳細を残せなくても、報告は続ける
            pass
        raise error
    return state["iter"]


def on_signal(signum, _frame):
    raise Interrupted(signal.Signals(signum).name)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("begin", help="前提を確かめ、試行を始める")
    b.add_argument("worktree", help="PR のブランチをチェックアウトした worktree の絶対パス")
    b.add_argument("--new-run", action="store_true", help="新しいシリーズを始める(利用者の指示があったときだけ使う)")
    e = sub.add_parser("end", help="混入が無いかを確かめ、試行の結果を記録する")
    e.add_argument("worktree", help="begin に渡したのと同じ worktree の絶対パス")
    e.add_argument("--failed", metavar="理由",
                   help="レビュー役が失敗したときに付ける。理由は PR の状態コメントに載る(100文字まで)")
    args = ap.parse_args()
    if args.cmd == "end" and args.failed is not None and not args.failed.strip():
        ap.error("--failed の理由が空")

    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(s, on_signal)
    try:
        if args.cmd == "begin":
            for k, v in begin(args.worktree, args.new_run).items():
                print(f"{k}={v}", flush=True)
        else:
            log(f"完了: 反復 {end(args.worktree, args.failed)}")
        return 0
    except AttemptFailed as e:
        log(f"failed: {e.kind}\n{e.detail}".rstrip())
        return 1
    except Precondition as e:
        log(f"error: {e}")
        return 2
    except Interrupted as e:
        log(f"error: シグナル {e} で止められた")
        return 2
    except Exception:
        log("error: internal_error\n" + traceback.format_exc())
        return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""PR のレビューループの1試行を、始める前と終えたあとに確かめて、PR の状態コメントに記録する。

    review_loop.py begin <worktree の絶対パス> [--new-run] [--roles 役,役,...]
    review_loop.py end   <worktree の絶対パス> [--failed 理由]

レビュー役は起動しない。観点スキルは、呼び出し元(親)が begin と end の間に呼ぶ。

begin: 前提(作業ディレクトリが worktree のトップ、作業ツリーがクリーン、ローカルの HEAD と PR の head が一致、
       自分のオープンな PR)を確かめ、作業ディレクトリと、レビュー役ごとの出力の置き場を作る。試行の記録(PR 番号、
       SHA、ブランチ、作業ディレクトリ、役ごとの出力の置き場)を git の管理ディレクトリに置き、標準出力に `pr=`、
       `sha=`、`attempt=`、`started=`、`workdir=`、役ごとの `out.<役の名前>=` の行を出す。GitHub には書かない。
end:   試行の記録を読み、begin のあとに作業ツリー、HEAD、ブランチ、PR の head が変わっていないかを確かめる。
       全ての役の出力を作業ディレクトリに集め(`review-<役の名前>.md`)、役の名前の区切りでつないで `reviews.md` を
       作り、試行の結果を PR の状態コメントに記録する。標準出力に `workdir=` と `roles=` の行を出す。
       レビュー役が失敗したときは、--failed に理由を付けて呼ぶ。

同じ PR で、2つのセッションが同時にループを回すことは防がない(ロックは無い)。反復の回数にも上限は無い。
どちらも、ループを回す親が1つであることと、親の終了の判断に任せる。

終了コード:
  0  begin: 試行を始めた。end: 試行を completed として記録した
  1  end: 試行の失敗を記録した(混入、PR の head の変化、--failed)
  2  何も記録していない(前提を満たさない、gh や git の失敗、閉じる試行が無い、出力の無い役がある)。
     end がこれで終わったときに試行が開いたままかは、stderr の理由による(SKILL.md の手順3)
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
# レビュー役の既定。begin の --roles で変える。変えるときは、SKILL.md の「前提」と手順2の表も合わせる。
# code-review を2つ並べるのは、同じ差分でも回ごとに見つける不具合が変わるため(skill-dev/review-loop/bench/README.md)
ROLES = ["code-review", "code-review-2", "security-review"]
COMMAND_TIMEOUT = 60          # git や gh の1回の呼び出し

MARKER = "review-loop-state"
FAILED_REASON_CHARS = 100     # 状態コメントに載せる、--failed の理由の文字数
TABLE_REASON_CHARS = 130      # 状態コメントの表に出す、失敗の種類と理由の文字数(reviewer_failed: と理由が収まる長さ)
ATTEMPT_FILE = "review-loop-attempt.json"  # 試行の記録。git の管理ディレクトリ(worktree ごと)に置く
ROLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")  # レビュー役の名前
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}$")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
SEPARATOR_RE = re.compile(r"^===== 観点: .* =====\s*$")


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


def parse_roles(arg):
    """--roles の値を、役の名前の一覧にする。"""
    roles = [r.strip() for r in arg.split(",")] if arg is not None else list(ROLES)
    bad = [r for r in roles if not ROLE_RE.match(r)]
    if bad or not roles:
        raise Precondition(f"--roles を役の名前として読めない: {arg!r}(カンマ区切り。名前は英数字と _ . : - で、80文字まで)")
    if len(set(roles)) != len(roles):
        raise Precondition(f"--roles に同じ名前がある: {arg}(同じスキルを重ねるときは code-review-2 のように番号を付ける)")
    return roles


# --- 状態コメント ------------------------------------------------------------
def valid_sha(v):
    return v is None or (isinstance(v, str) and bool(SHA_RE.match(v)))


def valid_state(s):
    """状態コメントの JSON が、このスクリプト(旧版を含む)の書いた形をしているか。render、begin、end が読むものだけを見る。
    旧版が記録していたロック、連続失敗の回数、観点、モデル、トークン数は読まないので、形も確かめない。"""
    try:
        prev = s.get("previous_run")
        return (bool(RUN_ID_RE.match(s["run_id"])) and isinstance(s["iter"], int)
                and all(isinstance(a["result"], str) and isinstance(a["at"], str)
                        and valid_sha(a.get("sha")) and isinstance(a.get("reason") or "", str)
                        and isinstance(a.get("iter") or 0, int)
                        and isinstance(a.get("roles") or [], list) and all(isinstance(n, str) for n in a.get("roles") or [])
                        for a in s["attempts"])
                and (prev is None or (bool(RUN_ID_RE.match(prev["run_id"])) and isinstance(prev["iterations"], int))))
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


class StateComment:
    def __init__(self, wt, pr_number, me):
        self.wt = wt
        self.pr = pr_number
        self.me = me
        self.id = None
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
            self.id = int(r.stdout.strip())
        else:
            run(["gh", "api", "-X", "PATCH", f"repos/{{owner}}/{{repo}}/issues/comments/{self.id}",
                 "--input", "-", "--jq", ".id"], cwd=self.wt, input=payload)


def new_run_id(previous=None):
    run_id = now().strftime("%Y%m%dT%H%M%S")
    if previous == run_id:  # 同じ秒に始め直すと作業ディレクトリが重なる
        time.sleep(1)
        run_id = now().strftime("%Y%m%dT%H%M%S")
    return run_id


def cell(text):
    """表のセルに入れる値を、表を壊さず(| と改行)、HTML として解釈されず(<)、メンションにならない(@)形にする。"""
    return text.replace("|", "\\|").replace("\n", " ").replace("<", "&lt;").replace("@", "@\u200b")


def render(state):
    raw = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    # HTML コメントを閉じないよう、また @ がメンションにならないようにエスケープする(JSON としては等価)
    raw = raw.replace(">", "\\u003e").replace("@", "\\u0040")
    lines = [f"<!-- {MARKER} {raw} -->", f"**review-loop** run {state['run_id']} — 反復 {state['iter']}", ""]
    prev = state.get("previous_run")
    if prev:
        lines += [f"直前のシリーズ: run {prev['run_id']}(反復 {prev['iterations']})", ""]
    if state["attempts"]:
        lines += ["| SHA | 時刻 | 結果 |", "|---|---|---|"]
        for a in state["attempts"]:
            result = a["result"] + (f"(反復 {a['iter']})" if a.get("iter") else "")
            if a.get("reason"):
                result += f": {a['reason'][:TABLE_REASON_CHARS]}"
            lines.append(f"| {cell((a.get('sha') or '')[:7])} | {cell(a['at'])} | {cell(result)} |")
        lines.append("")
    lines.append("<sub>review-loop のスクリプトが更新するコメント。手で編集しても上書きされる。</sub>")
    return "\n".join(lines)


# --- 作業ディレクトリ --------------------------------------------------------
def tmp_top():
    """<一時ディレクトリ>/review-loop を、自分だけが使える形で用意して返す。

    共有の一時ディレクトリ(TMPDIR のない Linux の /tmp)で他人に先回りされたり、レビューの出力を
    読まれたりしないよう、起点は自分が所有するディレクトリに限り、権限を 0700 に絞って使う。"""
    top = os.path.join(tempfile.gettempdir(), "review-loop")
    try:
        os.makedirs(top, mode=0o700, exist_ok=True)
        st = os.lstat(top)
        if stat.S_ISLNK(st.st_mode) or st.st_uid != os.getuid():
            raise Precondition(f"{top} が自分の所有するディレクトリではない")
        if st.st_mode & 0o077:  # umask などで広い権限で作られていたら絞る
            os.chmod(top, 0o700)
    except OSError as e:
        raise Precondition(f"作業ディレクトリを作れない: {e}")
    return top


def make_workdir(top, repo, pr_number, run_id, attempt_no):
    """<top>/<owner>_<repo>/<PR番号>/<run_id>/<試行>/ を新しく作って返す。
    既にあれば、前の出力と混ざるので始めない。"""
    path = os.path.join(top, repo, str(pr_number), run_id, str(attempt_no))
    try:
        os.makedirs(path)
    except FileExistsError:
        raise Precondition(f"作業ディレクトリが既にある: {path}。前の試行の出力と混ざるので始めない。"
                           "要らないものなら、消してから実行する")
    except OSError as e:
        raise Precondition(f"作業ディレクトリを作れない: {e}")
    return path


def make_outs(top, roles):
    """レビュー役ごとの出力の置き場を作り、{役の名前: 出力のファイルのパス} を返す。

    役ごとに、名前を推し量れない別のディレクトリにする。作業ディレクトリの中に置くと、レビュー役が、ほかの役の
    出力や、過去の試行の記録(俯瞰の役の出力)を、渡されたパスの隣で見つけられる。"""
    outs = {}
    try:
        for role in roles:
            d = os.path.join(top, "out", uuid.uuid4().hex)
            os.makedirs(d, mode=0o700)
            outs[role] = os.path.join(d, "review.md")
    except OSError as e:
        remove_outs(outs)
        raise Precondition(f"レビュー役の出力の置き場を作れない: {e}")
    return outs


def remove_outs(outs):
    for path in outs.values():
        shutil.rmtree(os.path.dirname(path), ignore_errors=True)


# --- 試行の記録 --------------------------------------------------------------
def attempt_file(wt):
    """試行の記録の置き場。git の管理ディレクトリの中なので、作業ツリーを汚さず、worktree ごとに分かれる。"""
    return os.path.join(run(["git", "rev-parse", "--absolute-git-dir"], cwd=wt).stdout.strip(), ATTEMPT_FILE)


def write_attempt(path, rec):
    """試行の記録を書く。書きかけのファイルを残さないよう、隣に書いてから置き換える。"""
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise Precondition(f"試行の記録 {path} を書けない: {e}")


def read_attempt(path):
    """試行の記録を返す。無ければ None。読めない形なら Precondition。"""
    hint = "この試行は閉じられないので、ファイルを消してから、手順1からやり直す"
    try:
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise Precondition(f"試行の記録 {path} を読めない: {e}。{hint}")
    outs = rec.get("outs") if isinstance(rec, dict) else None
    ok = (isinstance(rec, dict) and isinstance(rec.get("pr"), int) and isinstance(rec.get("attempt"), int)
          and valid_sha(rec.get("sha")) and rec.get("sha") and isinstance(rec.get("new_run"), bool)
          and all(isinstance(rec.get(k), str) for k in ("branch", "workdir", "started_at", "run_id"))
          and RUN_ID_RE.match(rec["run_id"])
          and isinstance(outs, dict) and outs
          and all(isinstance(k, str) and ROLE_RE.match(k) and isinstance(v, str) for k, v in outs.items()))
    if not ok:
        raise Precondition(f"試行の記録 {path} が、begin の書いた形をしていない。{hint}")
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
def collect_reviews(outs):
    """全ての役の出力を読み、[(役の名前, 本文)] を名前の順で返す。出力の無い役があれば Precondition。"""
    found, missing = [], []
    for role, path in sorted(outs.items()):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            text = ""
        except (OSError, ValueError) as e:
            raise Precondition(f"{role} の出力 {path} を読めない: {e}")
        if text.strip():
            found.append((role, text))
        else:
            missing.append(f"{role}({path})")
    if missing:
        raise Precondition("出力の無いレビュー役がある: " + "、".join(missing)
                           + "。結果が届いているなら、その内容をそのまま置く。その役が失敗したなら、--failed を付けて閉じる")
    return found


def write_reviews(workdir, reviews):
    """役ごとの出力を作業ディレクトリに写し(review-<役の名前>.md)、役の名前の区切りでつないで reviews.md に書く。

    本文に区切りと同じ形の行があれば、行頭に空白を足す(行頭から始まる区切りの行を数えれば、役を数えられるように)。"""
    parts = []
    try:
        for role, text in reviews:
            with open(os.path.join(workdir, f"review-{role}.md"), "w", encoding="utf-8") as f:
                f.write(text)
            body = "\n".join(" " + line if SEPARATOR_RE.match(line) else line for line in text.rstrip().split("\n"))
            parts.append(f"===== 観点: {role} =====\n{body}")
        with open(os.path.join(workdir, "reviews.md"), "w", encoding="utf-8") as f:
            f.write("\n\n".join(parts) + "\n")
    except OSError as e:
        raise Precondition(f"レビュー役の出力を {workdir} に書けない: {e}")


# --- 本体 --------------------------------------------------------------------
def begin(worktree, new_run, roles_arg=None):
    """試行を始める。標準出力に出す行の辞書を返す。GitHub には書かない。"""
    check_tools()
    roles = parse_roles(roles_arg)
    wt = normalize_worktree(worktree)
    if os.path.realpath(os.getcwd()) != wt:
        # レビュー役は、呼び出し元(親)の作業ディレクトリで動く。ここが worktree でなければ、別のツリーをレビューする
        raise Precondition(f"作業ディレクトリ({os.getcwd()})が worktree のトップ({wt})ではない。"
                           "レビュー役はあなたの作業ディレクトリで動くので、セッションの作業ディレクトリを worktree にしてから"
                           "実行する(コマンドの前に cd を付けて通しても、レビュー役は元の場所で動く)")
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
    state = sc.read()
    if sc.unreadable:
        if not new_run:
            raise Precondition(f"状態コメント {sc.id} を読めない(手で編集された可能性がある)。反復回数を黙って0に"
                               "戻さないよう、ここで止める。利用者の指示があれば --new-run で始め直す")
        log(f"warn: 状態コメント {sc.id} を読めないので、新しいシリーズとして上書きする")
    fresh = state is None or new_run  # 新しいシリーズ。状態コメントに書くのは end
    if fresh:
        run_id, attempt_no = new_run_id(state["run_id"] if state else None), 1
    else:
        run_id, attempt_no = state["run_id"], len(state["attempts"]) + 1

    workdir, outs = None, {}
    try:
        top = tmp_top()
        workdir = make_workdir(top, repo_slug(pr), pr["number"], run_id, attempt_no)
        outs = make_outs(top, roles)
        started = iso(now())
        write_attempt(record, {"pr": pr["number"], "sha": head, "branch": branch, "run_id": run_id, "new_run": fresh,
                               "attempt": attempt_no, "started_at": started, "workdir": workdir, "outs": outs})
    except BaseException:
        ignore_signals()
        # 始められなかった試行のものを残さない(残すと、次の begin が「作業ディレクトリが既にある」で止まる)
        if workdir:
            shutil.rmtree(workdir, ignore_errors=True)
        remove_outs(outs)
        try:
            os.remove(record)
        except OSError:
            pass
        raise
    lines = {"pr": pr["number"], "sha": head, "attempt": attempt_no, "started": started, "workdir": workdir}
    lines.update({f"out.{role}": path for role, path in outs.items()})
    return lines


def end(worktree, failed_reason):
    """試行を閉じる。completed なら、標準出力に出す行の辞書を返す。失敗として記録したら AttemptFailed を投げる。"""
    check_tools()
    wt = normalize_worktree(worktree)
    record = attempt_file(wt)
    rec = read_attempt(record)
    if rec is None:
        raise Precondition("閉じる試行が無い(この worktree で begin した試行の記録が無い。既に閉じたか、begin していない)")
    workdir = rec["workdir"]
    # git で分かる混入を先に見る。ブランチが切り替わっていても、PR は記録の番号で引くので、取り違えない
    changed = local_changes(wt, rec)

    me = run(["gh", "api", "user", "--jq", ".login"], cwd=wt).stdout.strip()
    sc = StateComment(wt, rec["pr"], me)
    state = sc.read()
    if sc.unreadable and not rec["new_run"]:
        # 混入は、記録できなくても必ず伝える(伝えないと、親がレビュー役の変更に気づかないまま、自分の修正としてコミットしかねない)
        raise Precondition(f"状態コメント {sc.id} を読めない(試行の間に、手で編集された可能性がある)。試行は開いたまま。"
                           "直せなければ、試行の記録を消し、利用者の指示で --new-run から始め直す"
                           + (f"\n\nこの試行の間に、次の変更があった。内容を確かめる:\n{changed}" if changed else ""))
    if state is None or (rec["new_run"] and state["run_id"] != rec["run_id"]):
        previous = {"run_id": state["run_id"], "iterations": state["iter"]} if state else None
        state = {"run_id": rec["run_id"], "iter": 0, "attempts": [], "previous_run": previous}

    recorded = state["attempts"][rec["attempt"] - 1] if len(state["attempts"]) >= rec["attempt"] else None
    if recorded and recorded.get("at") == rec["started_at"] and recorded.get("sha") == rec["sha"]:
        # 前の end が、書き込みには成功していた(gh が応答を受け取る前に止まった、など)。二重に記録しない
        log("warn: この試行は既に記録されている。記録は変えない")
        attempt = recorded
        error = None if recorded["result"] == "completed" else AttemptFailed(recorded.get("reason") or "failed", "(前の end が記録した失敗)")
    else:
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
        else:
            reviews = collect_reviews(rec["outs"])
            write_reviews(workdir, reviews)
            attempt["roles"] = [role for role, _ in reviews]
            previous = [a["roles"] for a in state["attempts"] if a.get("roles")]
            if previous and sorted(previous[-1]) != sorted(attempt["roles"]):
                log(f"warn: 直前の試行とレビュー役が違う(直前: {', '.join(previous[-1])}、今回: {', '.join(attempt['roles'])})。"
                    "利用者の指示で変えたのでなければ、begin の --roles の付け忘れを確かめる")
            state["iter"] += 1
            attempt.update(result="completed", iter=state["iter"])
        state["attempts"].append(attempt)
        ignore_signals()  # ここから先は記録だけなので、中断させない
        sc.write(state)  # 書けなければ Precondition。試行の記録は残るので、もう一度 end を呼べる
    try:
        os.remove(record)
    except OSError as e:
        log(f"warn: 試行の記録 {record} を消せなかった(次の begin が止まる。手で消す): {e}")
    remove_outs(rec["outs"])  # 出力は作業ディレクトリに写した。置き場を残すと、次の試行のレビュー役が見つけうる
    if error:
        try:
            with open(os.path.join(workdir, "failure.txt"), "w", encoding="utf-8") as f:
                f.write(f"{error.kind}\n{error.detail}\n")
        except OSError:  # 詳細を残せなくても、報告は続ける
            pass
        raise error
    return {"iter": attempt.get("iter") or state["iter"], "workdir": workdir, "roles": ",".join(attempt.get("roles") or [])}


def on_signal(signum, _frame):
    raise Interrupted(signal.Signals(signum).name)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("begin", help="前提を確かめ、試行を始める")
    b.add_argument("worktree", help="PR のブランチをチェックアウトした worktree の絶対パス")
    b.add_argument("--new-run", action="store_true", help="新しいシリーズを始める(利用者の指示があったときだけ使う)")
    b.add_argument("--roles", metavar="役,役,...",
                   help=f"この試行で呼ぶレビュー役の名前(カンマ区切り。既定 {','.join(ROLES)})。利用者の指示で観点を変えたときだけ使う")
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
            for k, v in begin(args.worktree, args.new_run, args.roles).items():
                print(f"{k}={v}", flush=True)
        else:
            done = end(args.worktree, args.failed)
            print(f"workdir={done['workdir']}\nroles={done['roles']}", flush=True)
            log(f"完了: 反復 {done['iter']}")
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

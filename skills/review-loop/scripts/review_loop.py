#!/usr/bin/env python3
"""PR のレビューループを1反復だけ進める。

    review_loop.py iterate <worktree の絶対パス> [--new-run]

観点別のレビュースキルを `claude -p` で並列に実行し、判定役の `claude -p` に突き合わせと
競合の裁定をさせ、判定 JSON を標準出力に出す。コードは修正しない。ループの状態は PR の
コメント1つ(マーカー付き)に記録する。

終了コード:
  0  成功。標準出力は判定 JSON だけ
  1  試行が失敗した。状態コメントに記録済み
  2  試行を始めなかった(前提を満たさない、ロックを取れない、上限に達した、開始前に中断された)。記録しない
どの場合も stderr の最後の行は作業ディレクトリのパス(作る前に終わったときは空行)。
"""
import argparse
import datetime as dt
import json
import os
import queue
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid

# --- 設定 ------------------------------------------------------------------
# 観点スキル。先頭の `/` を除いたスキル名と、その引数を書く。プラグインのスキルは `plugin:name` の形式。
# 引数の {pr} は PR 番号に、{base} は PR のベースブランチ名に置き換わる。引数の意味はスキルごとに違うので、
# PR 番号を自動では足さない。
# - 組み込みの code-review は、レベルを指定しないと利用者が最後に使ったレベルを引き継ぎ、反復ごとに
#   深さが変わりうるので固定する
# - mattpocock-skills:code-review は、引数を比較の起点(commit や branch)として読む。PR 番号を渡すと
#   短い SHA と取り違えうるので、起点と仕様の在りかを分けて書く
PERSPECTIVES = [
    "code-review high {pr}",
    "security-review",
    "mattpocock-skills:code-review origin/{base}(仕様は PR #{pr} の本文)",
]

SAFETY_MAX_ITER = 10          # シリーズあたりの反復の上限
MAX_CONSECUTIVE_FAILURES = 3  # 連続失敗の上限

PREFLIGHT_TIMEOUT = 2 * 60    # 事前確認(init を受け取るまで)
REVIEW_TIMEOUT = 40 * 60      # レビュー役1つあたり
JUDGE_TIMEOUT = 20 * 60       # 判定役
MARGIN = 5 * 60               # gh の呼び出しやロックの確認などの余裕
BASH_TIMEOUT = 90 * 60        # SKILL.md で Bash ツールに指定する制限時間
BASH_TIMEOUT_MAX = 120 * 60   # Bash ツールの最大制限時間
STALE_LOCK_AFTER = REVIEW_TIMEOUT + JUDGE_TIMEOUT + MARGIN
WATCHDOG_GRACE = 60           # 子の見張り役が、親のタイムアウトに加えて待つ時間
LOCK_SETTLE_SECONDS = 3       # nonce を書いてから読み直すまで
POLL_SECONDS = 2

MARKER = "review-loop-state"
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}$")
STRIP_ENV = ("CLAUDE_JOB_DIR", "CLAUDE_CODE_SESSION_KIND", "CLAUDE_CODE_SESSION_ID")
GUARD_ENV = "REVIEW_LOOP_ACTIVE"

NO_MUTATION = "ファイルの編集、checkout、commit、stash、pushなど、作業ツリーやブランチを変える操作をしないでください。"
REVIEW_CONSTRAINT = "他のレビューと並列に、同じworktreeで実行しています。" + NO_MUTATION
JUDGE_CONSTRAINT = "レビュー対象のworktreeで実行しています。" + NO_MUTATION

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verdict.schema.json")


class Precondition(Exception):
    """前提を満たさない。試行を始めず、終了コード2で終わる。"""


class AttemptFailed(Exception):
    """試行の失敗。kind と対象(どの子か)だけを状態コメントに載せ、detail は stderr と作業ディレクトリに残す。"""

    def __init__(self, kind, target="", detail=""):
        super().__init__(f"{kind}: {target}".rstrip(": "))
        self.kind, self.target, self.detail = kind, target, detail

    @property
    def reason(self):
        return str(self)


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
    try:
        r = subprocess.run(args, cwd=cwd, input=input, capture_output=True, text=True,
                           stdin=None if input is not None else subprocess.DEVNULL)
    except OSError as e:
        raise Precondition(f"{args[0]} を起動できない: {e}")
    if check and r.returncode != 0:
        raise Precondition(f"`{' '.join(args[:4])} …` が失敗した(終了コード {r.returncode}): {r.stderr.strip()}")
    return r


def sandbox_hint(text):
    keys = ("sandbox", "EPERM", "Operation not permitted", "ENOTFOUND", "ECONNREFUSED", "EAI_AGAIN", "eychain")
    if any(k in text for k in keys):
        return "(sandbox 内で実行している可能性がある。回避策は自動では取らないので、設定か実行場所を見直してほしい)"
    return ""


def ignore_signals():
    """後片付けの途中で2回目のシグナルに割り込まれないようにする。以後は終了するだけなので戻さない。"""
    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(s, signal.SIG_IGN)


# --- 子プロセス --------------------------------------------------------------
def kill_group(p):
    """子をプロセスグループごと止める。子自身が終わっていても、グループに残った孫(バックグラウンドの
    シェルなど)を止めるために送る。子が終わってから時間が経つと、PID が再利用されて無関係な
    グループに届きうるので、終わった子には終わりを検知した直後に一度だけ使う(Children.finish)。"""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(p.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        if p.poll() is None:
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                pass


class Children:
    """起動した子を覚えておき、どこで終わっても全て止められるようにする。

    子は見張り役(このスクリプトの `_watch`)を介して新しいプロセスグループで起動する。スクリプトが
    SIGKILL で止められて後始末できなくても、見張り役が親の消滅を検知してグループごと止める。"""

    def __init__(self):
        self.procs = []

    def spawn(self, args, timeout, cwd, env, stdin, stdout, stderr):
        try:
            p = subprocess.Popen(watched(args, timeout), cwd=cwd, env=env, stdin=stdin, stdout=stdout,
                                 stderr=stderr, start_new_session=True)
        except OSError as e:
            raise AttemptFailed("spawn_error", args[0], str(e))
        self.procs.append(p)
        return p

    def finish(self, p):
        """子が終わった(または止める)ときに、グループの残りを止めて以後は触らない。"""
        kill_group(p)
        self.procs.remove(p)

    def kill_all(self):
        for p in list(self.procs):
            self.finish(p)


def watched(args, timeout):
    """args を見張り役(`_watch`)経由で起動するコマンドにする。"""
    return [sys.executable, os.path.abspath(__file__), "_watch", str(os.getpid()),
            str(timeout + WATCHDOG_GRACE), "--", *args]


def watch_main(parent_pid, limit, cmd):
    """見張り役。cmd を同じグループで起動し、親が消えるか制限時間を超えたらグループごと止める。"""
    p = subprocess.Popen(cmd)
    deadline = time.monotonic() + limit
    while p.poll() is None:
        if os.getppid() != parent_pid or time.monotonic() > deadline:
            os.killpg(0, signal.SIGKILL)
        time.sleep(1)
    return p.returncode


def child_env():
    env = {k: v for k, v in os.environ.items() if k not in STRIP_ENV}
    env[GUARD_ENV] = "1"
    return env


def summarize_denials(denials):
    out = []
    for d in denials:
        inp = json.dumps(d.get("tool_input", {}), ensure_ascii=False)
        out.append(f"{d.get('tool_name', '?')} {inp[:200]}")
    return "; ".join(out)


def check_result(label, rc, base, attempt, structured=False):
    """子の結果を読んで費用を attempt に足し、成功の条件を全て満たすか確かめる。結果の JSON を返す。"""
    try:
        with open(base + ".stdout.json", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        with open(base + ".stderr.txt", encoding="utf-8", errors="replace") as f:
            err = f.read().strip()[-1000:]
        raise AttemptFailed("child_error", label, f"結果の JSON を読めない(終了コード {rc})。stderr: {err}{sandbox_hint(err)}")
    attempt["cost_usd"] += data.get("total_cost_usd") or 0.0
    denials = data.get("permission_denials") or []
    if denials:
        raise AttemptFailed("permission_denied", label, summarize_denials(denials))
    if rc != 0 or data.get("subtype") != "success" or data.get("is_error"):
        raise AttemptFailed("child_error", label, f"終了コード {rc}、subtype {data.get('subtype')}、"
                            f"is_error {data.get('is_error')}: {str(data.get('result', ''))[:500]}")
    if structured:
        if not isinstance(data.get("structured_output"), dict):
            raise AttemptFailed("no_output", label, "structured_output がない")
    elif not str(data.get("result") or "").strip():
        raise AttemptFailed("no_output", label, "result が空")
    return data


# --- 前提チェック ------------------------------------------------------------
def skill_name(spec):
    return spec.split()[0]


def check_tools():
    if sys.version_info < (3, 9):
        raise Precondition("Python 3.9 以降が必要")
    missing = [c for c in ("git", "gh", "claude") if shutil.which(c) is None]
    if missing:
        raise Precondition(f"コマンドが見つからない: {', '.join(missing)}")
    if PREFLIGHT_TIMEOUT + REVIEW_TIMEOUT + JUDGE_TIMEOUT + MARGIN > BASH_TIMEOUT or BASH_TIMEOUT > BASH_TIMEOUT_MAX:
        raise Precondition("タイムアウトの合計が Bash ツールの制限時間を超えている(スクリプト冒頭の設定を見直す)")
    names = [skill_name(s) for s in PERSPECTIVES]
    if len(set(names)) != len(names):  # 出力ファイルと結果を観点の名前で分けているため
        raise Precondition(f"PERSPECTIVES に同じスキルが重複している: {', '.join(names)}")


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
    r = run(["gh", "pr", "view", "--json", "number,headRefOid,baseRefName,state,author,url"], cwd=wt, check=False)
    if r.returncode != 0:
        raise Precondition(f"このブランチの PR を取得できない: {r.stderr.strip()}")
    return json.loads(r.stdout)


def snapshot(wt):
    """HEAD の SHA、ブランチ名、PR の head などを返す。混入の検出に使う。"""
    pr = pr_view(wt)
    m = re.match(r"https?://[^/]+/([^/]+)/([^/]+)/pull/", pr.get("url") or "")
    return {
        "number": pr["number"],
        "base": pr["baseRefName"],
        "repo": f"{m.group(1)}_{m.group(2)}" if m else "unknown",
        "state": pr.get("state"),
        "author": (pr.get("author") or {}).get("login"),
        "head": run(["git", "rev-parse", "HEAD"], cwd=wt).stdout.strip(),
        "branch": run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=wt, check=False).stdout.strip(),
        "pr_head": pr["headRefOid"],
    }


def preflight(wt, env):
    """子を1回だけ起動し、init を受け取ったらすぐ止める。API を呼ぶ前に止まるので費用はほぼかからない。"""
    err_file = tempfile.TemporaryFile(mode="w+")
    try:
        p = subprocess.Popen(watched(["claude", "-p", "--output-format", "stream-json", "--verbose", "ok"],
                                     PREFLIGHT_TIMEOUT),
                             cwd=wt, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=err_file, text=True, start_new_session=True)
    except OSError as e:
        raise Precondition(f"claude を起動できない: {e}")
    lines = queue.Queue()

    def reader():
        for line in p.stdout:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=reader, daemon=True).start()
    deadline = time.monotonic() + PREFLIGHT_TIMEOUT
    init = None
    try:
        while init is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                line = lines.get(timeout=remaining)
            except queue.Empty:
                break
            if line is None:
                break
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("type") == "system" and msg.get("subtype") == "init":
                init = msg
    finally:
        kill_group(p)
    if init is None:
        err_file.seek(0)
        err = err_file.read().strip()[-1000:]
        raise Precondition("事前確認: claude が起動しなかった(init が来ない)。認証・sandbox・ネットワークを確かめてほしい。"
                           f"stderr: {err}{sandbox_hint(err)}")
    if os.path.realpath(init.get("cwd") or "") != wt:
        raise Precondition(f"事前確認: 子の cwd が worktree と一致しない: {init.get('cwd')}")
    # 組み込みのコマンド(security-review など)は skills には載らず、slash_commands にだけ載る
    available = set(init.get("skills") or []) | set(init.get("slash_commands") or [])
    missing = [skill_name(s) for s in PERSPECTIVES if skill_name(s) not in available]
    if missing:
        raise Precondition(f"事前確認: 観点スキルが見つからない: {', '.join(missing)}"
                           "(名前の誤りか未導入。プラグインのスキルは plugin:name の形式で書く)")


# --- PR の状態コメント -------------------------------------------------------
def valid_state(s):
    """状態コメントの JSON が、このスクリプトの書いた形をしているか(render と acquire_lock が読むものを全て)。"""
    try:
        lock, prev = s["lock"], s.get("previous_run")
        if lock["running"]:
            parse_iso(lock["started_at"])
        return (bool(RUN_ID_RE.match(s["run_id"]))
                and isinstance(s["iter"], int) and isinstance(s["consecutive_failures"], int)
                and isinstance(lock["running"], bool)
                and all(isinstance(a["result"], str) and isinstance(a["at"], str)
                        and isinstance(a.get("sha") or "", str) and isinstance(a.get("cost_usd", 0), (int, float))
                        for a in s["attempts"])
                and (prev is None or (isinstance(prev["run_id"], str) and isinstance(prev["iterations"], int))))
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


class StateComment:
    def __init__(self, wt, pr_number, me):
        self.wt = wt
        self.pr = pr_number
        self.me = me
        self.id = None
        self.created = None  # このプロセスが作ったコメントの id

    def read(self):
        """状態を返す。コメントがない、または読めない形なら None(読めないコメントは上書きする)。"""
        r = run(["gh", "api", "--paginate", f"repos/{{owner}}/{{repo}}/issues/{self.pr}/comments",
                 "--jq", ".[] | {id, login: .user.login, created_at, body}"], cwd=self.wt)
        found = []
        for line in r.stdout.splitlines():
            if line.strip():
                c = json.loads(line)
                if c["login"] == self.me and f"<!-- {MARKER} " in (c["body"] or ""):
                    found.append(c)
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
            log(f"warn: 状態コメント {self.id} の JSON を読めない。新しいシリーズとして上書きする")
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
        lines += ["| SHA | 時刻 | 結果 | 費用 |", "|---|---|---|---|"]
        for a in state["attempts"]:
            result = a["result"] + (f"(反復 {a['iter']})" if a.get("iter") else "")
            if a.get("reason"):
                reason = a["reason"][:100].replace("|", "\\|").replace("<", "&lt;").replace("@", "@​")
                result += f": {reason}"
            lines.append(f"| {(a['sha'] or '')[:7]} | {a['at']} | {result} | ${a.get('cost_usd', 0):.2f} |")
        lines += ["", "失敗した試行の費用は、途中で止めた子の分を含まない(下限)。", ""]
    lines.append("<sub>review-loop のスクリプトが更新するコメント。手で編集しても上書きされる。</sub>")
    return "\n".join(lines)


def acquire_lock(sc, head, new_run):
    """ロックを取り、状態と nonce を返す。

    誤って二重に起動したことを検出するためのもので、厳密な排他制御ではない。ループを駆動する親は
    1つだけなので、gh の書き込みが遅れて両方が通る程度の取りこぼしは許容する。"""
    state = sc.read()
    if state is not None and state["lock"]["running"]:
        age = (now() - parse_iso(state["lock"]["started_at"])).total_seconds()
        if age < STALE_LOCK_AFTER:
            raise Precondition(f"別の試行が実行中(開始 {state['lock']['started_at']})。二重起動の可能性がある")
        log(f"warn: 古いロックが残っていた(開始 {state['lock']['started_at']})。前回の試行を interrupted として記録する")
        state["attempts"].append({"sha": state["lock"].get("sha"), "at": state["lock"]["started_at"],
                                  "result": "interrupted", "reason": "stale_lock", "cost_usd": 0})
        state["consecutive_failures"] += 1
    if state is None:
        state = new_state()
    elif new_run:
        state = new_state({"run_id": state["run_id"], "iterations": state["iter"]})
    nonce = uuid.uuid4().hex
    state["lock"] = {"running": True, "started_at": iso(now()), "sha": head, "nonce": nonce}
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
        raise Precondition("ロックの取得で競合した(二重起動の可能性がある)。撤退する")
    return state, nonce


def release_lock(sc, state, nonce):
    try:
        current = sc.read()
        if current and current["lock"].get("nonce") not in (nonce, None):
            log("warn: ロックが別の試行に書き換えられていた。状態コメントは更新しない")
            return
        state["lock"] = dict(UNLOCKED)
        sc.write(state)
    except Exception as e:  # ロックを解除できなくても、結果は返す
        log(f"warn: 状態コメントを更新できなかった(次回、古いロックとして扱われる): {e}")


# --- レビュー役と判定役 ------------------------------------------------------
def safe_name(s):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", s)


def run_reviews(wt, env, pr, workdir, children, attempt):
    """観点別レビューを並列に実行し、{観点: result} を返す。1つでも失敗したら残りを止める。"""
    running = {}
    for spec in PERSPECTIVES:
        base = os.path.join(workdir, f"review-{safe_name(skill_name(spec))}")
        prompt = "/" + spec.replace("{pr}", str(pr["number"])).replace("{base}", pr["base"])
        with open(base + ".stdout.json", "w") as out, open(base + ".stderr.txt", "w") as err:
            p = children.spawn(["claude", "-p", "--output-format", "json", "--append-system-prompt",
                                REVIEW_CONSTRAINT, prompt],
                               REVIEW_TIMEOUT, cwd=wt, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        running[skill_name(spec)] = (p, base, time.monotonic())
    results = {}
    while running:
        for name, (p, base, started) in list(running.items()):
            rc = p.poll()
            if rc is None:
                if time.monotonic() - started > REVIEW_TIMEOUT:
                    raise AttemptFailed("timeout", f"review {name}", f"{REVIEW_TIMEOUT // 60} 分を超えた")
                continue
            del running[name]
            children.finish(p)
            data = check_result(f"review {name}", rc, base, attempt)
            results[name] = data["result"]
            log(f"review {name}: 完了")
        if running:
            time.sleep(POLL_SECONDS)
    return {skill_name(s): results[skill_name(s)] for s in PERSPECTIVES}


JUDGE_PROMPT = """\
PR #{pr} に対する観点別レビューの出力を、標準入力で渡す(観点ごとに区切ってある)。
あなたの役割は、指摘を突き合わせ、観点どうしの競合を裁定し、レビューを続けるべきかを推奨すること。修正はしない。
- 同じ問題への指摘は1件にまとめ、挙げた観点を perspectives に全て入れる
- 指摘を捨てない。根拠が疑わしいものは、コードを読んで確かめ、その結果を rationale に書く
- 観点どうしで両立しない指摘(一方に従うと他方が悪化する)は conflicts に載せ、PR の意図に照らしてどちらを採るかを ruling で裁定する。action が fix になったものは findings にも載せ、その conflict に競合の id を入れる
- behavior_change は、その指摘に従って修正したときにプログラムの挙動が変わるかどうか
- PR 本文やコードコメントに判断の理由(以前のレビューで採らなかった指摘など)が書かれていれば、それを踏まえる。理由が妥当なら蒸し返さない
- recommendation.continue は、挙動が変わる修正を要する指摘が残っていれば true
- 指摘がなければ findings と conflicts は空配列にする
"""


def run_judge(wt, env, pr_number, reviews, workdir, children, attempt):
    input_path = os.path.join(workdir, "judge-input.md")
    with open(input_path, "w", encoding="utf-8") as f:
        for name, text in reviews.items():
            f.write(f"===== 観点: {name} =====\n{text.strip()}\n===== ここまで: {name} =====\n\n")
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.dumps(json.load(f), ensure_ascii=False)
    base = os.path.join(workdir, "verdict")
    with open(input_path, "rb") as fin, open(base + ".stdout.json", "w") as out, open(base + ".stderr.txt", "w") as err:
        p = children.spawn(["claude", "-p", "--output-format", "json", "--json-schema", schema,
                            "--append-system-prompt", JUDGE_CONSTRAINT, JUDGE_PROMPT.format(pr=pr_number)],
                           JUDGE_TIMEOUT, cwd=wt, env=env, stdin=fin, stdout=out, stderr=err)
    try:
        p.wait(JUDGE_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise AttemptFailed("timeout", "judge", f"{JUDGE_TIMEOUT // 60} 分を超えた")
    children.finish(p)
    data = check_result("judge", p.returncode, base, attempt, structured=True)
    return data["structured_output"]


def check_contamination(wt, start):
    problems = []
    status = git_status(wt)
    if status.strip():
        problems.append("作業ツリーがクリーンでない:\n" + status.rstrip())
    try:
        cur = snapshot(wt)
    except Precondition as e:
        problems.append(str(e))
        cur = {}
    for key, label in (("head", "HEAD"), ("branch", "ブランチ"), ("pr_head", "PR の head")):
        if key in cur and cur[key] != start[key]:
            problems.append(f"{label} が変わった: {start[key]} → {cur[key]}")
    if problems:
        raise AttemptFailed("contamination", "", "\n".join(problems) + "\n(変更は元に戻していない)")


# --- 本体 --------------------------------------------------------------------
def iterate(worktree, new_run, ctx):
    # 前提チェック。ロックを取る前なので、失敗しても状態には記録しない
    if os.environ.get(GUARD_ENV):
        raise Precondition(f"{GUARD_ENV} が設定済み。レビューループの中から再帰的に起動された")
    os.environ[GUARD_ENV] = "1"
    check_tools()
    env = child_env()
    wt = normalize_worktree(worktree)
    if git_status(wt).strip():
        raise Precondition("作業ツリーがクリーンでない。コミットしてから実行する")
    me = run(["gh", "api", "user", "--jq", ".login"], cwd=wt).stdout.strip()
    start = snapshot(wt)
    if start["state"] != "OPEN":
        raise Precondition(f"PR #{start['number']} はオープンではない({start['state']})")
    if start["author"] != me:
        raise Precondition(f"PR #{start['number']} の作成者({start['author']})が自分({me})ではない")
    if start["head"] != start["pr_head"]:
        raise Precondition(f"ローカルの HEAD({start['head'][:7]})が PR の head({start['pr_head'][:7]})と"
                           "一致しない。push してから実行する")
    preflight(wt, env)

    sc = StateComment(wt, start["number"], me)
    children = Children()
    attempt = None
    state, nonce = acquire_lock(sc, start["head"], new_run)
    try:  # ここから先は、どこで終わってもロックを解除する
        if state["iter"] >= SAFETY_MAX_ITER:
            raise Precondition(f"反復が安全上限({SAFETY_MAX_ITER} 回)に達した")
        if state["consecutive_failures"] >= MAX_CONSECUTIVE_FAILURES:
            raise Precondition(f"連続失敗が {MAX_CONSECUTIVE_FAILURES} 回に達した。原因を取り除いてから、利用者の指示で --new-run する")

        attempt = {"sha": start["head"], "at": state["lock"]["started_at"], "result": "failed", "cost_usd": 0.0}
        ctx["attempt"] = attempt
        ctx["workdir"] = make_workdir(start, state["run_id"], len(state["attempts"]) + 1)
        log(f"作業ディレクトリ: {ctx['workdir']}")
        reviews = run_reviews(wt, env, start, ctx["workdir"], children, attempt)
        verdict = run_judge(wt, env, start["number"], reviews, ctx["workdir"], children, attempt)
        children.kill_all()
        check_contamination(wt, start)
        with open(os.path.join(ctx["workdir"], "verdict.json"), "w", encoding="utf-8") as f:
            json.dump(verdict, f, ensure_ascii=False, indent=2)
        ignore_signals()  # ここから先は成功の記録だけなので、中断させない
        state["iter"] += 1
        state["consecutive_failures"] = 0
        attempt.update(result="completed", iter=state["iter"])
        return verdict
    except BaseException as e:
        ignore_signals()
        if attempt is not None:
            attempt["reason"], detail = classify(e)
            state["consecutive_failures"] += 1
            if ctx["workdir"]:
                with open(os.path.join(ctx["workdir"], "failure.txt"), "w", encoding="utf-8") as f:
                    f.write(f"{attempt['reason']}\n{detail}\n")
        raise
    finally:
        ignore_signals()
        children.kill_all()
        if attempt is not None:
            attempt["cost_usd"] = round(attempt["cost_usd"], 4)
            state["attempts"].append(attempt)
        release_lock(sc, state, nonce)


def make_workdir(start, run_id, attempt_no):
    """<一時ディレクトリ>/review-loop/<owner>_<repo>/<PR番号>/<run_id>/<試行>/ を新しく作る。

    共有の一時ディレクトリ(TMPDIR のない Linux の /tmp)で他人に先回りされないよう、起点を
    自分だけが使えるディレクトリにする。試行のディレクトリが既にあれば、前の出力と混ざるので失敗にする。"""
    top = os.path.join(tempfile.gettempdir(), "review-loop")
    os.makedirs(top, mode=0o700, exist_ok=True)
    st = os.lstat(top)
    if stat.S_ISLNK(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise AttemptFailed("workdir_error", "", f"{top} が自分だけのディレクトリではない(所有者か権限を確かめてほしい)")
    path = os.path.join(top, start["repo"], str(start["number"]), run_id, str(attempt_no))
    try:
        os.makedirs(path)
    except FileExistsError:
        raise AttemptFailed("workdir_error", "", f"作業ディレクトリが既にある: {path}")
    return path


def classify(e):
    """例外を (失敗の種類, 詳細) にする。状態コメントへの記録と stderr への出力で同じ分類を使う。"""
    if isinstance(e, AttemptFailed):
        return e.reason, e.detail
    if isinstance(e, Interrupted):
        return f"interrupted: {e}", f"シグナル {e} で止められた"
    if isinstance(e, Precondition):  # 前提チェックの失敗、または試行中の git や gh の失敗
        return "command_error", str(e)
    return "internal_error", "".join(traceback.format_exception(type(e), e, e.__traceback__))


def on_signal(signum, _frame):
    raise Interrupted(signal.Signals(signum).name)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "_watch":
        sep = sys.argv.index("--")
        return watch_main(int(sys.argv[2]), float(sys.argv[3]), sys.argv[sep + 1:])

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    it = sub.add_parser("iterate", help="レビューを1反復だけ実行する")
    it.add_argument("worktree", help="PR のブランチをチェックアウトした worktree の絶対パス")
    it.add_argument("--new-run", action="store_true", help="新しいシリーズを始める(利用者の指示があったときだけ使う)")
    args = ap.parse_args()

    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(s, on_signal)
    ctx = {"workdir": "", "attempt": None}
    code = 0
    try:
        verdict = iterate(args.worktree, args.new_run, ctx)
        print(json.dumps(verdict, ensure_ascii=False, indent=2), flush=True)
        log(f"完了: 反復 {ctx['attempt']['iter']}、費用 ${ctx['attempt']['cost_usd']:.2f}")
    except BaseException as e:
        ignore_signals()
        kind, detail = classify(e)
        if ctx["attempt"] is not None:  # 試行を始めていれば、状態コメントに記録済み
            log(f"failed: {kind}\n{detail}".rstrip())
            code = 1
        else:
            log(f"error: {detail}" + ("(試行の開始前。記録していない)" if isinstance(e, Interrupted) else ""))
            code = 2
    log(ctx["workdir"])
    return code


if __name__ == "__main__":
    sys.exit(main())

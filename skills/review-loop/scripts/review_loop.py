#!/usr/bin/env python3
"""PR のレビューループを1反復だけ進める。

    review_loop.py iterate <worktree の絶対パス> [--new-run]

観点別のレビュースキルを `claude -p` で並列に実行し、判定役の `claude -p` に突き合わせと
競合の裁定をさせ、判定 JSON を標準出力に出す。コードは修正しない。ループの状態は PR の
コメント1つ(マーカー付き)に記録する。

終了コード:
  0  成功。標準出力は判定 JSON だけ
  1  試行が失敗した。状態コメントに記録済み
  2  試行を始めなかった(前提を満たさない、ロックを取れない、上限に達した、開始前に中断された)。試行は記録しない
     (ただし、残っていた古いロックを interrupted として片付けた記録は残る)
0 と 1 でも、状態コメントへの書き込みに失敗したときは記録されていない(stderr にそう出る)。
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
# 引数の {pr} は PR 番号に置き換わる。引数の意味はスキルごとに違うので、
# PR 番号を自動では足さない。
# - 組み込みの code-review は、レベルを指定しないと利用者が最後に使ったレベルを引き継ぎ、反復ごとに
#   深さが変わりうるので固定する
# - mattpocock-skills:code-review は、引数を比較の起点(commit や branch)として読む。数字だけを渡すと
#   起点として解決できず推測に頼るので、「PR #番号」と書く。スキルが PR からベースを起点に決め(ローカルの
#   main か origin/main になる)、PR 本文を仕様として使う
PERSPECTIVES = [
    "code-review high {pr}",
    "security-review",
    "mattpocock-skills:code-review PR #{pr}",
]

SAFETY_MAX_ITER = 10          # シリーズあたりの反復の上限
MAX_CONSECUTIVE_FAILURES = 3  # 連続失敗の上限

PREFLIGHT_TIMEOUT = 2 * 60    # 事前確認(init を受け取るまで)
REVIEW_TIMEOUT = 40 * 60      # レビュー役1つあたり
JUDGE_TIMEOUT = 20 * 60       # 判定役
MARGIN = 5 * 60               # Bash の制限時間に対する余裕(事前確認の後の gh の呼び出しなど)
LOCK_MARGIN = 15 * 60         # ロックを持ったまま行う git・gh の呼び出し(各 COMMAND_TIMEOUT まで)の余裕
BASH_TIMEOUT = 90 * 60        # SKILL.md で Bash ツールに指定する制限時間
BASH_TIMEOUT_MAX = 120 * 60   # Bash ツールの最大制限時間
STALE_LOCK_AFTER = REVIEW_TIMEOUT + JUDGE_TIMEOUT + LOCK_MARGIN
WATCHDOG_GRACE = 60           # 子の見張り役が、親のタイムアウトに加えて待つ時間
LOCK_SETTLE_SECONDS = 3       # nonce を書いてから読み直すまで
POLL_SECONDS = 2
COMMAND_TIMEOUT = 60          # git や gh の1回の呼び出し

MARKER = "review-loop-state"
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}$")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
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
    """git や gh を実行する。後片付け中はシグナルを無視しているので、止まっても抜けられるよう制限時間を付ける。"""
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


def new_tokens():
    return {"input": 0, "cache_read": 0, "output": 0}


def add_tokens(tokens, data):
    """子の使ったトークン数を足す。usage はサブエージェントの分を含まず、空のこともあるので、モデルごとの
    累計である modelUsage を使う。input はキャッシュの書き込みと読み込みを含む入力の全体。"""
    for m in (data.get("modelUsage") or {}).values():
        tokens["input"] += (m.get("inputTokens", 0) + m.get("cacheCreationInputTokens", 0)
                            + m.get("cacheReadInputTokens", 0))
        tokens["cache_read"] += m.get("cacheReadInputTokens", 0)
        tokens["output"] += m.get("outputTokens", 0)


def check_result(label, rc, base, attempt, structured=False):
    """子の結果を読んでトークン数を attempt に足し、成功の条件を全て満たすか確かめる。結果の JSON を返す。"""
    try:
        with open(base + ".stdout.json", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        with open(base + ".stderr.txt", encoding="utf-8", errors="replace") as f:
            err = f.read().strip()[-1000:]
        raise AttemptFailed("child_error", label, f"結果の JSON を読めない(終了コード {rc})。stderr: {err}{sandbox_hint(err)}")
    add_tokens(attempt["tokens"], data)
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


def expand(spec, pr):
    return spec.replace("{pr}", str(pr["number"]))


def check_tools():
    if sys.version_info < (3, 9):
        raise Precondition("Python 3.9 以降が必要")
    missing = [c for c in ("git", "gh", "claude") if shutil.which(c) is None]
    if missing:
        raise Precondition(f"コマンドが見つからない: {', '.join(missing)}")
    if PREFLIGHT_TIMEOUT + REVIEW_TIMEOUT + JUDGE_TIMEOUT + MARGIN > BASH_TIMEOUT or BASH_TIMEOUT > BASH_TIMEOUT_MAX:
        raise Precondition("タイムアウトの合計が Bash ツールの制限時間を超えている(スクリプト冒頭の設定を見直す)")
    names = [safe_name(skill_name(s)) for s in PERSPECTIVES]
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
    r = run(["gh", "pr", "view", "--json", "number,headRefOid,state,author,url"], cwd=wt, check=False)
    if r.returncode != 0:
        raise Precondition(f"このブランチの PR を取得できない: {r.stderr.strip()}")
    return json.loads(r.stdout)


def pr_view_retrying(wt, attempts=3, wait=5):
    """pr_view を、一時的な失敗に備えて数回試す。長い試行の最後の確認で、判定を捨てないようにする。"""
    for i in range(attempts):
        try:
            return pr_view(wt)
        except Precondition:
            if i == attempts - 1:
                raise
            time.sleep(wait)


def local_refs(wt):
    """(HEAD の SHA, ブランチ名) を返す。detached HEAD ならブランチ名は空。"""
    return (run(["git", "rev-parse", "HEAD"], cwd=wt).stdout.strip(),
            run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=wt, check=False).stdout.strip())


def snapshot(wt):
    """HEAD の SHA、ブランチ名、PR の head などを返す。混入の検出に使う。"""
    pr = pr_view(wt)
    m = re.match(r"https?://[^/]+/([^/]+)/([^/]+)/pull/", pr.get("url") or "")
    head, branch = local_refs(wt)
    return {
        "number": pr["number"],
        "repo": f"{m.group(1)}_{m.group(2)}" if m else "unknown",
        "state": pr.get("state"),
        "author": (pr.get("author") or {}).get("login"),
        "head": head,
        "branch": branch,
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
def valid_tokens(t):
    return t is None or (isinstance(t, dict) and set(t) == set(new_tokens())
                         and all(isinstance(v, int) for v in t.values()))


def valid_sha(v):
    return v is None or bool(SHA_RE.match(v))


def valid_state(s):
    """状態コメントの JSON が、このスクリプトの書いた形をしているか(render と acquire_lock が読むものを全て)。"""
    try:
        lock, prev = s["lock"], s.get("previous_run")
        if lock["running"]:
            parse_iso(lock["started_at"])
        return (bool(RUN_ID_RE.match(s["run_id"]))
                and isinstance(s["iter"], int) and isinstance(s["consecutive_failures"], int)
                and isinstance(lock["running"], bool) and valid_sha(lock.get("sha"))
                and all(isinstance(a["result"], str) and isinstance(a["at"], str)
                        and valid_sha(a.get("sha")) and isinstance(a.get("reason") or "", str)
                        and valid_tokens(a.get("tokens"))
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


def format_count(n):
    """トークン数を 1.2万 のように短く書く。"""
    return f"{n / 10000:.1f}万" if n >= 10000 else str(n)


def format_tokens(t):
    """(入力, 出力) の表記を返す。入力にはキャッシュ読み込みの内訳を添える。"""
    return (f"{format_count(t['input'])}(うちキャッシュ読み込み {format_count(t['cache_read'])})",
            format_count(t["output"]))


def total_tokens(attempts):
    total = new_tokens()
    for a in attempts:
        for k, v in (a.get("tokens") or {}).items():
            total[k] += v
    return total


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
        used = "、入力 {}・出力 {} トークン".format(*format_tokens(prev["tokens"])) if prev.get("tokens") else ""
        lines += [f"直前のシリーズ: run {prev['run_id']}(反復 {prev['iterations']}{used})", ""]
    if state["attempts"]:
        lines += ["| SHA | 時刻 | 結果 | 入力トークン | 出力トークン |", "|---|---|---|---|---|"]
        for a in state["attempts"]:
            result = a["result"] + (f"(反復 {a['iter']})" if a.get("iter") else "")
            if a.get("reason"):
                result += f": {a['reason'][:100]}"
            tin, tout = format_tokens(a["tokens"]) if a.get("tokens") else ("—", "—")
            lines.append(f"| {cell((a['sha'] or '')[:7])} | {cell(a['at'])} | {cell(result)} | {tin} | {tout} |")
        tin, tout = format_tokens(total_tokens(state["attempts"]))
        lines.append(f"| **合計** | | | {tin} | {tout} |")
        lines += ["", "失敗した試行のトークン数は、途中で止めた子の分を含まない(下限)。", ""]
    lines.append("<sub>review-loop のスクリプトが更新するコメント。手で編集しても上書きされる。</sub>")
    return "\n".join(lines)


def acquire_lock(sc, head, new_run):
    """ロックを取り、状態と nonce を返す。

    誤って二重に起動したことを検出するためのもので、厳密な排他制御ではない。ループを駆動する親は
    1つだけなので、gh の書き込みが遅れて両方が通る程度の取りこぼしは許容する。"""
    state = sc.read()
    if sc.unreadable:
        if not new_run:
            raise Precondition(f"状態コメント {sc.id} を読めない(手で編集された可能性がある)。反復回数と連続失敗の"
                               "上限を黙って外さないよう、ここで止める。利用者の指示があれば --new-run で始め直す")
        log(f"warn: 状態コメント {sc.id} を読めないので、新しいシリーズとして上書きする")
    if state is not None and state["lock"]["running"]:
        age = (now() - parse_iso(state["lock"]["started_at"])).total_seconds()
        if age < STALE_LOCK_AFTER:
            raise Precondition(f"別の試行が実行中(開始 {state['lock']['started_at']})。二重起動の可能性がある")
        log(f"warn: 古いロックが残っていた(開始 {state['lock']['started_at']})。前回の試行を interrupted として記録する")
        state["attempts"].append({"sha": state["lock"].get("sha"), "at": state["lock"]["started_at"],
                                  "result": "interrupted", "reason": "stale_lock", "tokens": new_tokens()})
        state["consecutive_failures"] += 1
    if state is None:
        state = new_state()
    elif new_run:
        state = new_state({"run_id": state["run_id"], "iterations": state["iter"],
                           "tokens": total_tokens(state["attempts"])})
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


# --- レビュー役と判定役 ------------------------------------------------------
def safe_name(s):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", s)


def run_reviews(wt, env, pr, workdir, children, attempt):
    """観点別レビューを並列に実行し、{観点: result} を返す。1つでも失敗したら残りを止める。"""
    running = {}
    for spec in PERSPECTIVES:
        base = os.path.join(workdir, f"review-{safe_name(skill_name(spec))}")
        prompt = "/" + expand(spec, pr)
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
- 観点の出力がレビューになっていない(セットアップの案内や利用者への質問で終わっている、対象を取り違えているなど)ときは、その観点が欠けたことを category が other の指摘として findings に載せ、behavior_change を true にする
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


def find_contamination(wt, start):
    """子が作業ツリーやブランチを変えていないか、PR の head が試行中に動いていないかを確かめる。
    問題があれば (種類, 詳細) を、なければ None を返す。"""
    problems = []
    status = git_status(wt)
    if status.strip():
        problems.append("作業ツリーがクリーンでない:\n" + status.rstrip())
    # ブランチが切り替わっていると gh pr view が失敗するので、git で分かるものを先に見る
    head, branch = local_refs(wt)
    for label, before, after in (("HEAD", start["head"], head), ("ブランチ", start["branch"], branch)):
        if before != after:
            problems.append(f"{label} が変わった: {before} → {after}")
    if problems:
        return "contamination", "\n".join(problems) + "\n(変更は元に戻していない)"
    pr_head = pr_view_retrying(wt)["headRefOid"]
    if pr_head != start["pr_head"]:
        # 外からの push と、子がローカルを変えずに直接 push したものは区別できない
        return "head_changed", (f"試行中に PR の head が変わった: {start['pr_head']} → {pr_head}。"
                                "自分で push したのでなければ、子が禁じられた push をした可能性がある。"
                                "取り込む前に、新しいコミットの作者と内容を確かめる")
    return None


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
    attempt = state = nonce = None
    try:  # ロックを取ったら、どこで終わっても解除する
        state, nonce = acquire_lock(sc, start["head"], new_run)
        if state["iter"] >= SAFETY_MAX_ITER:
            raise Precondition(f"反復が安全上限({SAFETY_MAX_ITER} 回)に達した")
        if state["consecutive_failures"] >= MAX_CONSECUTIVE_FAILURES:
            raise Precondition(f"連続失敗が {MAX_CONSECUTIVE_FAILURES} 回に達した。原因を取り除いてから、利用者の指示で --new-run する")

        attempt = {"sha": start["head"], "at": state["lock"]["started_at"], "result": "failed", "tokens": new_tokens()}
        ctx["attempt"] = attempt
        ctx["workdir"] = make_workdir(start, state["run_id"], len(state["attempts"]) + 1)
        log(f"作業ディレクトリ: {ctx['workdir']}")
        reviews = run_reviews(wt, env, start, ctx["workdir"], children, attempt)
        verdict = run_judge(wt, env, start["number"], reviews, ctx["workdir"], children, attempt)
        children.kill_all()
        found = find_contamination(wt, start)
        if found:
            raise AttemptFailed(found[0], "", found[1])
        with open(os.path.join(ctx["workdir"], "verdict.json"), "w", encoding="utf-8") as f:
            json.dump(verdict, f, ensure_ascii=False, indent=2)
        ignore_signals()  # ここから先は成功の記録だけなので、中断させない
        state["iter"] += 1
        state["consecutive_failures"] = 0
        attempt.update(result="completed", iter=state["iter"])
        return verdict
    except BaseException as e:
        ignore_signals()
        if attempt is None:
            raise
        kind, detail = classify(e)
        # 失敗した試行でも、子が作業ツリーやブランチを変えていないかを確かめる。変えていれば、そちらを優先して
        # 報告する(放っておくと、親が子の変更を自分の修正としてコミットしかねない)
        children.kill_all()
        if not (isinstance(e, AttemptFailed) and e.kind in ("contamination", "head_changed")):
            try:
                found = find_contamination(wt, start)
            except Exception:
                found = None
            if found:
                e = AttemptFailed(found[0], "", f"{found[1]}\n\n(この試行はもともと {kind} で失敗した: {detail.strip()})")
                kind, detail = classify(e)
        attempt["reason"] = kind
        state["consecutive_failures"] += 1
        if ctx["workdir"]:  # 作業ディレクトリを作る前の失敗(workdir_error)では残さない
            try:
                with open(os.path.join(ctx["workdir"], "failure.txt"), "w", encoding="utf-8") as f:
                    f.write(f"{kind}\n{detail}\n")
            except OSError:  # 詳細を残せなくても、記録と報告は続ける
                pass
        raise e
    finally:
        ignore_signals()
        children.kill_all()
        if attempt is not None:
            state["attempts"].append(attempt)
        if nonce is not None and not release_lock(sc, state, nonce) and attempt is not None:
            log("warn: この試行の結果を状態コメントに記録できなかった"
                + ("(反復回数が進んでいない)" if attempt["result"] == "completed" else "(連続失敗にも数えられていない)")
                + f"。ロックが残っていれば、{STALE_LOCK_AFTER // 60}分たつまで次の起動は「別の試行が実行中」で止まる")


def make_workdir(start, run_id, attempt_no):
    """<一時ディレクトリ>/review-loop/<owner>_<repo>/<PR番号>/<run_id>/<試行>/ を新しく作る。

    共有の一時ディレクトリ(TMPDIR のない Linux の /tmp)で他人に先回りされたり、レビューの出力を
    読まれたりしないよう、起点は自分が所有するディレクトリに限り、権限を 0700 に絞って使う。
    試行のディレクトリが既にあれば、前の出力と混ざるので失敗にする。"""
    top = os.path.join(tempfile.gettempdir(), "review-loop")
    path = os.path.join(top, start["repo"], str(start["number"]), run_id, str(attempt_no))
    try:
        os.makedirs(top, mode=0o700, exist_ok=True)
        st = os.lstat(top)
        if stat.S_ISLNK(st.st_mode) or st.st_uid != os.getuid():
            raise AttemptFailed("workdir_error", "", f"{top} が自分の所有するディレクトリではない")
        if st.st_mode & 0o077:  # umask などで広い権限で作られていたら絞る
            os.chmod(top, 0o700)
        os.makedirs(path)
    except FileExistsError:
        raise AttemptFailed("workdir_error", "", f"作業ディレクトリが既にある: {path}")
    except OSError as e:
        raise AttemptFailed("workdir_error", "", f"作業ディレクトリを作れない: {e}")
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
        log("完了: 反復 {}、入力 {}、出力 {} トークン".format(ctx["attempt"]["iter"], *format_tokens(ctx["attempt"]["tokens"])))
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

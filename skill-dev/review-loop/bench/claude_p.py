#!/usr/bin/env python3
"""bench が子を `claude -p` で起動し、stream を読むための部品。

本番の `skills/review-loop/scripts/review_loop.py` が、レビュー役を `claude -p` で起動していた版から、bench.py と
score.py が使うもの(Children、StreamTail、child_env など)と、それが参照するものだけを写した。中身は変えていない。
本番は、親が観点スキルを直接呼ぶ形に変えたので、この起動の仕組みは bench だけが使う(モデルを固定して、
構成どうしを比べるため)。

子は見張り役を介して起動する(Children)。見張り役は、このファイルを `_watch` 付きで実行したもの。
"""
import json
import os
import signal
import subprocess
import sys
import time

REVIEW_TIMEOUT = 40 * 60      # レビュー役1つあたり
WATCHDOG_GRACE = 60           # 子の見張り役が、親のタイムアウトに加えて待つ時間
STRIP_ENV = ("CLAUDE_JOB_DIR", "CLAUDE_CODE_SESSION_KIND", "CLAUDE_CODE_SESSION_ID")
GUARD_ENV = "REVIEW_LOOP_ACTIVE"
NO_MUTATION = "ファイルの編集、checkout、commit、stash、pushなど、作業ツリーやブランチを変える操作をしないでください。"
# システムプロンプトはサブエージェントに引き継がれないので、任せるときは依頼文に含めるよう頼む
DELEGATE_CONSTRAINT = "サブエージェントやサブタスクに作業を任せるときは、この制約をその依頼文にも含めてください。"
REVIEW_CONSTRAINT = "他のレビューと並列に、同じworktreeで実行しています。" + NO_MUTATION + DELEGATE_CONSTRAINT


class AttemptFailed(Exception):
    """試行の失敗。kind と対象(どの子か)だけを状態コメントに載せ、detail は stderr と作業ディレクトリに残す。"""

    def __init__(self, kind, target="", detail=""):
        super().__init__(f"{kind}: {target}".rstrip(": "))
        self.kind, self.target, self.detail = kind, target, detail

    @property
    def reason(self):
        return str(self)


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


# 試行を止めない拒否の decision_reason_type。複合コマンド(`;`・`&&`・パイプなど)を、サブコマンドごとの
# 判定から拒否したもの。読み取りの一部が利用者の deny ルール(`Read(**/.env*)` など)に当たるといった形で
# 普通に起き、子は該当部分を外してやり直せる。この値からは、拒否されたのが一部か全部か、deny ルールに
# 当たったのか許可ルールに無かったのかは見分けられない。auto mode の分類器の判定(classifier)や安全確認
# (safetyCheck)のように、子が読めないまま進みうるものは含めない。項目名と値は、本物の claude(2.1.325)が
# stream に出す permission_denied のイベントに合わせてある
TOLERATED_DENIAL = "subcommandResults"


def tolerated(event):
    """試行を止めない拒否のイベントか。tool_use_id がないものは、result の permission_denials と
    突き合わせられないので止める側に倒す。"""
    return event.get("decision_reason_type") == TOLERATED_DENIAL and bool(event.get("tool_use_id"))


class StreamTail:
    """子が書き出している stream-json のファイルを、書き終わった行だけ少しずつ読み、成否の判断に使うものだけを覚える。

    - results: 最上位(parent_tool_use_id がない)の result の行を、出た順に全て
    - blocking: 試行を止める権限の拒否のイベント(system の permission_denied)。止めない拒否(tolerated)は
      tolerated_ids に覚え、まだ記録していないものを take_tolerated で渡す。サブエージェントの中での拒否も、
      同じイベントとして stream に出る
    - 拒否されたツールの入力はイベントにないので、tool_use の行から引けるよう、ツール呼び出しの入力を
      id ごとに覚えておく"""

    def __init__(self, path):
        self.path, self.offset = path, 0
        self.results = []
        self.blocking = []
        self.tolerated_ids = set()
        self.unrecorded = []
        self.tool_inputs = {}

    def poll(self):
        try:
            with open(self.path, "rb") as f:
                f.seek(self.offset)
                chunk = f.read()
        except OSError:
            return
        end = chunk.rfind(b"\n") + 1  # 書きかけの最後の行は次に回す
        self.offset += end
        for line in chunk[:end].splitlines():
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            kind = msg.get("type")
            if kind == "result":
                if not msg.get("parent_tool_use_id"):
                    self.results.append(msg)
            elif kind == "system" and msg.get("subtype") == "permission_denied":
                if tolerated(msg):
                    self.tolerated_ids.add(msg["tool_use_id"])
                    self.unrecorded.append(msg)
                else:
                    self.blocking.append(msg)
            elif kind == "assistant":
                for block in (msg.get("message") or {}).get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        self.tool_inputs[block.get("id")] = block.get("input", {})

    def texts(self):
        """最上位の result の行のうち、エラーでも空でもないもののテキストを、出た順に返す。"""
        return [t for t in (str(r.get("result") or "").strip() for r in self.results if not r.get("is_error")) if t]

    def denied_call(self, event):
        """拒否のイベントを、summarize_denials に渡せる形(ツール名と入力)にする。"""
        return {"tool_name": event.get("tool_name"), "tool_input": self.tool_inputs.get(event.get("tool_use_id"), {})}

    def blocking_denials(self):
        """試行を止める拒否を、summarize_denials に渡せる形で返す。イベントで出たものに加え、result の
        permission_denials にしか載っていないもの(出どころが分からない)も含める。"""
        out = [self.denied_call(e) for e in self.blocking]
        seen = self.tolerated_ids | {e.get("tool_use_id") for e in self.blocking if e.get("tool_use_id")}
        for r in self.results:  # permission_denials は result の行ごとに同じものが繰り返し載りうる
            for d in r.get("permission_denials") or []:
                # tool_use_id のないものは止める側に倒し、重複はツールと入力で見分ける
                key = d.get("tool_use_id") or json.dumps([d.get("tool_name"), d.get("tool_input")], sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    out.append(d)
        return out

    def take_tolerated(self):
        """まだ記録していない、止めない拒否の要約を返す。"""
        items, self.unrecorded = self.unrecorded, []
        return [summarize_denials([self.denied_call(e)]) + f"(decision_reason_type {e.get('decision_reason_type')})" for e in items]


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "_watch":
        sep = sys.argv.index("--")
        sys.exit(watch_main(int(sys.argv[2]), float(sys.argv[3]), sys.argv[sep + 1:]))
    sys.exit("このファイルは bench.py から取り込んで使う")

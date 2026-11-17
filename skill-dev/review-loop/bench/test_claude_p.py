#!/usr/bin/env python3
"""claude_p.py(bench が子を起動し、stream を読む部品)を、作り物の子で確かめる。claude は起動しない。

    python3 skill-dev/review-loop/bench/test_claude_p.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bench  # noqa: E402  bench.py と同じ取り込み方で読む

rl = bench.rl
fails = 0


def check(cond, label):
    global fails
    print(("ok    " if cond else "FAIL  ") + label)
    if not cond:
        fails += 1


def child(lines):
    """stream-json の行を出して終わる子のコマンドを返す。"""
    code = "".join(f"print({json.dumps(json.dumps(line, ensure_ascii=False))}, flush=True)\n" for line in lines)
    return [sys.executable, "-c", code]


def usage(n):
    return {"m": {"inputTokens": n, "outputTokens": n, "cacheReadInputTokens": n, "cacheCreationInputTokens": n}}


d = tempfile.mkdtemp(prefix="claude-p-test.")
out = os.path.join(d, "o.jsonl")
children = rl.Children()

# 子の起動と、stream の読み取り
lines = [{"type": "system", "subtype": "init"},
         {"type": "result", "subtype": "success", "is_error": False, "result": "途中経過", "modelUsage": usage(1)},
         {"type": "result", "subtype": "success", "is_error": False, "result": "", "modelUsage": usage(2)},
         {"type": "result", "subtype": "success", "is_error": False, "result": "指摘A", "modelUsage": usage(3)}]
with open(out, "w") as o:
    p = children.spawn(child(lines), 30, cwd=d, env=rl.child_env(), stdin=subprocess.DEVNULL, stdout=o, stderr=subprocess.DEVNULL)
tail = rl.StreamTail(out)
while p.poll() is None:
    tail.poll()
    time.sleep(0.1)
rc = p.poll()
children.finish(p)
tail.poll()
check(rc == 0 and tail.texts() == ["途中経過", "指摘A"], "子の result の行のうち、空でないものを出た順に読む")
tokens = rl.new_tokens()
rl.add_tokens(tokens, tail.results[-1])
check(tokens == {"input": 9, "cache_read": 3, "output": 3}, "トークン数は、最後の result の行の modelUsage から数える")
check(tail.blocking_denials() == [] and tail.take_tolerated() == [], "拒否が無ければ、止める拒否も止めない拒否も無い")

# 権限の拒否の振り分け
# 拒否のイベントにツールの入力は無いので、入力は tool_use の行から引かれる
lines = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "cat .env; ls"}},
                                                        {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "git push"}}]}},
         {"type": "system", "subtype": "permission_denied", "tool_name": "Bash", "tool_use_id": "t1", "decision_reason_type": "subcommandResults"},
         {"type": "system", "subtype": "permission_denied", "tool_name": "Bash", "tool_use_id": "t2", "decision_reason_type": "classifier"},
         {"type": "result", "subtype": "success", "is_error": False, "result": "指摘B", "modelUsage": usage(1),
          "permission_denials": [{"tool_name": "Bash", "tool_use_id": "t1", "tool_input": {"command": "cat .env; ls"}},
                                 {"tool_name": "Bash", "tool_use_id": "t2", "tool_input": {"command": "git push"}}]}]
with open(out, "w") as o:
    p = children.spawn(child(lines), 30, cwd=d, env=rl.child_env(), stdin=subprocess.DEVNULL, stdout=o, stderr=subprocess.DEVNULL)
p.wait()
children.finish(p)
tail = rl.StreamTail(out)
tail.poll()
blocking = [rl.summarize_denials([x]) for x in tail.blocking_denials()]
tolerated = tail.take_tolerated()
check(len(blocking) == 1 and "git push" in blocking[0], "分類器による拒否は、止める拒否に数える")
check(len(tolerated) == 1 and "cat .env" in json.dumps(tolerated, ensure_ascii=False),
      "複合コマンドのサブコマンドごとの判定による拒否は、止めない拒否に数える")

# 子の環境
os.environ["CLAUDE_JOB_DIR"] = "/should/be/stripped"
env = rl.child_env()
check("CLAUDE_JOB_DIR" not in env and env.get(rl.GUARD_ENV), "子の環境から親のセッションの変数を外し、再帰の目印を付ける")

# 子を止める
p = children.spawn([sys.executable, "-c", "import time; time.sleep(60)"], 30, cwd=d, env=rl.child_env(), stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
started = time.monotonic()
children.kill_all()
check(p.poll() is not None and time.monotonic() - started < 20, "kill_all が、動いている子を止める")

# 見張り役が、制限時間を過ぎた子を止める
saved = rl.WATCHDOG_GRACE
rl.WATCHDOG_GRACE = 0
p = children.spawn([sys.executable, "-c", "import time; time.sleep(60)"], 1, cwd=d, env=rl.child_env(), stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
rl.WATCHDOG_GRACE = saved
try:
    p.wait(20)
except subprocess.TimeoutExpired:
    pass
check(p.poll() is not None, "見張り役が、制限時間を過ぎた子を止める")
children.kill_all()

shutil.rmtree(d, ignore_errors=True)
print("\n失敗 %d 件" % fails if fails else "\n全て成功")
sys.exit(1 if fails else 0)

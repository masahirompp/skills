#!/usr/bin/env python3
"""review-loop の review_loop.py を、偽の claude と gh で検証する。GitHub にも API にも触れない。

    python3 skill-dev/review-loop/test.py         # 実行して後片付けする
    KEEP=1 python3 skill-dev/review-loop/test.py  # 作業ディレクトリを残す
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, "../../skills/review-loop/scripts"))
FAKES = os.path.join(HERE, "fakes")

# 待ち時間を縮めて、本物のスクリプトを読み込んで実行する
RUNNER = """
import json, os, sys
sys.path.insert(0, sys.argv[1])
import review_loop as r
r.PERSPECTIVES = ["code-review high", "security-review", "mattpocock-skills:code-review"]
r.LOCK_SETTLE_SECONDS = 0
r.POLL_SECONDS = 0.1
for k, v in json.loads(os.environ.get("OVERRIDES", "{}")).items():
    setattr(r, k, v)
sys.argv = ["review_loop.py"] + sys.argv[2:]
sys.exit(r.main())
"""

root = os.path.realpath(tempfile.mkdtemp(prefix="review-loop-test."))
fails = 0


def check(cond, label):
    global fails
    print(("ok    " if cond else "FAIL  ") + label)
    if not cond:
        fails += 1


def sh(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def setup():
    """origin(bare)と PR のブランチをチェックアウトした worktree を作る。"""
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(os.path.join(root, "fake"))
    sh("git", "init", "-q", "--bare", "-b", "main", os.path.join(root, "origin.git"))
    wt = os.path.join(root, "wt")
    sh("git", "clone", "-q", os.path.join(root, "origin.git"), wt)
    for k, v in (("user.name", "t"), ("user.email", "t@example.com")):
        sh("git", "config", k, v, cwd=wt)
    with open(os.path.join(wt, ".gitignore"), "w") as f:
        f.write("*.log\n")
    with open(os.path.join(wt, "a.txt"), "w") as f:
        f.write("a\n")
    sh("git", "add", "-A", cwd=wt)
    sh("git", "commit", "-qm", "init", cwd=wt)
    sh("git", "switch", "-qc", "feature", cwd=wt)
    sh("git", "push", "-q", "origin", "main", "feature", cwd=wt)
    return wt


def env_for(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("FAKE_", "REVIEW_LOOP"))}
    env.update(PATH=FAKES + os.pathsep + env["PATH"], FAKE_DIR=os.path.join(root, "fake"),
               CLAUDE_JOB_DIR="/should/be/stripped", CLAUDE_CODE_SESSION_ID="parent", TMPDIR=root)
    env.update(extra)
    return env


def run(wt, *flags, overrides=None, **extra):
    env = env_for(OVERRIDES=json.dumps(overrides or {}), **extra)
    p = subprocess.run([sys.executable, "-c", RUNNER, SCRIPTS, "iterate", wt, *flags],
                       env=env, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def comments():
    try:
        with open(os.path.join(root, "fake", "comments.json")) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def state():
    cs = [c for c in comments() if c["login"] == "me"]
    if not cs:
        return None
    body = cs[0]["body"]
    raw = body.split("<!-- review-loop-state ", 1)[1].split(" -->", 1)[0]
    return json.loads(raw)


def calls():
    try:
        with open(os.path.join(root, "fake", "calls.jsonl")) as f:
            return [json.loads(line) for line in f]
    except FileNotFoundError:
        return []


def write_state(s):
    body = "<!-- review-loop-state " + json.dumps(s) + " -->\nx"
    with open(os.path.join(root, "fake", "comments.json"), "w") as f:
        json.dump([{"id": 500, "login": "me", "created_at": "2026-01-01T00:00:00Z", "body": body, "edits": 0}], f)


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def commit_and_push(wt, name):
    with open(os.path.join(wt, name), "w") as f:
        f.write(name)
    sh("git", "add", "-A", cwd=wt)
    sh("git", "commit", "-qm", name, cwd=wt)
    sh("git", "push", "-q", "origin", "feature", cwd=wt)


# --- 成功 --------------------------------------------------------------------
wt = setup()
rc, out, err = run(wt)
check(rc == 0, f"成功すると終了コード0({rc}) {err[-300:] if rc else ''}")
verdict = json.loads(out) if rc == 0 else {}
check(verdict.get("recommendation", {}).get("continue") is True, "標準出力は判定 JSON だけ")
s = state()
check(s and s["iter"] == 1 and s["attempts"][0]["result"] == "completed", "状態コメントに反復1が記録される")
check(s and s["lock"]["running"] is False, "ロックが解除される")
check(s and abs(s["attempts"][0]["cost_usd"] - 2.0) < 1e-9, "費用はレビュー役3つと判定役の合計")
workdir = err.rstrip().splitlines()[-1]
check(os.path.isfile(os.path.join(workdir, "verdict.json")), "stderr の最後の行は作業ディレクトリ")
check(workdir.startswith(os.path.join(root, "review-loop", "o_r", "7")), "作業ディレクトリは <tmp>/review-loop/<リポジトリ>/<PR>/<run>/<試行>")
cs = calls()
reviews = [c for c in cs if c["kind"] == "review"]
check(len(reviews) == 3, "観点ごとに1プロセス起動する")
check(all(not c["env_job_dir"] and not c["env_session_id"] for c in cs), "子の環境から CLAUDE_JOB_DIR などを外す")
check(all(c["guard"] == "1" for c in cs), "子には REVIEW_LOOP_ACTIVE が渡る")
check(not any(c["kind"] == "preflight-not-killed" for c in cs), "事前確認の子は init の直後に止める")
judge = [c for c in cs if c["kind"] == "judge"]
check(judge and "===== 観点: security-review =====" in judge[0]["stdin"], "判定役には各レビューを区切って stdin で渡す")
check(judge and '"enum"' in judge[0]["args"][judge[0]["args"].index("--json-schema") + 1],
      "--json-schema にはスキーマの中身を渡す")
check(all("--append-system-prompt" in c["args"] for c in reviews + judge), "運用上の制約を渡す")
check(any(c["args"][-1] == "/code-review high 7" for c in reviews), "レビュー役のプロンプトは /<観点と引数> <PR番号>")

# 2回目: 同じコメントを編集で更新する
rc, out, err = run(wt)
check(rc == 0 and state()["iter"] == 2, "同じ SHA で再実行できる")
check(len(comments()) == 1 and comments()[0]["edits"] >= 2, "新しいコメントを作らず編集で更新する")

# --- 前提チェック(状態に記録しない) ------------------------------------------
before = json.dumps(state())
with open(os.path.join(wt, "untracked.txt"), "w") as f:
    f.write("x")
rc, _, err = run(wt)
check(rc == 2 and "クリーンでない" in err, "作業ツリーが汚れていれば終了コード2")
os.remove(os.path.join(wt, "untracked.txt"))
with open(os.path.join(wt, "x.log"), "w") as f:
    f.write("ignored")

sh("git", "commit", "-q", "--allow-empty", "-m", "local", cwd=wt)
rc, _, err = run(wt)
check(rc == 2 and "push" in err, "push していなければ終了コード2")
sh("git", "push", "-q", "origin", "feature", cwd=wt)

rc, _, err = run(wt, FAKE_NO_PR="1")
check(rc == 2 and "PR を取得できない" in err, "PR がなければ終了コード2")
rc, _, err = run(wt, FAKE_SKILLS="code-review")
check(rc == 2 and "mattpocock-skills:code-review" in err, "事前確認で観点スキルの欠落を検出する")
rc, _, err = run(wt, REVIEW_LOOP_ACTIVE="1")
check(rc == 2 and "再帰" in err, "再帰ガード")
rc, _, err = run("relative/path")
check(rc == 2 and "絶対パス" in err, "worktree は絶対パスで指定する")
os.makedirs(os.path.join(wt, "sub"))
rc, _, err = run(os.path.join(wt, "sub"))
check(rc == 2 and "トップではない" in err, "worktree のトップ以外は拒否する")
check(json.dumps(state()) == before, "前提チェックの失敗は状態に記録しない")

# --- 試行の失敗 --------------------------------------------------------------
t = time.time()
rc, _, err = run(wt, FAKE_REVIEW_code_review="deny", FAKE_REVIEW_security_review="hang")
s = state()
check(rc == 1 and "permission_denied" in err and "gh pr diff 7" in err, "権限の拒否は失敗にし、内容を出す")
check(time.time() - t < 30, "1つ失敗したら残りをすぐ止める")
hung = [c for c in calls() if c["kind"] == "review" and c["name"] == "security-review"][-1]
check(not alive(hung["pid"]), "止めた子のプロセスが残らない")
check(s["consecutive_failures"] == 1 and s["attempts"][-1]["result"] == "failed", "失敗を記録し連続失敗を数える")
check(s["iter"] == 2 and s["lock"]["running"] is False, "失敗しても反復は進まず、ロックは解除される")
check(err.rstrip().splitlines()[-1].endswith("/3"), "失敗しても stderr の最後の行は作業ディレクトリ")

rc, _, err = run(wt, FAKE_REVIEW_security_review="dirty")
check(rc == 1 and "contamination" in err and "stray.txt" in err, "子が作業ツリーを変えたら失敗にする")
check(os.path.exists(os.path.join(wt, "stray.txt")), "混入した変更は元に戻さない")
os.remove(os.path.join(wt, "stray.txt"))
check(state()["consecutive_failures"] == 2, "連続失敗が積み上がる")

rc, _, err = run(wt, FAKE_REVIEW_code_review="empty")
check(rc == 1 and "result が空" in err, "result が空なら失敗")
rc, _, err = run(wt)
check(rc == 2 and "連続失敗" in err, "連続失敗3回で止まる")

rc, _, err = run(wt, "--new-run")
s = state()
check(rc == 0 and s["iter"] == 1 and s["previous_run"]["iterations"] == 2 and len(s["attempts"]) == 1,
      "--new-run で直前のシリーズを要約して始め直す")

rc, _, err = run(wt, FAKE_JUDGE="noso")
check(rc == 1 and "structured_output" in err, "判定役に structured_output がなければ失敗")
rc, _, err = run(wt, FAKE_JUDGE="retries")
check(rc == 1 and "error_max_structured_output_retries" in err, "構造化出力の再試行が尽きたら失敗")
rc, _, err = run(wt, FAKE_REVIEW_code_review="fail")
check(rc == 1 and "boom" in err, "子が異常終了したら stderr を添えて失敗")

rc, _, err = run(wt, "--new-run", FAKE_REVIEW_mattpocock_skills_code_review="hang", overrides={"REVIEW_TIMEOUT": 1})
hung = [c for c in calls() if c["kind"] == "review" and c["name"] == "mattpocock-skills:code-review"][-1]
check(rc == 1 and "timeout" in err and not alive(hung["pid"]), "タイムアウトした子はグループごと止める")

# SIGTERM で止められてもロックを解除し、子を止める
env = env_for(OVERRIDES="{}", FAKE_REVIEW_code_review="hang")
p = subprocess.Popen([sys.executable, "-c", RUNNER, SCRIPTS, "iterate", wt], env=env,
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
deadline = time.time() + 20
while time.time() < deadline and not (state() or {}).get("lock", {}).get("running"):
    time.sleep(0.2)
time.sleep(1)
p.send_signal(signal.SIGTERM)
_, err = p.communicate(timeout=30)
s = state()
hung = [c for c in calls() if c["kind"] == "review" and c["name"] == "code-review"][-1]
check(p.returncode == 1 and s["lock"]["running"] is False and "interrupted" in s["attempts"][-1]["reason"],
      "SIGTERM でも失敗として記録し、ロックを解除する")
check(not alive(hung["pid"]), "SIGTERM で子も止める")

# --- ロック ------------------------------------------------------------------
s = state()
s["lock"] = {"running": True, "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sha": "abc", "nonce": "n"}
write_state(s)
rc, _, err = run(wt)
check(rc == 2 and "実行中" in err and state()["lock"]["nonce"] == "n", "実行中のロックがあれば撤退する")

s["lock"]["started_at"] = "2026-01-01T00:00:00Z"
s["consecutive_failures"] = 0
write_state(s)
n = len(s["attempts"])
rc, _, err = run(wt)
s = state()
check(rc == 0 and s["attempts"][n]["result"] == "interrupted" and s["attempts"][n]["sha"] == "abc",
      "古いロックは interrupted として記録してから取得する")

# --- 後片付けと中断 ----------------------------------------------------------
rc, _, err = run(wt, FAKE_REVIEW_security_review="bg")
g = [c for c in calls() if c["kind"] == "grandchild"][-1]["grandchild"]
time.sleep(0.5)
check(rc == 0 and not alive(g), "正常終了した子がグループに残した孫も止める")

t = time.time()
rc, _, err = run(wt, FAKE_REVIEW_code_review="slow", FAKE_REVIEW_security_review="slow",
                 FAKE_REVIEW_mattpocock_skills_code_review="slow")
check(rc == 0 and time.time() - t < 8, f"レビュー役は並列に動く({time.time() - t:.1f} 秒)")

# スクリプトが SIGKILL されても、見張り役が子を止める
env = env_for(OVERRIDES="{}", FAKE_REVIEW_code_review="hang")
p = subprocess.Popen([sys.executable, "-c", RUNNER, SCRIPTS, "iterate", wt], env=env,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
deadline = time.time() + 20
while time.time() < deadline and not any(c["kind"] == "review" and c["name"] == "code-review" and c["pid"] != hung["pid"]
                                         for c in calls()):
    time.sleep(0.2)
hung = [c for c in calls() if c["kind"] == "review" and c["name"] == "code-review"][-1]
p.kill()
p.wait()
time.sleep(3)
check(not alive(hung["pid"]), "スクリプトが SIGKILL されても子は止まる")
s = state()
s["lock"]["started_at"] = "2026-01-01T00:00:00Z"  # 古いロックとして片付けさせる
s["consecutive_failures"] = 0
write_state(s)
rc, _, _ = run(wt)
check(rc == 0, "SIGKILL 後に残ったロックは次回の起動で片付く")

# 試行の開始前(事前確認中)に止められたら、何も記録せず終了コード2
before = json.dumps(state())
env = env_for(OVERRIDES="{}", FAKE_PREFLIGHT_DELAY="30")
p = subprocess.Popen([sys.executable, "-c", RUNNER, SCRIPTS, "iterate", wt], env=env,
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(3)
p.send_signal(signal.SIGTERM)
_, err = p.communicate(timeout=30)
check(p.returncode == 2 and "開始前" in err and json.dumps(state()) == before, "開始前の中断は記録せず終了コード2")

# 読めない形の状態コメントは、新しいシリーズとして上書きする
write_state({})
rc, _, err = run(wt)
s = state()
check(rc == 0 and s["iter"] == 1 and "読めない" in err, "読めない状態コメントは新しいシリーズとして上書きする")
s["run_id"] = "../../escape"
write_state(s)
rc, _, err = run(wt)
check(rc == 0 and state()["run_id"] != "../../escape" and not os.path.exists(os.path.join(root, "escape")),
      "run_id の形を検証し、作業ディレクトリのパスに外の値を使わない")

# 同時にコメントを作った場合、負けた側は自分のコメントを消して撤退する
os.remove(os.path.join(root, "fake", "comments.json"))
rc, _, err = run(wt, FAKE_RACE="1")
check(rc == 2 and "競合" in err and [c["id"] for c in comments()] == [50], "競合で負けたら自分のコメントを消す")
os.remove(os.path.join(root, "fake", "comments.json"))

rc, _, err = run(wt, FAKE_PR_STATE="MERGED")
check(rc == 2 and "オープンではない" in err, "オープンでない PR は拒否する")
rc, _, err = run(wt, FAKE_PR_AUTHOR="someone")
check(rc == 2 and "自分" in err, "他人の PR は拒否する")

rc, _, err = run(wt, FAKE_REVIEW_code_review="deny")
body = comments()[0]["body"]
check(rc == 1 and "gh pr diff" in err and "gh pr diff" not in body, "失敗の詳細は stderr にだけ出し、PR には種類だけを載せる")
check(os.path.isfile(os.path.join(err.rstrip().splitlines()[-1], "failure.txt")), "失敗の詳細を作業ディレクトリに残す")
run(wt, "--new-run")

# --- 安全上限と他人のコメント -------------------------------------------------
s = state()
s["iter"] = 10
write_state(s)
with open(os.path.join(root, "fake", "comments.json")) as f:
    cs = json.load(f)
cs.insert(0, {"id": 1, "login": "someone", "created_at": "2025-01-01T00:00:00Z",
              "body": "<!-- review-loop-state {} -->", "edits": 0})
with open(os.path.join(root, "fake", "comments.json"), "w") as f:
    json.dump(cs, f)
rc, _, err = run(wt)
check(rc == 2 and "安全上限" in err, "反復が安全上限に達したら止まる")
check(state() is not None and next(c for c in comments() if c["id"] == 1)["edits"] == 0, "他人のコメントは触らない")
check("@" not in comments()[-1]["body"].split("-->")[0].replace("\\u0040", ""), "状態コメントに生の @ を含めない")

if os.environ.get("KEEP"):
    print("作業ディレクトリ:", root)
else:
    shutil.rmtree(root, ignore_errors=True)
print(f"\n{'全て成功' if fails == 0 else f'{fails} 件失敗'}")
sys.exit(1 if fails else 0)

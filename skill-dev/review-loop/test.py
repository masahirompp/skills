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
sys.dont_write_bytecode = True  # スキルのディレクトリに __pycache__ を作らない
sys.path.insert(0, sys.argv[1])
import review_loop as r
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


def system_prompt(c):
    """子の呼び出しの記録から、--append-system-prompt の値を取り出す。"""
    return c["args"][c["args"].index("--append-system-prompt") + 1]


def last_row():
    """状態コメントの表のうち、最後の試行の行(合計の行の直前)を返す。"""
    lines = comments()[0]["body"].splitlines()
    return lines[lines.index(next(line for line in lines if line.startswith("| **合計**"))) - 1]


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
check(out.startswith("## 指摘") and "### F1: s" in out, "標準出力は判定のテキストだけ")
s = state()
check(s and s["iter"] == 1 and s["attempts"][0]["result"] == "completed", "状態コメントに反復1が記録される")
check(s and s["lock"]["running"] is False, "ロックが解除される")
check(s and s["attempts"][0]["tokens"] == {"input": 4 * 3500, "cache_read": 4 * 2000, "output": 4 * 300},
      "トークン数はレビュー役3つと判定役の modelUsage の合計(入力はキャッシュを含む)")
body = comments()[0]["body"]
check("| 1.4万(うちキャッシュ読み込み 8000) | 1200 |" in body, "入力と出力のトークン数を別の列に出す")
workdir = err.rstrip().splitlines()[-1]
check(os.path.isfile(os.path.join(workdir, "verdict.md")), "stderr の最後の行は作業ディレクトリ")
with open(os.path.join(workdir, "verdict.md"), encoding="utf-8") as f:
    check(f.read() == out, "判定は作業ディレクトリの verdict.md にも残る")
check(workdir.startswith(os.path.join(root, "review-loop", "o_r", "7")), "作業ディレクトリは <tmp>/review-loop/<リポジトリ>/<PR>/<run>/<試行>")
with open(os.path.join(workdir, "review-code-review.result.md"), encoding="utf-8") as f:
    check(f.read() == "code-review: 指摘1件\n", "各レビューの result のテキストを review-*.result.md に残す")
cs = calls()
reviews = [c for c in cs if c["kind"] == "review"]
check(len(reviews) == 3, "観点ごとに1プロセス起動する")
check(all(not c["env_job_dir"] and not c["env_session_id"] for c in cs), "子の環境から CLAUDE_JOB_DIR などを外す")
check(all(c["guard"] == "1" for c in cs), "子には REVIEW_LOOP_ACTIVE が渡る")
check(not any(c["kind"] == "preflight-not-killed" for c in cs), "事前確認の子は init の直後に止める")
judge = [c for c in cs if c["kind"] == "judge"]
check(judge and "===== 観点: security-review =====" in judge[0]["stdin"], "判定役には各レビューを区切って stdin で渡す")
check(judge and "--json-schema" not in judge[0]["args"] and "## 指摘" in judge[0]["args"][-1],
      "判定役には出力の形をプロンプトで渡す")
check(all("--append-system-prompt" in c["args"] for c in reviews + judge), "運用上の制約を渡す")
check(judge and "stream-json" in judge[0]["args"] and "--verbose" in judge[0]["args"], "判定役も stream-json で受ける")
check(os.path.isfile(os.path.join(workdir, "judge.result.md")) and not os.path.exists(os.path.join(workdir, "denials.txt")),
      "判定役の result のテキストも judge.result.md に残し、拒否がなければ denials.txt は作らない")
prompts = {c["args"][-1] for c in reviews}
check(prompts == {"/code-review high 7", "/security-review", "/mattpocock-skills:code-review PR #7"},
      f"レビュー役のプロンプトは /<観点と引数>({{pr}} を展開)。{prompts}")

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
wd = err.rstrip().splitlines()[-1]
with open(os.path.join(wd, "review-code-review.result.md"), encoding="utf-8") as f:
    check(f.read() == "読めなかった\n", "失敗したレビューでも result のテキストを review-*.result.md に残す")
check(s["attempts"][-1]["tokens"]["output"] >= 300, "拒否で終わった子のトークン数も記録する")
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
check(rc == 1 and "no_output" in err and "空でない result の行がない" in err, "result が空なら失敗")
rc, _, err = run(wt)
check(rc == 2 and "連続失敗" in err, "連続失敗3回で止まる")

rc, _, err = run(wt, "--new-run")
s = state()
check(rc == 0 and s["iter"] == 1 and s["previous_run"]["iterations"] == 2 and len(s["attempts"]) == 1,
      "--new-run で直前のシリーズを要約して始め直す")

rc, _, err = run(wt, FAKE_JUDGE="noheading")
check(rc == 1 and "no_output" in err and "## 指摘" in err, "判定に決めた見出しがなければ失敗")
rc, out, err = run(wt, FAKE_JUDGE="fenced")
check(rc == 0 and out.startswith("## 指摘(1件)") and out.rstrip().endswith("なし"),
      "見出しに文字が足されていても通し、前置きとコードフェンスは落とす")
rc, out, err = run(wt, FAKE_JUDGE="codeend")
check(rc == 0 and out.rstrip().endswith("x\n```"), "前置きでフェンスを開いていなければ、末尾のコードブロックは残す")
rc, out, err = run(wt, FAKE_JUDGE="conflictfirst")
check(rc == 0 and out.startswith("## 競合"), "競合の節が先にあっても落とさない")
rc, _, err = run(wt, FAKE_JUDGE="empty")
check(rc == 1 and "no_output" in err and "空でない result の行がない" in err, "判定が空なら失敗")
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
s["lock"] = {"running": True, "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sha": "abcdef0", "nonce": "n"}
write_state(s)
rc, _, err = run(wt)
check(rc == 2 and "実行中" in err and state()["lock"]["nonce"] == "n", "実行中のロックがあれば撤退する")

s["lock"]["started_at"] = "2026-01-01T00:00:00Z"
s["consecutive_failures"] = 2
write_state(s)
rc, _, err = run(wt)
check(rc == 2 and "連続失敗" in err and state()["attempts"][-1]["result"] == "interrupted",
      "古いロックの interrupted も連続失敗に数え、上限に達すれば止まる(片付けは記録される)")
s["consecutive_failures"] = 0
write_state(s)
n = len(s["attempts"])
rc, _, err = run(wt)
s = state()
check(rc == 0 and s["attempts"][n]["result"] == "interrupted" and s["attempts"][n]["sha"] == "abcdef0",
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

# 読めない形の状態コメントは、--new-run の指示があるまで上書きしない(上限を黙って外さない)
write_state({})
rc, _, err = run(wt)
check(rc == 2 and "読めない" in err and "--new-run" in err and state() == {}, "読めない状態コメントでは止まり、上書きしない")
rc, _, err = run(wt, "--new-run")
s = state()
check(rc == 0 and s["iter"] == 1, "--new-run なら読めない状態コメントを上書きして始め直す")
s["run_id"] = "../../escape"
write_state(s)
rc, _, err = run(wt)
check(rc == 2 and not os.path.exists(os.path.join(root, "escape")),
      "run_id の形を検証し、作業ディレクトリのパスに外の値を使わない")
s["run_id"] = "20260101T000000"
s["attempts"][0]["reason"] = 5
write_state(s)
rc, _, err = run(wt)
check(rc == 2 and "読めない" in err, "表に出す値の型も検証する")
run(wt, "--new-run")

s = state()
s["attempts"][0].pop("at")
write_state(s)
rc, _, err = run(wt)
check(rc == 2 and "読めない" in err, "試行の記録の形が崩れていても止まる")
run(wt, "--new-run")

# 事前確認の最中にスクリプトが SIGKILL されても、事前確認の子は残らない
env = env_for(OVERRIDES="{}", FAKE_PREFLIGHT_DELAY="60")
n_pre = len([c for c in calls() if c["kind"] == "preflight"])
p = subprocess.Popen([sys.executable, "-c", RUNNER, SCRIPTS, "iterate", wt], env=env,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
deadline = time.time() + 20
while time.time() < deadline and len([c for c in calls() if c["kind"] == "preflight"]) == n_pre:
    time.sleep(0.2)
pre = [c for c in calls() if c["kind"] == "preflight"][-1]
p.kill()
p.wait()
time.sleep(3)
check(not alive(pre["pid"]), "事前確認の子も見張り役が止める")

rc, _, err = run(wt, overrides={"PERSPECTIVES": ["code-review high", "code-review max"]})
check(rc == 2 and "重複" in err, "同じスキルを重複して並べると拒否する")

# 試行の作業ディレクトリが既にあれば、前の出力と混ざらないよう失敗にする(failed: <種類> の行を出す)
s = state()
os.makedirs(os.path.join(root, "review-loop", "o_r", "7", s["run_id"], str(len(s["attempts"]) + 1)))
rc, _, err = run(wt)
check(rc == 1 and "failed: workdir_error" in err, "作業ディレクトリが既にあれば失敗にし、failed: の行に種類を出す")
run(wt, "--new-run")

# 起点が広い権限で作られていても、自分のものなら 0700 に絞って使う
os.chmod(os.path.join(root, "review-loop"), 0o755)
rc, _, err = run(wt)
mode = os.stat(os.path.join(root, "review-loop")).st_mode & 0o777
check(rc == 0 and mode == 0o700, f"起点が 0755 なら 0700 に直して使う({oct(mode)}) {err[-200:] if rc else ''}")

# 失敗した試行でも、子が作業ツリーを変えていれば混入を優先して報告する
rc, _, err = run(wt, FAKE_REVIEW_code_review="dirty", FAKE_REVIEW_security_review="deny")
reason = state()["attempts"][-1]["reason"]
check(rc == 1 and "failed: contamination" in err and "stray.txt" in err and "permission_denied" in err
      and reason == "contamination", f"失敗した試行でも混入を確かめ、優先して報告する({reason})")
os.remove(os.path.join(wt, "stray.txt"))

# 子がブランチを切り替えたら(gh pr view が失敗する状態でも)混入として報告する
rc, _, err = run(wt, FAKE_REVIEW_security_review="switch")
check(rc == 1 and "failed: contamination" in err and "ブランチ が変わった" in err, "ブランチの切り替えは混入")
sh("git", "switch", "-q", "feature", cwd=wt)
sh("git", "branch", "-q", "-D", "other", cwd=wt)

# 状態コメントの表に合計の行を出し、--new-run でも前のシリーズの合計を残す
body = comments()[0]["body"]
check("| **合計** |" in body, "表に合計の行を出す")
rc, _, err = run(wt, "--new-run")
s = state()
check(rc == 0 and s["previous_run"]["tokens"]["output"] > 0 and "直前のシリーズ" in comments()[0]["body"],
      "--new-run でも前のシリーズのトークン数の合計を残す")

# トークン数の記録に欠けたキーがあれば、読めない状態コメントとして扱う
s["attempts"][0]["tokens"] = {"input": 1}
write_state(s)
rc, _, err = run(wt)
check(rc == 2 and "読めない" in err, "トークン数の記録の形も検証する")
run(wt, "--new-run")

# 試行中に PR にだけ別の push があったら、混入ではなく head_changed として失敗にする
rc, _, err = run(wt, FAKE_REVIEW_security_review="remote")
check(rc == 1 and "failed: head_changed" in err and "作者と内容を確かめる" in err,
      "試行中の PR への push は head_changed とし、子の push の可能性を伝える")
sh("git", "fetch", "-q", "origin", cwd=wt)
sh("git", "reset", "-q", "--hard", "origin/feature", cwd=wt)

# マーカーを引用した自分の通常のコメントは、状態コメントとみなさない
with open(os.path.join(root, "fake", "comments.json")) as f:
    cs = json.load(f)
cs.insert(0, {"id": 2, "login": "me", "created_at": "2024-01-01T00:00:00Z",
              "body": "状態は `<!-- review-loop-state ... -->` に書かれる", "edits": 0})
with open(os.path.join(root, "fake", "comments.json"), "w") as f:
    json.dump(cs, f)
rc, _, err = run(wt)
quoted = next(c for c in comments() if c["id"] == 2)
check(rc == 0 and quoted["edits"] == 0 and "件ある" not in err, "マーカーを引用しただけの自分のコメントは上書きしない")
run(wt, "--new-run")

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

# 状態コメントへの書き込み(ロックの解除)に失敗したら、成功でもそう伝える(F10)
patches = os.path.join(root, "fake", "patches")
if os.path.exists(patches):
    os.remove(patches)
rc, _, err = run(wt, FAKE_FAIL_PATCH_FROM="2")  # 1回目(ロックの取得)は通し、2回目(解除)から失敗させる
check(rc == 0 and "記録できなかった" in err and "反復回数が進んでいない" in err, "成功でも記録できなければ警告する")
s = state()
s["lock"] = {"running": False, "started_at": None, "sha": None, "nonce": None}
write_state(s)

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
s = state()
s["attempts"].append({"sha": "abcdef0", "at": "2026-01-01T00:00:00Z", "result": "failed", "reason": "x @someone"})
s["iter"] = 0
write_state(s)
run(wt)
body = next(c for c in comments() if c["login"] == "me")["body"]
json_part, table = body.split("-->", 1)
check("@" not in json_part and "@someone" not in table and "@\u200bsomeone" in table, "状態コメントに生の @ を含めない")

# 拒否のイベントが stream に出たら、子が作業を続けていても、その時点で全体を止める
run(wt, "--new-run")
t = time.time()
rc, _, err = run(wt, FAKE_REVIEW_code_review="denylive", FAKE_REVIEW_security_review="hang")
check(rc == 1 and "permission_denied: review code-review" in err and "gh pr diff 7" in err and time.time() - t < 30,
      "拒否のイベントが出たら、子の終了を待たずに permission_denied で止める")
last = [c for c in calls() if c["kind"] == "review"][-3:]
check(not any(alive(c["pid"]) for c in last), "拒否で止めたとき、どの子も残らない")

# result の行が複数あれば、最上位の空でないものを全てつなぐ(最後の行だけを使うと本文が捨てられる)
run(wt, "--new-run")
for mode, final in (("multiempty", ""), ("multishort", "前のメッセージの内容から変わりません")):
    rc, out, err = run(wt, FAKE_REVIEW_mattpocock_skills_code_review=mode)
    wd = err.rstrip().splitlines()[-1]
    stdin = [c for c in calls() if c["kind"] == "judge"][-1]["stdin"]
    with open(os.path.join(wd, "review-mattpocock-skills_code-review.result.md"), encoding="utf-8") as f:
        saved = f.read()
    check(rc == 0 and "mattpocock-skills:code-review: 本文" in stdin and "バックグラウンドで実行しています" in stdin
          and saved.index("バックグラウンド") < saved.index("本文") and (not final or final in saved)
          and "サブエージェントの結果" not in saved,
          f"result の行が複数あれば、最上位の空でないものを出た順につなぐ(最後の行が{'空' if not final else '短い文'})")
    check(state()["attempts"][-1]["tokens"]["output"] == 4 * 300,
          "トークン数は最後の result の行だけで数える(modelUsage は累計なので足さない)")
rc, out, err = run(wt, FAKE_REVIEW_code_review="multierror")
stdin = [c for c in calls() if c["kind"] == "judge"][-1]["stdin"]
check(rc == 0 and "code-review: 本文" in stdin and "API Error" not in stdin, "エラーの result の行はつながない")
rc, _, err = run(wt, FAKE_REVIEW_code_review="multiallempty")
check(rc == 1 and "no_output: review code-review" in err, "result の行が全て空なら no_output")

# 判定役は行をつながず、見出しを含む行のうち最後のものを採る
rc, out, err = run(wt, FAKE_JUDGE="multi")
check(rc == 0 and out.startswith("## 指摘") and "突き合わせています" not in out,
      "判定役の result の行が複数でも、判定の行を採り、前置きは落とす")
rc, out, err = run(wt, FAKE_JUDGE="multishort")
check(rc == 0 and out.rstrip().endswith("なし") and "変わりません" not in out, "判定役の後の行の短い文は判定に混ぜない")
rc, out, err = run(wt, FAKE_JUDGE="partiallater")
check(rc == 0 and "## 競合" in out and "補足" not in out, "後の行が見出しを一部だけ持っていても、完全な判定を採る")
rc, out, err = run(wt, FAKE_JUDGE="redo")
check(rc == 0 and out.count("## 指摘") == 1 and "下書き" not in out and "```" not in out,
      "判定役が判定を出し直したら、最後の判定だけを採る")

# 設定のルールで、`;` でつないだコマンドの一部が拒否されただけなら止めず、内容を作業ディレクトリと stderr に残す
rc, out, err = run(wt, FAKE_REVIEW_security_review="denyconfig", FAKE_JUDGE="denyconfig")
wd = err.rstrip().splitlines()[-1]
with open(os.path.join(wd, "denials.txt"), encoding="utf-8") as f:
    denials = f.read()
check(rc == 0 and out.startswith("## 指摘"), f"設定のルールでの拒否では試行を止めない {err[-300:] if rc else ''}")
check("review security-review: Bash" in denials and "judge: Bash" in denials and "grep -n KEY .env" in denials
      and "subcommandResults" in denials, "設定のルールでの拒否は作業ディレクトリの denials.txt に残す")
check("設定のルールで拒否された" in err and "grep -n KEY .env" in err, "設定のルールでの拒否は stderr にも出す")
stdin = [c for c in calls() if c["kind"] == "judge"][-1]["stdin"]
check("権限の設定で拒否された" in stdin and "review security-review: Bash" in stdin, "止めなかった拒否は判定役の入力にも添える")

# source が config でも、分類器による拒否や、tool_use_id のない拒否は止める
rc, _, err = run(wt, FAKE_REVIEW_security_review="denyclassifier")
check(rc == 1 and "permission_denied: review security-review" in err, "source が config でも、分類器による拒否は止める")
rc, _, err = run(wt, FAKE_REVIEW_security_review="denynoid")
check(rc == 1 and "permission_denied: review security-review" in err, "tool_use_id のない拒否は止める")
run(wt, "--new-run")
rc, _, err = run(wt, FAKE_REVIEW_security_review="denyrepeat")
detail = err.split("failed: ", 1)[-1]
check(rc == 1 and "permission_denied" in err and detail.count("gh pr diff 7") == 1,
      "tool_use_id のない拒否が result の行ごとに載っても、1回だけ出す")
run(wt, "--new-run")

# ほかの観点の失敗で止めるときも、まだ動いている子の止めない拒否を記録に残す
rc, _, err = run(wt, FAKE_REVIEW_code_review="failslow", FAKE_REVIEW_security_review="denyconfighang")
wd = err.rstrip().splitlines()[-1]
check(rc == 1 and "child_error: review code-review" in err and os.path.isfile(os.path.join(wd, "denials.txt")),
      "ほかの観点の失敗で止めても、動いていた子の止めない拒否を denials.txt に残す")
run(wt, "--new-run")

# --- 観点の入れ替えと追加の指示 -----------------------------------------------
n = len(calls())
rc, out, err = run(wt, "--perspective", " /code-review\thigh  {pr} ", "--perspective", "mattpocock-skills:code-review PR #{pr}",
                   "--instruct", "code-review=削除したファイルの中身は確かめない", "--instruct", " code-review = テストは見ない",
                   "--instruct", "/mattpocock-skills:code-review=a=b PR #{pr}")
new = calls()[n:]
reviews = [c for c in new if c["kind"] == "review"]
judge = [c for c in new if c["kind"] == "judge"]
check(rc == 0 and {c["args"][-1] for c in reviews} == {"/code-review high 7", "/mattpocock-skills:code-review PR #7"},
      f"--perspective を渡すと、既定の代わりにそれだけを使い、空白を詰めて起動する {err[-300:] if rc else ''}")
by_name = {c["name"]: system_prompt(c) for c in reviews}
check("削除したファイルの中身は確かめない\nテストは見ない" in by_name.get("code-review", ""),
      "--instruct はその観点のシステムプロンプトに足し、同じ観点への指示は改行でつなぐ")
check("削除したファイル" not in by_name.get("mattpocock-skills:code-review", "x"), "--instruct はほかの観点には渡さない")
check(by_name.get("mattpocock-skills:code-review", "").endswith("\na=b PR #7"), "--instruct は最初の `=` で分け、スキル名の先頭の `/` を除き、{pr} を置き換える")
check(all("依頼文" in system_prompt(c) for c in reviews + judge),
      "レビュー役にも判定役にも、サブエージェントに任せるときは制約と指示を依頼文に含めるよう頼む")
check(judge and "観点 code-review のレビュー役に与えた追加の指示 -----\n削除したファイル" in system_prompt(judge[0])
      and "----- ここまで: code-review -----" in system_prompt(judge[0])
      and "削除したファイル" not in judge[0]["stdin"],
      "追加の指示は判定役のシステムプロンプトで渡し、標準入力には混ぜない")
check(judge and "追加の指示" in judge[0]["args"][-1], "判定役の手順に、追加の指示の扱いを書く")
last = state()["attempts"][-1]
body = comments()[0]["body"]
check(last.get("perspectives") == ["code-review high {pr}", "mattpocock-skills:code-review PR #{pr}"]
      and last.get("instructed") == ["code-review", "mattpocock-skills:code-review"]
      and "観点 code-review high {pr}, mattpocock-skills:code-review PR #{pr}、指示あり code-review, mattpocock-skills:code-review" in body
      and "削除したファイル" not in body,
      "既定と違う観点と、指示を渡した観点を状態コメントに残す(指示の本文は残さない)")
rc, _, err = run(wt, "--perspective", "code-review low {pr}", "--perspective", "security-review",
                 "--perspective", "mattpocock-skills:code-review PR #{pr}")
check(rc == 0 and "観点 code-review low {pr}, security-review" in last_row(),
      "スキル名が既定と同じでも、引数が違えば表に観点を出す")
check("直前の試行と指示を渡した観点が違う" in err and "直前の試行と観点が違う" in err,
      "直前の試行と観点や指示が違えば警告する")
rc, _, err = run(wt, "--perspective", "security-review", "--perspective", "mattpocock-skills:code-review PR #{pr}",
                 "--perspective", "code-review high {pr}")
last = state()["attempts"][-1]
check(rc == 0 and "instructed" not in last and "、観点" not in last_row(),
      "既定の観点を並べ替えただけなら、表に観点を出さない")
rc, _, err = run(wt)
last = state()["attempts"][-1]
check(rc == 0 and "warn: 直前の試行と" not in err and len(last.get("perspectives", [])) == 3,
      "直前の試行と同じなら警告せず、既定の観点も記録する")
s = state()
s["attempts"].append({"sha": "abcdef0", "at": "2026-01-01T00:00:00Z", "result": "interrupted", "reason": "stale_lock",
                      "tokens": {"input": 0, "cache_read": 0, "output": 0}})
write_state(s)
rc, _, err = run(wt)
check(rc == 0 and "warn: 直前の試行と" not in err, "古いロックを片付けた記録とは比べない")
rc, _, _ = run(wt, "--instruct", "security-review=x", FAKE_REVIEW_security_review="fail")
check(rc == 1 and state()["attempts"][-1].get("instructed") == ["security-review"], "失敗した試行にも、指示を渡した観点を残す")
rc, _, err = run(wt, "--new-run", "--instruct", "security-review=x")
check(rc == 0 and "warn: 直前の試行と" not in err, "シリーズの初回は警告しない")
rc, _, _ = run(wt, "--perspective", "code-review " + "x" * 300)
check(rc == 0 and len(state()["attempts"][-1]["perspectives"][0]) == 200, "状態コメントに記録する観点の長さを抑える")
long_flags = [a for i in range(10) for a in ("--perspective", f"code-review{i} " + "x" * 300)]
long_skills = ",".join(f"code-review{i}" for i in range(10))
run(wt, *long_flags, FAKE_SKILLS=long_skills)
limit = len(comments()[0]["body"]) + 500  # 長い観点の試行を2つは載せられない
rc, _, _ = run(wt, *long_flags, overrides={"MAX_BODY_CHARS": limit}, FAKE_SKILLS=long_skills)
s = state()
check(rc == 0 and len(comments()[0]["body"]) <= limit and "perspectives" not in s["attempts"][-2]
      and "perspectives" in s["attempts"][-1],
      "本文が上限を超えるなら、古い試行から観点の記録を外す")

before = json.dumps(state())
for flags, label in ((("--instruct", "security-review"), "`=` のない --instruct"),
                     (("--instruct", "=x"), "スキル名が空の --instruct"),
                     (("--instruct", "code-review= "), "指示が空の --instruct"),
                     (("--instruct", "nosuch=x"), "観点にないスキルへの --instruct"),
                     (("--perspective", "code-review high {pr}", "--instruct", "security-review=x"),
                      "--perspective で外した観点への --instruct"),
                     (("--perspective", " "), "空の --perspective"),
                     (("--perspective", "code-review high {pr}", "--perspective", "code-review low {pr}"),
                      "同じスキルを重ねた --perspective")):
    rc, _, err = run(wt, *flags)
    check(rc == 2, f"{label}: 終了コード2({rc}) {err.strip().splitlines()[-2:] if rc != 2 else ''}")
check(json.dumps(state()) == before, "観点の指定の誤りは状態に記録しない")

if os.environ.get("KEEP"):
    print("作業ディレクトリ:", root)
else:
    shutil.rmtree(root, ignore_errors=True)
print(f"\n{'全て成功' if fails == 0 else f'{fails} 件失敗'}")
sys.exit(1 if fails else 0)

#!/usr/bin/env python3
"""review-loop の review_loop.py(begin と end)を、偽の gh で検証する。GitHub には触れない。

    python3 skill-dev/review-loop/test.py         # 実行して後片付けする
    KEEP=1 python3 skill-dev/review-loop/test.py  # 作業ディレクトリを残す
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile

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


def run(wt, cmd, *flags, overrides=None, **extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("FAKE_")}
    env.update(PATH=FAKES + os.pathsep + env["PATH"], FAKE_DIR=os.path.join(root, "fake"), TMPDIR=root,
               OVERRIDES=json.dumps(overrides or {}))
    env.update(extra)
    p = subprocess.run([sys.executable, "-c", RUNNER, SCRIPTS, cmd, wt, *flags], env=env, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def begin(wt, *flags, **kw):
    """begin を実行し、(終了コード, 標準出力の key=value の辞書, stderr) を返す。"""
    rc, out, err = run(wt, "begin", *flags, **kw)
    return rc, dict(line.split("=", 1) for line in out.splitlines() if "=" in line), err


def end(wt, *flags, **kw):
    rc, _, err = run(wt, "end", *flags, **kw)
    return rc, err


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
    raw = cs[0]["body"].split("<!-- review-loop-state ", 1)[1].split(" -->", 1)[0]
    return json.loads(raw)


def write_state(s):
    body = "<!-- review-loop-state " + (s if isinstance(s, str) else json.dumps(s)) + " -->\nx"
    with open(os.path.join(root, "fake", "comments.json"), "w") as f:
        json.dump([{"id": 500, "login": "me", "created_at": "2026-01-01T00:00:00Z", "body": body, "edits": 0}], f)


def base_state(**over):
    s = {"run_id": "20260101T000000", "iter": 0, "safety_max": 10, "consecutive_failures": 0, "attempts": [],
         "previous_run": None, "lock": {"running": False, "started_at": None, "sha": None, "nonce": None}}
    s.update(over)
    return s


def ago(minutes):
    t = dt.datetime.now(dt.timezone.utc).replace(microsecond=0) - dt.timedelta(minutes=minutes)
    return t.isoformat().replace("+00:00", "Z")


def commit(wt, name, push=True):
    with open(os.path.join(wt, name), "w") as f:
        f.write(name)
    sh("git", "add", "-A", cwd=wt)
    sh("git", "commit", "-qm", name, cwd=wt)
    if push:
        sh("git", "push", "-q", "origin", "feature", cwd=wt)


def table_rows():
    return [line for line in comments()[0]["body"].splitlines() if line.startswith("| ") and not line.startswith("| SHA")]


# --- 1反復: begin → end ------------------------------------------------------
wt = setup()
head = sh("git", "rev-parse", "HEAD", cwd=wt)
rc, out, err = begin(wt)
check(rc == 0 and out.get("pr") == "7" and out.get("sha") == head and out.get("attempt") == "1", "begin が pr、sha、attempt を出す")
check(os.path.isdir(out.get("workdir", "")) and out["workdir"].startswith(os.path.join(root, "review-loop", "o_r", "7")),
      "begin が作業ディレクトリを作る")
check(os.stat(os.path.join(root, "review-loop")).st_mode & 0o777 == 0o700, "作業ディレクトリの起点は 0700")
s = state()
check(s["lock"]["running"] and s["lock"]["sha"] == head and s["lock"]["branch"] == "feature"
      and s["lock"]["stale_after"] == 55 * 60 and s["attempts"] == [], "begin がロックに SHA とブランチを記録し、試行はまだ記録しない")
with open(os.path.join(wt, "debug.log"), "w") as f:  # .gitignore に当たるファイルは、混入に数えない
    f.write("x")
rc, err = end(wt)
s = state()
check(rc == 0 and "完了: 反復 1" in err, "end が completed で終わる")
check(s["iter"] == 1 and not s["lock"]["running"] and s["consecutive_failures"] == 0
      and s["attempts"] == [{"sha": head, "at": s["attempts"][0]["at"], "result": "completed", "iter": 1}],
      "end が試行を completed として記録し、ロックを解く")
check(len(comments()) == 1 and comments()[0]["edits"] == 1, "状態コメントは1つで、編集で更新する")
check(table_rows() == [f"| {head[:7]} | {s['attempts'][0]['at']} | completed(反復 1) |"], "表に SHA、時刻、結果が出る")

commit(wt, "b.txt")
rc, out, _ = begin(wt)
check(rc == 0 and out["attempt"] == "2" and out["workdir"].endswith("/2"), "2回目の begin は、別の作業ディレクトリを作る")
rc, _ = end(wt)
check(rc == 0 and state()["iter"] == 2 and len(state()["attempts"]) == 2, "2回目の end で反復が2になる")

# --- begin の前提 ------------------------------------------------------------
wt = setup()
with open(os.path.join(wt, "new.txt"), "w") as f:
    f.write("x")
rc, _, err = begin(wt)
check(rc == 2 and "作業ツリーがクリーンでない" in err and state() is None, "未コミットの変更があれば始めない")
os.remove(os.path.join(wt, "new.txt"))
commit(wt, "c.txt", push=False)
rc, _, err = begin(wt)
check(rc == 2 and "PR の head" in err and state() is None, "push していなければ始めない")
sh("git", "push", "-q", "origin", "feature", cwd=wt)
for label, extra, word in (("PR がオープンでない", {"FAKE_PR_STATE": "MERGED"}, "オープンではない"),
                           ("PR の作成者が自分でない", {"FAKE_PR_AUTHOR": "other"}, "作成者"),
                           ("PR が無い", {"FAKE_NO_PR": "1"}, "PR を取得できない")):
    rc, _, err = begin(wt, **extra)
    check(rc == 2 and word in err and state() is None, f"{label}なら始めない")
rc, _, err = run("wt", "begin")
check(rc == 2 and "絶対パス" in err, "worktree が相対パスなら始めない")
os.makedirs(os.path.join(wt, "sub"))
rc, _, err = begin(os.path.join(wt, "sub"))
check(rc == 2 and "トップではない" in err, "worktree のトップでなければ始めない")
os.rmdir(os.path.join(wt, "sub"))
rc, _, err = run(wt, "end", "--failed", " ")
check(rc == 2 and "--failed の理由が空" in err, "--failed の理由が空なら受け付けない")

# --- ロック ------------------------------------------------------------------
rc, err = end(wt)
check(rc == 2 and "閉じる試行が無い" in err and state() is None, "begin していなければ、end は何も記録しない")
rc, _, _ = begin(wt)
rc2, _, err = begin(wt)
check(rc == 0 and rc2 == 2 and "別の試行が実行中" in err and "end" in err, "begin を2回続けると、2回目は始めない")
check(state()["lock"]["running"] and state()["attempts"] == [], "2回目の begin は、1回目のロックを変えない")
rc, _ = end(wt)
rc2, err = end(wt)
check(rc == 0 and rc2 == 2 and "閉じる試行が無い" in err and state()["iter"] == 1, "end を2回続けても、反復は1回しか進まない")

wt = setup()
rc, _, err = begin(wt, FAKE_RACE="1")
check(rc == 2 and "競合" in err and [c["id"] for c in comments()] == [50], "同時に始めた別の試行が先なら撤退し、自分のコメントを消す")

wt = setup()
head = sh("git", "rev-parse", "HEAD", cwd=wt)
for label, lock, minutes, ok in (
        ("stale_after を過ぎたロック", {"stale_after": 3300}, 56, True),
        ("stale_after の内のロック", {"stale_after": 3300}, 1, False),
        ("記録の無い旧版の、75分以内のロック", {}, 60, False),
        ("記録の無い旧版の、75分を過ぎたロック", {}, 76, True),
        ("stale_after が短すぎるロック(55分より短くは見ない)", {"stale_after": 1}, 10, False),
        ("stale_after が大きすぎるロック(120分より長くは見ない)", {"stale_after": 10 ** 9}, 121, True),
        ("stale_after が数でないロック(旧版と同じ長さで見る)", {"stale_after": "x"}, 60, False)):
    write_state(base_state(lock={"running": True, "started_at": ago(minutes), "sha": head, "nonce": "old", **lock}))
    rc, _, err = begin(wt)
    s = state()
    if ok:
        check(rc == 0 and s["attempts"] == [{"sha": head, "at": s["attempts"][0]["at"], "result": "interrupted", "reason": "stale_lock"}]
              and s["consecutive_failures"] == 1 and s["lock"]["nonce"] != "old", f"{label}は、interrupted として片付けて始める")
        shutil.rmtree(os.path.join(root, "review-loop"))
    else:
        check(rc == 2 and "別の試行が実行中" in err and s["lock"]["nonce"] == "old" and s["attempts"] == [], f"{label}は奪わない")

# 旧版のロック(ブランチ名を持たない)を end で閉じる
write_state(base_state(lock={"running": True, "started_at": ago(1), "sha": head, "nonce": "old", "stale_after": 3300}))
rc, _ = end(wt)
check(rc == 0 and state()["iter"] == 1, "ブランチ名の無い旧版のロックも、end で閉じられる")

# --- end の検査 --------------------------------------------------------------
wt = setup()
head = sh("git", "rev-parse", "HEAD", cwd=wt)
rc, out, _ = begin(wt)
with open(os.path.join(wt, "stray.txt"), "w") as f:
    f.write("x")
rc, err = end(wt)
s = state()
check(rc == 1 and "failed: contamination" in err and "stray.txt" in err and "元に戻していない" in err, "作業ツリーが変わっていれば contamination")
check(s["attempts"][-1]["result"] == "failed" and s["attempts"][-1]["reason"] == "contamination" and s["iter"] == 0
      and s["consecutive_failures"] == 1 and not s["lock"]["running"], "contamination を失敗として記録し、ロックを解く")
check(os.path.exists(os.path.join(wt, "stray.txt")), "混入したファイルは消さない")
with open(os.path.join(out["workdir"], "failure.txt")) as f:
    check(f.read().startswith("contamination\n"), "失敗の詳細を作業ディレクトリに残す")
os.remove(os.path.join(wt, "stray.txt"))

rc, _, _ = begin(wt)
commit(wt, "d.txt", push=False)
rc, err = end(wt)
check(rc == 1 and "failed: contamination" in err and "HEAD が変わった" in err, "HEAD が変わっていれば contamination")
sh("git", "push", "-q", "origin", "feature", cwd=wt)

rc, _, _ = begin(wt)
sh("git", "switch", "-qc", "other", cwd=wt)
rc, err = end(wt)
check(rc == 2 and "PR を取得できない" in err and state()["lock"]["running"], "PR の無いブランチに切り替わっていると、end は記録せずに止まる(ロックは残る)")
sh("git", "push", "-q", "origin", "other", cwd=wt)  # 切り替えた先のブランチにも PR がある場合
rc, err = end(wt)
check(rc == 1 and "ブランチが変わった: feature → other" in err, "ブランチが変わっていれば contamination")
sh("git", "switch", "-q", "feature", cwd=wt)
check(state()["consecutive_failures"] == 3, "失敗が続くと、連続失敗が数えられる")
rc, _, err = begin(wt)
check(rc == 2 and "連続失敗が 3 回" in err and not state()["lock"]["running"], "連続失敗が上限に達していれば始めず、ロックも残さない")

wt = setup()
rc, _, _ = begin(wt)
other = os.path.join(root, "other")
sh("git", "clone", "-q", "-b", "feature", os.path.join(root, "origin.git"), other)
for k, v in (("user.name", "t"), ("user.email", "t@example.com")):
    sh("git", "config", k, v, cwd=other)
commit(other, "pushed.txt")
rc, err = end(wt)
check(rc == 1 and "failed: head_changed" in err and state()["attempts"][-1]["reason"] == "head_changed",
      "試行中に PR へ push があれば head_changed")

wt = setup()
rc, _, _ = begin(wt)
rc, err = end(wt, "--failed", "code-review が結果を返さなかった | @someone <b> --> 終わり")
s = state()
check(rc == 1 and "failed: reviewer_failed" in err and s["attempts"][-1]["reason"].startswith("reviewer_failed: code-review が結果を返さなかった")
      and s["consecutive_failures"] == 1 and s["iter"] == 0 and not s["lock"]["running"], "--failed は、理由付きの失敗として記録する")
row = table_rows()[-1]
check("\\|" in row and "@​" in row and "&lt;b>" in row and "@someone" not in row.replace("@​", ""),
      "理由の | と @ と < は、表を壊さず、メンションにもならない形で出る")
rc, _, _ = begin(wt)
rc, err = end(wt, "--failed", "x" * 300)
check(rc == 1 and len(state()["attempts"][-1]["reason"]) == len("reviewer_failed: ") + 100, "理由は100文字までで記録する")
rc, _, _ = begin(wt)
with open(os.path.join(wt, "stray.txt"), "w") as f:
    f.write("x")
rc, err = end(wt, "--failed", "タイムアウト")
check(rc == 1 and "failed: contamination" in err and "--failed で閉じようとした: タイムアウト" in err
      and state()["attempts"][-1]["reason"] == "contamination", "--failed でも、混入があれば混入を優先して記録する")

# end の書き込みが失敗したら、ロックが残り、やり直せる
wt = setup()
rc, _, _ = begin(wt)
rc, err = end(wt, FAKE_FAIL_PATCH_FROM="1")
check(rc == 2 and "失敗した" in err and state()["lock"]["running"] and state()["iter"] == 0, "end の書き込みが失敗すると、記録せずに止まる(ロックは残る)")
os.remove(os.path.join(root, "fake", "patches"))
rc, _ = end(wt)
check(rc == 0 and state()["iter"] == 1, "もう一度 end を呼べば、記録できる")

# --- 上限、読めない状態、--new-run --------------------------------------------
wt = setup()
write_state(base_state(iter=10))
rc, _, err = begin(wt)
check(rc == 2 and "安全上限(10 回)" in err and not state()["lock"]["running"] and state()["attempts"] == [],
      "反復が上限に達していれば始めず、ロックも残さない")
rc, out, _ = begin(wt, "--new-run")
s = state()
check(rc == 0 and s["iter"] == 0 and s["previous_run"] == {"run_id": "20260101T000000", "iterations": 10}
      and s["run_id"] != "20260101T000000", "--new-run は、直前のシリーズを要約して始め直す")
check("直前のシリーズ: run 20260101T000000(反復 10)" in comments()[0]["body"], "直前のシリーズが状態コメントに出る")
end(wt)

for label, broken in (("JSON でない", "{broken"), ("iter が数でない", json.dumps(base_state(iter="1"))),
                      ("lock が無い", json.dumps({k: v for k, v in base_state().items() if k != "lock"})),
                      ("試行の sha が SHA でない", json.dumps(base_state(attempts=[{"sha": "zzz", "at": "x", "result": "completed"}])))):
    wt = setup()
    write_state(broken)
    rc, _, err = begin(wt)
    check(rc == 2 and "読めない" in err and "--new-run" in err, f"状態コメントが読めない({label})なら始めない")
    rc, err = end(wt)
    check(rc == 2 and "状態コメントを読めない" in err, f"状態コメントが読めない({label})なら、end も記録しない")
rc, _, err = begin(wt, "--new-run")
check(rc == 0 and "新しいシリーズとして上書きする" in err and state()["iter"] == 0, "読めない状態コメントは、--new-run で上書きして始める")

# 旧版(レビュー役を起動していた版)が書いた状態を読める
wt = setup()
head = sh("git", "rev-parse", "HEAD", cwd=wt)
old = base_state(iter=1, previous_run={"run_id": "20251231T000000", "iterations": 2, "tokens": {"input": 5, "cache_read": 1, "output": 2}},
                 attempts=[{"sha": head, "at": "2026-01-01T00:00:00Z", "result": "completed", "iter": 1, "model": "opus",
                            "tokens": {"input": 100, "cache_read": 50, "output": 10},
                            "perspectives": ["code-review high {pr}", "security-review"], "instructed": ["code-review"]},
                           {"sha": head, "at": "2026-01-01T01:00:00Z", "result": "failed", "reason": "permission_denied: review code-review",
                            "tokens": {"input": 0, "cache_read": 0, "output": 0}}])
write_state(old)
rc, out, _ = begin(wt)
rc2, _ = end(wt)
s = state()
check(rc == 0 and rc2 == 0 and out["attempt"] == "3" and s["iter"] == 2 and s["attempts"][:2] == old["attempts"],
      "旧版の状態(トークン数、観点、モデルの記録つき)を読め、記録を保ったまま続けられる")
check(table_rows()[1].endswith("| failed: permission_denied: review code-review |") and "トークン" not in comments()[0]["body"],
      "旧版の試行も表に出る(トークン数の列は出さない)")

# --- 作業ディレクトリ --------------------------------------------------------
wt = setup()
head = sh("git", "rev-parse", "HEAD", cwd=wt)
write_state(base_state())
os.makedirs(os.path.join(root, "review-loop", "o_r", "7", "20260101T000000", "1"))
rc, _, err = begin(wt)
s = state()
check(rc == 1 and "failed: workdir_error" in err and "既にある" in err, "作業ディレクトリが既にあれば workdir_error")
check(s["attempts"] == [{"sha": head, "at": s["attempts"][0]["at"], "result": "failed", "reason": "workdir_error"}]
      and s["consecutive_failures"] == 1 and not s["lock"]["running"], "workdir_error を失敗として記録し、ロックを解く")

if not os.environ.get("KEEP"):
    shutil.rmtree(root, ignore_errors=True)
else:
    print("作業ディレクトリ:", root)
print("\n失敗 %d 件" % fails if fails else "\n全て成功")
sys.exit(1 if fails else 0)

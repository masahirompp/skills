#!/usr/bin/env python3
"""review-loop の review_loop.py(begin と end)を、偽の gh で検証する。GitHub には触れない。

    python3 skill-dev/review-loop/test.py         # 実行して後片付けする
    KEEP=1 python3 skill-dev/review-loop/test.py  # 作業ディレクトリを残す
"""
import datetime as dt
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


def run(wt, cmd, *flags, overrides=None, cwd=None, **extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("FAKE_")}
    env.update(PATH=FAKES + os.pathsep + env["PATH"], FAKE_DIR=os.path.join(root, "fake"), TMPDIR=root,
               OVERRIDES=json.dumps(overrides or {}))
    env.update(extra)
    # 親は worktree のトップを作業ディレクトリにして呼ぶ(begin が確かめる)
    p = subprocess.run([sys.executable, "-c", RUNNER, SCRIPTS, cmd, wt, *flags], env=env, capture_output=True, text=True,
                       cwd=cwd or (wt if os.path.isdir(wt) else root))
    return p.returncode, p.stdout, p.stderr


def begin(wt, *flags, roles=("code-review",), **kw):
    """begin を実行し、(終了コード, 標準出力の key=value の辞書, stderr) を返す。始められたら、全ての役の出力を置く。
    roles が None なら --roles を付けない(既定の役)。"""
    if roles is not None:
        flags += ("--roles", ",".join(roles))
    rc, out, err = run(wt, "begin", *flags, **kw)
    out = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    if rc == 0:
        for key in out:
            if key.startswith("out."):
                review(out, key[len("out."):], f"{key[len('out.'):]} の指摘\n")
    return rc, out, err


def review(out, role, text):
    """役の出力を、begin が示した置き場に書く。text が None なら消す。"""
    path = out[f"out.{role}"]
    if text is None:
        os.remove(path)
        return
    with open(path, "w") as f:
        f.write(text)


def end(wt, *flags, **kw):
    global end_out
    rc, out, err = run(wt, "end", *flags, **kw)
    end_out = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return rc, err


def record_path(wt):
    return os.path.join(sh("git", "rev-parse", "--absolute-git-dir", cwd=wt), "review-loop-attempt.json")


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
check(set(out) == {"pr", "sha", "attempt", "workdir", "out.code-review"} and os.path.dirname(out["out.code-review"]) != out["workdir"]
      and not out["out.code-review"].startswith(out["workdir"]), "begin が、役の出力の置き場を、作業ディレクトリの外に作る")
check(s["lock"]["running"] and s["lock"]["sha"] == head and s["lock"]["branch"] == "feature"
      and s["lock"]["stale_after"] == 55 * 60 and s["attempts"] == [], "begin がロックに SHA とブランチを記録し、試行はまだ記録しない")
with open(os.path.join(wt, "debug.log"), "w") as f:  # .gitignore に当たるファイルは、混入に数えない
    f.write("x")
rc, err = end(wt)
s = state()
check(rc == 0 and "完了: 反復 1" in err and end_out == {"workdir": out["workdir"], "roles": "code-review"},
      "end が completed で終わり、作業ディレクトリと役の名前を出す")
check(sorted(os.listdir(out["workdir"])) == ["review-code-review.md", "reviews.md"] and not os.path.exists(os.path.dirname(out["out.code-review"])),
      "end が、役の出力を作業ディレクトリに集め、置き場を消す")
check(s["iter"] == 1 and not s["lock"]["running"] and s["consecutive_failures"] == 0
      and s["attempts"] == [{"sha": head, "at": s["attempts"][0]["at"], "result": "completed", "roles": ["code-review"], "iter": 1}],
      "end が試行を completed として記録し、ロックを解く")
check(not os.path.exists(record_path(wt)) and sh("git", "status", "--porcelain", "--ignored", cwd=wt) == "!! debug.log",
      "試行の記録は end で消え、作業ツリーにも残らない")
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
rc, _, err = begin(wt, cwd=root)
check(rc == 2 and "worktree のトップ" in err and "レビュー役はあなたの作業ディレクトリで動く" in err and state() is None,
      "作業ディレクトリが worktree でなければ始めない")
os.makedirs(os.path.join(wt, "sub"))
rc, _, err = begin(os.path.join(wt, "sub"), cwd=os.path.join(wt, "sub"))
check(rc == 2 and "トップではない" in err, "worktree のトップでなければ始めない")
os.rmdir(os.path.join(wt, "sub"))
rc, _, err = run(wt, "end", "--failed", " ")
check(rc == 2 and "--failed の理由が空" in err, "--failed の理由が空なら受け付けない")

# --- ロック ------------------------------------------------------------------
rc, err = end(wt)
check(rc == 2 and "閉じる試行が無い" in err and state() is None, "begin していなければ、end は何も記録しない")
rc, _, _ = begin(wt)
rc2, _, err = begin(wt)
check(rc == 0 and rc2 == 2 and "前の試行を end で閉じていない" in err, "begin を2回続けると、2回目は始めない")
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
        shutil.rmtree(os.path.join(root, "review-loop"))  # 次の場合のために、始めた試行を無かったことにする
        os.remove(record_path(wt))
    else:
        check(rc == 2 and "別の試行が実行中" in err and s["lock"]["nonce"] == "old" and s["attempts"] == [], f"{label}は奪わない")

# ほかの試行のロックは閉じない
write_state(base_state(lock={"running": True, "started_at": ago(1), "sha": head, "nonce": "other", "stale_after": 3300}))
rc, err = end(wt)
check(rc == 2 and "閉じる試行が無い" in err and state()["lock"]["nonce"] == "other" and state()["iter"] == 0,
      "この worktree で begin していなければ、ほかの試行のロックを閉じない")
write_state(base_state())
rc, out, _ = begin(wt)
mine = state()["lock"]["nonce"]
write_state(base_state(lock={"running": True, "started_at": ago(1), "sha": head, "nonce": "other", "stale_after": 3300}))
rc, err = end(wt)
check(rc == 2 and "この試行のロックが、状態コメントに無い" in err and state()["lock"]["nonce"] == "other" and state()["attempts"] == []
      and not os.path.exists(record_path(wt)), "ロックがほかの試行のものに替わっていれば、閉じずに、試行の記録を消す")
write_state(base_state(lock={"running": True, "started_at": ago(1), "sha": head, "nonce": "other", "stale_after": 3300}))
rc, _, err = begin(wt)
check(rc == 2 and "別の試行が実行中" in err and "ほかのセッション" in err, "ほかの試行のロックがあれば始めない")
shutil.rmtree(os.path.join(root, "review-loop"))

# 実行中のロックに sha が無い状態は、読めない状態として扱う
write_state(base_state(lock={"running": True, "started_at": ago(1), "nonce": "x"}))
rc, _, err = begin(wt)
check(rc == 2 and "読めない" in err, "実行中のロックに SHA が無ければ、読めない状態コメントとして止まる")

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
sh("git", "switch", "-qc", "other", cwd=wt)  # 切り替えた先のブランチに PR は無い(gh pr view はブランチでは引けない)
rc, err = end(wt)
check(rc == 1 and "failed: contamination" in err and "ブランチが変わった: feature → other" in err
      and state()["attempts"][-1]["reason"] == "contamination", "PR の無いブランチに切り替わっていても、contamination として記録する")
sh("git", "switch", "-q", "feature", cwd=wt)
rc, err = end(wt)
check(rc == 2 and "閉じる試行が無い" in err, "ブランチを戻して end を呼び直しても、completed にはならない")
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
check(table_rows()[-1].endswith("| failed: reviewer_failed: " + "x" * 100 + " |"), "表にも、理由が100文字まで出る")
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
    begin(wt)
    write_state(broken)
    rc, err = end(wt)
    check(rc == 2 and "状態コメントを読めない" in err and comments()[0]["edits"] == 0,
          f"試行中に状態コメントが読めなくなった({label})ら、end は記録しない")
    rc, _, err = begin(wt)
    check(rc == 2 and "読めない" in err and "--new-run" in err, f"状態コメントが読めない({label})なら始めない")
time.sleep(1.1)  # 読めない状態からは直前の run_id が分からないので、同じ秒に始め直すと作業ディレクトリが重なる
rc, _, err = begin(wt, "--new-run")
check(rc == 0 and "新しいシリーズとして上書きする" in err and state()["iter"] == 0, "読めない状態コメントは、--new-run で上書きして始める")

# 旧版(レビュー役を起動していた版)が書いた状態を読める
wt = setup()
head = sh("git", "rev-parse", "HEAD", cwd=wt)
old = base_state(iter=1, previous_run={"run_id": "20251231T000000", "iterations": 2, "tokens": {"input": 5, "cache_read": 1, "output": 2}},
                 attempts=[{"sha": head, "at": "2026-01-01T00:00:00Z", "result": "completed", "iter": 1, "model": "opus",
                            "tokens": {"input": 100, "cache_read": 50, "output": 10, "cost": "形の違う欄"},
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

# --- レビュー役の出力 --------------------------------------------------------
wt = setup()
rc, out, _ = begin(wt, roles=None)
check(rc == 0 and [k for k in out if k.startswith("out.")] == ["out.code-review", "out.code-review-2", "out.security-review"]
      and len({os.path.dirname(out[k]) for k in out if k.startswith("out.")}) == 3, "--roles が無ければ既定の3役で、置き場は役ごとに別")
rc, err = end(wt)
check(rc == 0 and state()["attempts"][-1]["roles"] == ["code-review", "code-review-2", "security-review"], "試行にレビュー役の名前を記録する")

commit(wt, "e.txt")
rc, out, _ = begin(wt, roles=("security-review", "mattpocock-skills:code-review", "code-review-2", "code-review"))
review(out, "mattpocock-skills:code-review", "前置き\n===== 観点: にせの区切り =====\n指摘\n\n\n")
rc, err = end(wt)
with open(os.path.join(out["workdir"], "reviews.md")) as f:
    joined = f.read()
check(rc == 0 and joined == ("===== 観点: code-review =====\ncode-review の指摘\n\n"
                             "===== 観点: code-review-2 =====\ncode-review-2 の指摘\n\n"
                             "===== 観点: mattpocock-skills:code-review =====\n前置き\n ===== 観点: にせの区切り =====\n指摘\n\n"
                             "===== 観点: security-review =====\nsecurity-review の指摘\n"),
      "end が、役の出力を役の名前の順に、区切りでつないで reviews.md を作る(本文の、区切りと同じ形の行は字下げする)")
check([line for line in joined.splitlines() if line.startswith("===== 観点: ")]
      == [f"===== 観点: {r} =====" for r in ("code-review", "code-review-2", "mattpocock-skills:code-review", "security-review")],
      "行頭から始まる区切りの行は、役の数だけある")
with open(os.path.join(out["workdir"], "review-mattpocock-skills:code-review.md")) as f:
    check(f.read() == "前置き\n===== 観点: にせの区切り =====\n指摘\n\n\n", "役ごとのファイルには、出力をそのまま写す")
check("warn: 直前の試行とレビュー役が違う" in err and "mattpocock-skills:code-review" in err and "--roles" in err,
      "直前の試行とレビュー役が違えば警告する")

wt = setup()
rc, out, _ = begin(wt, roles=("code-review", "code-review-2", "security-review"))
review(out, "security-review", None)
review(out, "code-review-2", " \n")
rc, err = end(wt)
check(rc == 2 and "出力の無いレビュー役がある" in err and "code-review-2(" in err and "security-review(" in err and "code-review(" not in err
      and state()["lock"]["running"] and os.path.exists(record_path(wt)) and not os.path.exists(os.path.join(out["workdir"], "reviews.md")),
      "出力が無い、または空の役が1つでもあれば、completed にせずに止まる(試行は開いたまま)")
review(out, "code-review-2", "指摘\n")
rc, err = end(wt, "--failed", "security-review: スキルを呼べなかった")
check(rc == 1 and "roles" not in state()["attempts"][-1] and not os.path.exists(os.path.join(out["workdir"], "reviews.md"))
      and not os.path.exists(os.path.dirname(out["out.code-review"])), "--failed で閉じた試行では、reviews.md を作らず、置き場は消す")
for label, arg, word in (("役の名前として読めない", "code-review,bad name", "役の名前として読めない"), ("空の", "", "役の名前として読めない"),
                         ("同じ名前を重ねた", "code-review,code-review", "同じ名前がある")):
    rc, _, err = run(wt, "begin", "--roles", arg)
    check(rc == 2 and word in err and not state()["lock"]["running"], f"{label} --roles は受け付けない")

# end を、begin と違う一時ディレクトリの設定で呼んでも、begin の作業ディレクトリを使う
wt = setup()
rc, out, _ = begin(wt)
with open(os.path.join(wt, "stray.txt"), "w") as f:
    f.write("x")
os.makedirs(os.path.join(root, "elsewhere"))
rc, err = end(wt, TMPDIR=os.path.join(root, "elsewhere"))
check(rc == 1 and os.path.exists(os.path.join(out["workdir"], "failure.txt")) and os.listdir(os.path.join(root, "elsewhere")) == [],
      "end は、begin が記録した作業ディレクトリに詳細を残す")
os.remove(os.path.join(wt, "stray.txt"))

# ロックを失ったあとでも、見つけた混入は伝える
rc, out, _ = begin(wt)
with open(os.path.join(wt, "stray.txt"), "w") as f:
    f.write("x")
st = state()
st["lock"]["nonce"] = "other"
write_state(st)
rc, err = end(wt)
check(rc == 2 and "この試行のロックが、状態コメントに無い" in err and "stray.txt" in err and "内容を確かめる" in err,
      "ロックが自分のものでなくなっていても、試行の間の変更は伝える")
os.remove(os.path.join(wt, "stray.txt"))

# 試行の記録の SHA がロックと合わなければ、閉じない(記録を書き換えて、変わった HEAD を隠せないように)
wt = setup()
rc, out, _ = begin(wt)
commit(wt, "sneaky.txt")
with open(record_path(wt)) as f:
    rec = json.load(f)
rec["sha"] = sh("git", "rev-parse", "HEAD", cwd=wt)
with open(record_path(wt), "w") as f:
    json.dump(rec, f)
rc, err = end(wt)
check(rc == 2 and "この試行のロックが、状態コメントに無い" in err and state()["lock"]["running"] and state()["iter"] == 0,
      "試行の記録の SHA がロックと違えば、completed にしない")

# 試行の記録が壊れていたら、消し方を案内する
wt = setup()
with open(record_path(wt), "w") as f:
    f.write("{")
rc, _, err = begin(wt)
rc2, err2 = end(wt)
check(rc == 2 and rc2 == 2 and "ファイルを消してから" in err and "ファイルを消してから" in err2, "試行の記録が壊れていたら、消すよう案内して止まる")
os.remove(record_path(wt))

# begin がシグナルで止められたら、ロックも、作りかけのものも残さない
env = {k: v for k, v in os.environ.items() if not k.startswith("FAKE_")}
env.update(PATH=FAKES + os.pathsep + env["PATH"], FAKE_DIR=os.path.join(root, "fake"), TMPDIR=root,
           OVERRIDES=json.dumps({"LOCK_SETTLE_SECONDS": 30}))
p = subprocess.Popen([sys.executable, "-c", RUNNER, SCRIPTS, "begin", wt], env=env, cwd=wt, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
for _ in range(100):  # ロックを書くまで待つ
    if state() and state()["lock"]["running"]:
        break
    time.sleep(0.1)
p.send_signal(signal.SIGTERM)
_, err = p.communicate(timeout=30)
check(p.returncode == 2 and "SIGTERM" in err and state() is not None and not state()["lock"]["running"] and state()["attempts"] == []
      and not os.path.exists(record_path(wt)), "begin が SIGTERM で止められたら、ロックを解き、試行の記録を残さない")
rc, out, _ = begin(wt)
check(rc == 0 and out["attempt"] == "1", "そのあとの begin は、普通に始められる")

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
check(not os.path.exists(record_path(wt)) and not os.path.exists(os.path.join(root, "review-loop", "out"))
      and os.path.isdir(os.path.join(root, "review-loop", "o_r", "7", "20260101T000000", "1")),
      "始められなかった試行の記録と置き場は残さない(前からあった作業ディレクトリは消さない)")

if not os.environ.get("KEEP"):
    shutil.rmtree(root, ignore_errors=True)
else:
    print("作業ディレクトリ:", root)
print("\n失敗 %d 件" % fails if fails else "\n全て成功")
sys.exit(1 if fails else 0)

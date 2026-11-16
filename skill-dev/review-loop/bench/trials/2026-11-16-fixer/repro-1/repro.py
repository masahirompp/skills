"""偽の claude / gh(対象のルートの skill-dev/review-loop/fakes)で iterate を流し、起動したレビュー役の数と、
作業ディレクトリに残った review-*.result.md の数を比べる。名前が重なると、出力ファイルと結果が上書きされて減る。
守られている = 起動前に終了コード2で断る(レビュー役を1つも起動しない)か、起動した数だけ別々の出力が残る。"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

target = os.path.abspath(sys.argv[1])
scripts = os.path.join(target, "skills/review-loop/scripts")
fakes = os.path.join(target, "skill-dev/review-loop/fakes")
here = os.path.dirname(os.path.abspath(__file__))
RUNNER = """
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
import review_loop as r
r.LOCK_SETTLE_SECONDS = 0
r.POLL_SECONDS = 0.1
sys.argv = ["review_loop.py"] + sys.argv[2:]
sys.exit(r.main())
"""


def sh(*args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def case(label, skills, flags, reject_ok=True):
    root = os.path.realpath(tempfile.mkdtemp(prefix="run.", dir=here))
    try:
        os.makedirs(os.path.join(root, "fake"))
        sh("git", "init", "-q", "--bare", "-b", "main", os.path.join(root, "origin.git"))
        wt = os.path.join(root, "wt")
        sh("git", "clone", "-q", os.path.join(root, "origin.git"), wt)
        for k, v in (("user.name", "t"), ("user.email", "t@example.com")):
            sh("git", "config", k, v, cwd=wt)
        with open(os.path.join(wt, "a.txt"), "w") as f:
            f.write("a\n")
        sh("git", "add", "-A", cwd=wt)
        sh("git", "commit", "-qm", "init", cwd=wt)
        sh("git", "switch", "-qc", "feature", cwd=wt)
        sh("git", "push", "-q", "origin", "main", "feature", cwd=wt)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("FAKE_", "REVIEW_LOOP", "CLAUDE"))}
        env.update(PATH=fakes + os.pathsep + env["PATH"], FAKE_DIR=os.path.join(root, "fake"), TMPDIR=root,
                   FAKE_SKILLS=skills, PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([sys.executable, "-B", "-c", RUNNER, scripts, "iterate", wt, *flags],
                           env=env, capture_output=True, text=True, timeout=60)
        try:
            with open(os.path.join(root, "fake", "calls.jsonl")) as f:
                launched = sum(json.loads(line)["kind"] == "review" for line in f)
        except FileNotFoundError:
            launched = 0
        outputs = len(glob.glob(os.path.join(root, "review-loop", "**", "review-*.result.md"), recursive=True))
        last = (p.stderr.strip().splitlines() or [""])[-1][:160]
        if p.returncode == 2 and launched == 0:
            ok, what = reject_ok, "起動前に断った"
        elif p.returncode == 0 and launched == outputs == len(flags) // 2:
            ok, what = True, "全ての役の出力が別々に残った"
        else:
            ok, what = False, "名前が重なり、出力が減った" if outputs < launched else "想定外の終わり方"
        print(f"{'ok  ' if ok else 'FAIL'} {label}: rc={p.returncode} 起動したレビュー役={launched} "
              f"残った出力={outputs} → {what} | {last}")
        return ok
    finally:
        shutil.rmtree(root, ignore_errors=True)


results = [
    case("指摘の箇所: 同じスキル focus を2つ + --focus 2つ(focus-2 が重なる)", "focus",
         ["--perspective", "focus", "--perspective", "focus", "--focus", "a", "--focus", "b"]),
    case("横展開: スキル focus-1 を1つ + --focus 1つ(focus-1 が重なる)", "focus-1",
         ["--perspective", "focus-1", "--focus", "a"]),
    case("対照: スキル focus を1つ + --focus 1つ(重ならない。断ってはいけない)", "focus",
         ["--perspective", "focus", "--focus", "a"], reject_ok=False),
    case("対照: code-review を2つ + --focus 2つ(重ならない。断ってはいけない)", "code-review",
         ["--perspective", "code-review high {pr}", "--perspective", "code-review high {pr}", "--focus", "a", "--focus", "b"],
         reject_ok=False),
]
sys.exit(0 if all(results) else 1)

"""正解の一覧が無い題材(不具合0件)だけの結果を作り、repeat.py を流す。
守られている = 例外で落ちず(Traceback が無い)、不具合が0件だという説明を出して終わる。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

target = os.path.abspath(sys.argv[1])
here = os.path.dirname(os.path.abspath(__file__))
out = tempfile.mkdtemp(prefix="results.", dir=here)
try:
    case = "repro-no-answers"  # answers/<題材>.json が無いので、正解は0件
    assert not os.path.exists(os.path.join(target, "skill-dev/review-loop/bench/answers", case + ".json"))
    for n in (1, 2):
        d = os.path.join(out, case, "code-review", str(n))
        os.makedirs(d)
        with open(os.path.join(d, "meta.json"), "w") as f:
            json.dump({"case": case, "config": "code-review", "trial": n, "cost_usd": 0.1, "duration_s": 10}, f)
        with open(os.path.join(d, "score.json"), "w") as f:
            json.dump({"bugs": [], "extras": []}, f)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, "-B", os.path.join(target, "skill-dev/review-loop/bench/repeat.py"), out],
                       capture_output=True, text=True, env=env, timeout=60)
    text = p.stdout + p.stderr
    crashed = "Traceback" in text
    explained = "0件" in text or "0 件" in text
    ok = not crashed and explained
    last = (p.stderr.strip().splitlines() or [""])[-1][:200]
    print(f"{'ok  ' if ok else 'FAIL'} repeat.py(不具合0件の結果): rc={p.returncode} 例外={'あり' if crashed else 'なし'} "
          f"0件の説明={'あり' if explained else 'なし'} | {last}")
    sys.exit(0 if ok else 1)
finally:
    shutil.rmtree(out, ignore_errors=True)

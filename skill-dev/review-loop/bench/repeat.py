#!/usr/bin/env python3
"""同じ構成を繰り返して合わせた場合と、別の構成を足した場合を比べる。

    repeat.py <結果の置き場> [繰り返す構成(既定は code-review)]

combos.py は「同じ番号の試行を、構成の数だけ並列に回したもの」を1反復として数えるので、同じ構成を2回流して
合わせた場合が出ない。ここでは、繰り返す構成の試行を2つずつ(と全部)合わせたものと、その構成の試行1つに
ほかの構成の試行1を足したものを並べる。数え方は combos.py と同じ(検出は、どれかが検出すれば検出。時間は
並列なので最長。費用と余計な指摘は合計で、同じ指摘の重なりは、まとまりで1件)。新しく子を起動しない。
"""
import collections
import itertools
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
import score  # noqa: E402

out = os.path.abspath(sys.argv[1])
target = sys.argv[2] if len(sys.argv) > 2 else "code-review"
rows = score.trials(out)
configs = [c for c in score.bench.CONFIGS if any(m["config"] == c for _, m in rows)]
cases = sorted({m["case"] for _, m in rows})
bugs = [(c, b["id"]) for c in cases for b in score.answers(c)["bugs"] if b.get("scope", "in") == "in"]
trials = sorted({m["trial"] for _, m in rows if m["config"] == target})
if len(trials) < 2:
    sys.exit(f"{target} の試行が2つ以上要る")

det = collections.defaultdict(set)      # (構成, 試行) -> 検出した不具合
extra = collections.defaultdict(set)    # (構成, 試行) -> 余計な指摘のまとまり
cost = collections.defaultdict(float)   # (構成, 試行) -> 全題材の費用
dur = collections.defaultdict(dict)     # (構成, 試行) -> {題材: 秒}
cluster_of, klass = {}, {}
for case in cases:
    data = score.read_json(os.path.join(out, "_clusters", case + ".json"))
    for c in (data or {}).get("clusters", []):
        k = c.get("class", "unclassified")
        klass[c["id"]] = ("real_" + c.get("scope", "in")) if k == "real" else k
        for m in c["members"]:
            mm = data["members"][m]
            cluster_of[(os.path.join(out, mm["dir"]), mm["n"])] = c["id"]
for d, m in rows:
    key = (m["config"], m["trial"])
    cost[key] += m.get("cost_usd") or 0
    dur[key][m["case"]] = m.get("duration_s") or 0
    s = score.read_json(os.path.join(d, "score.json"))
    if not s:
        continue
    det[key] |= {(m["case"], b["id"]) for b in s["bugs"] if b["verdict"] == "detected"}
    extra[key] |= {cluster_of.get((d, e["n"]), f"{d}#{e['n']}") for e in s["extras"]}


def row(name, keys):
    found = set().union(*[det[k] for k in keys])
    e = set().union(*[extra[k] for k in keys])
    real = sum(klass.get(x, "").startswith("real") for x in e)
    minutes = sum(max(dur[k].get(c, 0) for k in keys) for c in cases) / len(cases) / 60
    usd = sum(cost[k] for k in keys) / len(cases)
    print(f"| {name} | {len(found)}({100 * len(found) / len(bugs):.0f}%) | {(len(e) - real) / len(cases):.1f} | "
          f"{real / len(cases):.1f} | {minutes:.1f}分 | ${usd:.2f} |")


print(f"## {target} を繰り返した場合と、ほかの構成を足した場合(不具合は {len(bugs)} 件、題材は {len(cases)} 件)\n")
print("| 組み合わせ(構成#試行) | 検出した不具合 | 本物でない余計な指摘 / 題材 | 本物の余計な指摘 / 題材 | 時間 / 題材 | 費用 / 題材 |")
print("|---|---|---|---|---|---|")
for n in trials:
    row(f"{target}#{n}", [(target, n)])
for a, b in itertools.combinations(trials, 2):
    row(f"{target}#{a} + {target}#{b}", [(target, a), (target, b)])
row(" + ".join(f"{target}#{n}" for n in trials), [(target, n) for n in trials])
others = [c for c in configs if c != target and (c, 1) in cost]
for r in (1, 2):
    for combo in itertools.combinations(others, r):
        for n in trials:
            row(f"{target}#{n} + " + " + ".join(f"{c}#1" for c in combo), [(target, n)] + [(c, 1) for c in combo])
for a, b in itertools.combinations(trials, 2):
    for c in others:
        row(f"{target}#{a} + {target}#{b} + {c}#1", [(target, a), (target, b), (c, 1)])

everything = set().union(*[det[(target, n)] for n in trials])
print(f"\n## {target} の全ての試行を合わせても見つからず、ほかの構成の試行1が見つけた不具合\n")
for c in others:
    only = sorted(det[(c, 1)] - everything)
    print(f"- {c}: {', '.join(b for _, b in only) if only else 'なし'}")

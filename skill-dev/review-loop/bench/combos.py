#!/usr/bin/env python3
"""構成の組み合わせごとに、1反復で見つかる不具合の数、余計な指摘、時間、費用を出す。構成どうしの差の揺れも出す。

    combos.py <結果の置き場>

1反復 = 同じ番号の試行を、組み合わせた構成の数だけ並列に回したもの、として数える。構成によって試行の数が違うときは、
組み合わせた構成の全てにある番号の試行だけを数える。検出は、組み合わせのどれかが検出すれば検出。時間は並列なので最長、費用と余計な指摘は合計(同じ指摘の重なりは、まとまりで1件に数える)。
差の揺れは、不具合を単位にしたブートストラップ(同じ不具合の3回は独立でないので、不具合ごとまとめて引き直す)。
"""
import collections
import itertools
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
import score  # noqa: E402

out = os.path.abspath(sys.argv[1])
rows = score.trials(out)
configs = [c for c in score.bench.CONFIGS if any(m["config"] == c for _, m in rows)]
cases = sorted({m["case"] for _, m in rows})
bugs = [(c, b["id"]) for c in cases for b in score.answers(c)["bugs"] if b.get("scope", "in") == "in"]
ran = {c: {m["trial"] for _, m in rows if m["config"] == c} for c in configs}  # 構成 -> 回した試行の番号

det = collections.defaultdict(set)      # (構成, 試行) -> 検出した不具合
extra = collections.defaultdict(set)    # (構成, 試行) -> 余計な指摘のまとまり(分類つき)
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


def measure(combo):
    found, noise, real, t, usd = [], [], [], [], []
    for n in sorted(set.intersection(*[ran[c] for c in combo])):
        f = set().union(*[det[(c, n)] for c in combo])
        e = set().union(*[extra[(c, n)] for c in combo])
        found.append(len(f))
        real.append(sum(klass.get(x, "").startswith("real") for x in e))
        noise.append(len(e) - real[-1])
        t.append(sum(max(dur[(c, n)].get(case, 0) for c in combo) for case in cases) / len(cases) / 60)
        usd.append(sum(cost[(c, n)] for c in combo) / len(cases))
    return found, noise, real, t, usd


def mean(xs):
    return sum(xs) / len(xs)


print(f"## 構成の組み合わせ(1反復あたり。不具合は {len(bugs)} 件、題材は {len(cases)} 件)\n")
print("| 組み合わせ | 検出した不具合(試行ごと) | 平均 | 本物でない余計な指摘 / 題材 | 本物の余計な指摘 / 題材 | 時間 / 題材 | 費用 / 題材 |")
print("|---|---|---|---|---|---|---|")
table = []
for r in range(1, len(configs) + 1):
    for combo in itertools.combinations(configs, r):
        f, n, re_, t, u = measure(combo)
        table.append((mean(f), combo, f, n, re_, t, u))
for _, combo, f, n, re_, t, u in sorted(table, key=lambda x: (len(x[1]), -x[0])):
    print(f"| {' + '.join(combo)} | {'、'.join(map(str, f))} | {mean(f):.1f}({100 * mean(f) / len(bugs):.0f}%) | "
          f"{mean(n) / len(cases):.1f} | {mean(re_) / len(cases):.1f} | {mean(t):.1f}分 | ${mean(u):.2f} |")

# 構成どうしの差(検出率の差)の 95% の幅。不具合を単位に引き直す
rate = {c: {b: sum(b in det[(c, n)] for n in ran[c]) / len(ran[c]) for b in bugs} for c in configs}
rng = random.Random(1)
print("\n## 構成どうしの検出率の差(不具合を単位にしたブートストラップ、95% の幅)\n")
print("| 比べる構成 | 差(ポイント) | 95% の幅 | 0 をまたぐか |")
print("|---|---|---|---|")
for a, b in itertools.combinations(configs, 2):
    diffs = []
    for _ in range(4000):
        sample = [rng.choice(bugs) for _ in bugs]
        diffs.append(100 * (mean([rate[a][x] for x in sample]) - mean([rate[b][x] for x in sample])))
    diffs.sort()
    lo, hi = diffs[100], diffs[3899]
    d = 100 * (mean(list(rate[a].values())) - mean(list(rate[b].values())))
    print(f"| {a} − {b} | {d:+.0f} | {lo:+.0f} 〜 {hi:+.0f} | {'またぐ(差があるとは言えない)' if lo <= 0 <= hi else 'またがない'} |")

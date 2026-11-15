#!/usr/bin/env python3
"""レビューの指摘を実行で確かめる「検証役」を試し、本物の不具合を誤って落とす率を測る。

    verify.py run    <出力先> <結果の置き場>... [--per-bug 2] [--jobs 4]
    verify.py report <出力先>

review-loop に「レビュー役の指摘 → 検証役が実行で確かめる → 通ったものだけ残す」という段を足す案の、下調べ。
検証役に渡すのは、レビュー役が書いた指摘の文面(レビューの出力から、その指摘の前後を切り出したもの)だけ。
正解と一致した指摘(本物と分かっている)と、正解に無い指摘(分類済み)を混ぜて渡し、検証役にはどちらかを伝えない。

- 正解と一致した指摘が「起きなかった」になる率 = 検証の段が本物を落とす率
- 正解に無い指摘について、分類役(score.py classify)の分類と突き合わせる

検証役の結論は VERIFY_PROMPT が正。
"""
import argparse
import collections
import json
import os
import random
import re
import shutil
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
import score  # noqa: E402

bench = score.bench
BATCH = 6
VERDICTS = ("reproduced", "not_reproduced", "not_runnable", "no_behavior_impact")
JA = {"reproduced": "再現した", "not_reproduced": "起きなかった", "not_runnable": "実行では示せない",
      "no_behavior_impact": "挙動に関わらない"}

VERIFY_PROMPT = """\
このリポジトリの PR(main から今のブランチ HEAD への差分)に対して、レビュー役が挙げた指摘を渡す。
指摘は、コードを読んだだけの仮説で、誤っていることもある。1つずつ、実行して確かめる。修正はしない。

あなた専用の複製なので、このディレクトリの中でファイルを作り、コマンドを実行して構わない。再現は、テストの中、
一時ディレクトリに作ったリポジトリなど、隔離した場所で行う。このディレクトリの外のファイルは変えない。commit と push はしない。

結論(verdict)は次の4つ。
- reproduced: 指摘どおりのことが起きるのを、実行して見た(失敗するテスト、再現スクリプト、コマンドの出力)
- not_reproduced: 指摘が起きると言っている条件を作って実行したが、起きなかった。条件を作れずに試したもの、
  指摘とは違う条件で試したものは、これにしない
- not_runnable: 実行では示せない。文書やプロンプトの書き方、外部のサービスの挙動、狙って起こせないタイミング、
  この環境では作れない条件(別の OS、サンドボックスなど)が当たる。テストを書くのが手間、は理由にならない。
  この結論のときは、コードや文面を追って、指摘が成り立つか(traced: holds / does_not_hold / unclear)も書く
- no_behavior_impact: 指摘の内容は事実だが、挙動に関わらない(命名、コメント、書き方、構造の好み、テストが無いという指摘、
  将来の変更があって初めて問題になるもの)

commands には、実行したコマンドか書いたテストの要点を書く(実行していなければ空文字列)。
evidence には、出力の要点と、そこから分かることを書く。not_runnable なら、実行で示せない理由と、追ったファイルと行。
"""

SCHEMA = {
    "type": "object", "required": ["items"], "additionalProperties": False,
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "required": ["id", "verdict", "traced", "commands", "evidence"], "additionalProperties": False,
        "properties": {"id": {"type": "string"}, "verdict": {"enum": list(VERDICTS)},
                       "traced": {"enum": ["holds", "does_not_hold", "unclear", "na"]},
                       "commands": {"type": "string"}, "evidence": {"type": "string"}}}}},
}


EXTRACT_PROMPT = """\
コードレビューの出力と、その中の1つの指摘からの引用を渡す。その引用を含む**指摘1件だけ**の全文を、レビューの出力から
一字一句そのまま抜き出す。ツールは使わない。

- 指摘の見出しや箇条書きの先頭から、その指摘の終わり(次の指摘や次の見出しの手前)までを抜き出す
- 隣の指摘、前置き、まとめは含めない
- 言い換えや要約をしない。レビューの出力に連続して現れる文字列だけを返す
"""
EXTRACT_SCHEMA = {"type": "object", "required": ["text"], "additionalProperties": False,
                  "properties": {"text": {"type": "string"}}}


def extract(review, quote, cwd):
    """レビューの出力から、引用を含む指摘1件の全文を抜き出す。前後を機械的に切り出すと隣の指摘が混ざり、検証役が
    隣の指摘まで確かめてしまうので、LLM に抜き出させ、出力に実在することを照合する。照合できなければ引用だけを使う。"""
    try:
        out, _ = score.ask(EXTRACT_PROMPT + "\n\n===== 引用 =====\n" + quote + "\n\n===== レビューの出力 =====\n" + review,
                           EXTRACT_SCHEMA, cwd)
    except Exception:
        return quote
    text = out["text"].strip()
    return text if score.quote_ok(text, review) and score.squash(quote)[:30] in score.squash(text) else quote


def collect(outs, per_bug):
    """{題材: [項目]}。項目は、正解と一致した指摘(kind=seeded)と、同じ数までの正解に無い指摘(kind=extra)。"""
    seeded, extras = collections.defaultdict(list), collections.defaultdict(list)
    for out in outs:
        klass = {}
        for case in os.listdir(os.path.join(out, "_clusters")) if os.path.isdir(os.path.join(out, "_clusters")) else []:
            data = score.read_json(os.path.join(out, "_clusters", case))
            for c in data["clusters"]:
                for m in c["members"]:
                    mm = data["members"][m]
                    klass[(os.path.join(out, mm["dir"]), mm["n"])] = (c.get("class"), c.get("scope"), c["id"])
        for d, meta in score.trials(out):
            s = score.read_json(os.path.join(d, "score.json"))
            if not s:
                continue
            with open(os.path.join(d, "result.md"), encoding="utf-8") as f:
                review = f.read()
            for b in s["bugs"]:
                if b["verdict"] == "detected" and b["quote_ok"]:
                    seeded[(meta["case"], b["id"])].append({"kind": "seeded", "bug": b["id"], "config": meta["config"],
                                                            "from": os.path.relpath(d, HERE), "quote": b["quote"]})
            for e in s["extras"]:
                k = klass.get((d, e["n"]))
                if k and k[0] and e["quote_ok"]:
                    extras[meta["case"]].append({"kind": "extra", "class": k[0], "scope": k[1], "cluster": k[2],
                                                 "config": meta["config"], "from": os.path.relpath(d, HERE),
                                                 "quote": e["quote"]})
    rng = random.Random(7)
    by_case = collections.defaultdict(list)
    for (case, _), items in sorted(seeded.items()):
        rng.shuffle(items)
        picked, seen = [], set()
        for it in items:  # 構成が重ならないように選ぶ
            if it["config"] not in seen and len(picked) < per_bug:
                picked.append(it)
                seen.add(it["config"])
        by_case[case] += picked
    for case, items in by_case.items():
        pool, seen = [], set()
        for e in rng.sample(extras[case], len(extras[case])):
            if e["cluster"] not in seen:  # 同じ指摘を2回入れない
                seen.add(e["cluster"])
                pool.append(e)
        items += pool[:len(items)]
        rng.shuffle(items)
        for i, it in enumerate(items, 1):
            it["id"] = f"{case}/v{i}"
    empty = tempfile.mkdtemp(prefix="rb-score-")

    def fill(it):
        with open(os.path.join(HERE, it["from"], "result.md"), encoding="utf-8") as f:
            it["text"] = extract(f.read(), it["quote"], empty)
        it["extracted"] = it["text"] != it["quote"]

    try:
        score.pool(6, fill, [it for items in by_case.values() for it in items])
    finally:
        shutil.rmtree(empty, ignore_errors=True)
    return by_case


def cmd_run(args):
    os.makedirs(args.dest, exist_ok=True)
    plan_path = os.path.join(args.dest, "items.json")
    plan = score.read_json(plan_path)
    if plan is None:
        plan = collect([os.path.abspath(o) for o in args.outs], args.per_bug)
        score.write_json(plan_path, plan)
    done_path = os.path.join(args.dest, "verdicts.json")
    done = score.read_json(done_path, {})
    lock = threading.Lock()
    root = os.path.realpath(tempfile.mkdtemp(prefix="rb-"))
    work = []
    for case, items in sorted(plan.items()):
        todo = [it for it in items if it["id"] not in done]
        work += [(case, todo[i:i + BATCH]) for i in range(0, len(todo), BATCH)]
    templates = {}
    try:
        for case in sorted({w[0] for w in work}):
            templates[case] = os.path.join(root, "tpl", case)
            bench.build(bench.load_case(case), templates[case])

        def one(item):
            case, items = item
            listing = [{"id": it["id"], "指摘": it["text"]} for it in items]
            trial, repo = bench.clone_trial(templates[case], root, bench.load_case(case))
            try:
                out, cost = score.ask(VERIFY_PROMPT + "\n\n===== 指摘 =====\n" + json.dumps(listing, ensure_ascii=False, indent=1),
                                      SCHEMA, repo, tools=True, system=bench.OWN_COPY)
            finally:
                shutil.rmtree(trial, ignore_errors=True)
            with lock:
                for v in out["items"]:
                    if any(v["id"] == it["id"] for it in items):
                        done[v["id"]] = {**v, "cost_usd": cost / len(items)}
                score.write_json(done_path, done)
            print(f"verified {case}: {len(out['items'])} 件", file=sys.stderr, flush=True)

        score.pool(args.jobs, one, work)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    cmd_report(args)


def cmd_report(args):
    plan = score.read_json(os.path.join(args.dest, "items.json"))
    done = score.read_json(os.path.join(args.dest, "verdicts.json"), {})
    items = [dict(it, case=case, **{"v": done.get(it["id"])}) for case, its in sorted(plan.items()) for it in its]
    got = [it for it in items if it["v"]]
    kinds = {c: bench.load_case(c)["kind"] for c in plan}
    L = ["# 検証役の試し", "", f"渡した指摘 {len(items)} 件のうち、結論が出たもの {len(got)} 件。"
         f"費用 ${sum(it['v']['cost_usd'] for it in got):.2f}(API 換算)。", ""]

    def table(title, rows, key, keys):
        out = [f"## {title}", "", "| | " + " | ".join(JA[v] for v in VERDICTS) + " | 計 |", "|---|" + "---|" * (len(VERDICTS) + 1)]
        for k in keys:
            sub = [r for r in rows if key(r) == k]
            if sub:
                c = collections.Counter(r["v"]["verdict"] for r in sub)
                out.append(f"| {k} | " + " | ".join(str(c[v]) for v in VERDICTS) + f" | {len(sub)} |")
        c = collections.Counter(r["v"]["verdict"] for r in rows)
        out.append("| **計** | " + " | ".join(str(c[v]) for v in VERDICTS) + f" | {len(rows)} |")
        return out + [""]

    seeded = [it for it in got if it["kind"] == "seeded"]
    extra = [it for it in got if it["kind"] == "extra"]
    L += table("正解と一致した指摘(本物と分かっているもの)。題材の種類ごと", seeded, lambda r: kinds[r["case"]],
               sorted(set(kinds.values())))
    nr = [it for it in seeded if it["v"]["verdict"] == "not_runnable"]
    c = collections.Counter(it["v"]["traced"] for it in nr)
    L += [f"「実行では示せない」{len(nr)} 件を、検証役がコードや文面で追った結果: 成り立つ {c['holds']}、"
          f"成り立たない {c['does_not_hold']}、分からない {c['unclear']}。", ""]
    L += table("正解に無い指摘。分類役の分類ごと", extra, lambda r: score.CLASS_JA.get(r["class"], r["class"]),
               [score.CLASS_JA[k] for k in score.CLASSES])
    L += ["## 本物なのに落ちた、または落ちかけたもの", ""]
    for it in seeded:
        v = it["v"]
        if v["verdict"] in ("not_reproduced", "no_behavior_impact") or (v["verdict"] == "not_runnable" and v["traced"] != "holds"):
            L += [f"- `{it['id']}` {it['bug']}({it['config']})→ **{JA[v['verdict']]}**"
                  + (f"・追った結果 {v['traced']}" if v["verdict"] == "not_runnable" else ""),
                  f"  - 根拠: {v['evidence'][:600]}"]
    L += ["", "## 全件", ""]
    for it in got:
        v = it["v"]
        tag = it["bug"] if it["kind"] == "seeded" else f"正解に無い・{score.CLASS_JA.get(it['class'], it['class'])}"
        L += [f"- `{it['id']}` [{tag}] {it['config']} → **{JA[v['verdict']]}**"
              + (f"({v['traced']})" if v["verdict"] == "not_runnable" else ""),
              f"  - 指摘: {' '.join(it['text'].split())[:240]}", f"  - 根拠: {' '.join(v['evidence'].split())[:400]}"]
    path = os.path.join(args.dest, "report.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("dest")
    r.add_argument("outs", nargs="+")
    r.add_argument("--per-bug", type=int, default=2)
    r.add_argument("--jobs", type=int, default=4)
    r.set_defaults(fn=cmd_run)
    p = sub.add_parser("report")
    p.add_argument("dest")
    p.set_defaults(fn=cmd_report)
    args = ap.parse_args()
    args.dest = os.path.abspath(args.dest)
    args.fn(args)


if __name__ == "__main__":
    main()

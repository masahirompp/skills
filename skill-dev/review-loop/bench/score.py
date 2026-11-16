#!/usr/bin/env python3
"""bench.py run の結果を採点し、集計する。

    score.py score    <結果の置き場> [--jobs 4]   試行ごとに、埋め込んだ不具合の検出と、それ以外の指摘を取り出す
    score.py cluster  <結果の置き場>              題材ごとに、それ以外の指摘を同じものでまとめる
    score.py classify <結果の置き場> [--jobs 3]   まとまりごとに、本物 / 些末 / 誤り / 未確定 を根拠つきで分類する
    score.py report   <結果の置き場>              report.md と scoring-review.md を書く

採点は LLM(`claude -p`)に任せる。基準はこのファイルの SCORE_PROMPT と CLASSIFY_PROMPT が正。
採点役には、どの構成の出力かを渡さない。判定には、レビューの出力からの引用を必ず付けさせ、引用が出力に
実在するかはこのスクリプトが照合する(quote_ok)。抜き取りで確かめるための一覧が scoring-review.md。
どの段も、済んだものは飛ばすので、途中で止めても同じコマンドで続きから回せる。
"""
import argparse
import collections
import concurrent.futures
import json
import os
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
import bench  # noqa: E402

rl = bench.rl
ANSWERS = os.path.join(HERE, "answers")
SCORED = ("ok", "denied")  # 出力のある試行。denied は本番なら止まる拒否があったもので、集計では分ける
CLASSES = ("real", "trivial", "wrong", "undetermined")
CLASS_JA = {"real": "本物", "trivial": "些末", "wrong": "誤り", "undetermined": "未確定"}

SCORE_PROMPT = """\
コードレビューの出力を採点する。ツールは使わず、渡された文章だけで判断する。

入力は2つ。
1. 正解の一覧: レビュー対象の差分に含まれると分かっている不具合(無いこともある)
2. レビューの出力

## 仕事1: 正解の不具合ごとに、レビューが検出したかを判定する

- detected: レビューの指摘が、正解と同じ場所(ファイルと、関数や処理)を指し、原因か起きる条件が正解と一致する。
  正解の detect_criteria を満たすこと。言い回しや影響の見積もりが違っていても構わない
- partial: 場所は合っているが、原因が曖昧か、起きる結果だけを述べている。または、原因は合っているが場所が違う
- missed: 上のどちらでもない。場所が合っていても、原因が正解と違うなら missed

quote には、判定の根拠にしたレビューの出力の一節を、一字一句そのまま(連続した200文字以内)で入れる。missed なら空文字列。
reason には、判定の理由を1文で書く。

## 仕事2: 正解に無い指摘を、全て取り出す

レビューが「問題」「懸念」「改善すべき点」として挙げたもののうち、仕事1で detected か partial に数えなかったものを、
1つの問題につき1件ずつ取り出す。

- 同じ問題が要約と本文の両方に出ていたら、1件にする
- 正解の不具合と同じ原因を、別の角度から述べただけの指摘(同じ原因から出る別の症状、その不具合の直し方の提案)は、
  その不具合の一部として扱い、取り出さない。その不具合を検出できるテストが無い、という指摘は取り出す
- 褒めている箇所、確認して問題が無かったという報告、作業の経過、対象の説明は取り出さない
- レビューが自分で「問題なし」「誤検知」「報告しない」と結論したものは取り出さない
- 質問の形でも、問題の疑いを述べているなら取り出す

各件に、location(レビューが書いた場所。無ければ空文字列)、summary(何が問題だと言っているかを1文で)、
quote(レビューの出力の一節を一字一句そのまま、連続した200文字以内)を付ける。
"""

SCORE_SCHEMA = {
    "type": "object", "required": ["bugs", "extras"], "additionalProperties": False,
    "properties": {
        "bugs": {"type": "array", "items": {
            "type": "object", "required": ["id", "verdict", "quote", "reason"], "additionalProperties": False,
            "properties": {"id": {"type": "string"}, "verdict": {"enum": ["detected", "partial", "missed"]},
                           "quote": {"type": "string"}, "reason": {"type": "string"}}}},
        "extras": {"type": "array", "items": {
            "type": "object", "required": ["location", "summary", "quote"], "additionalProperties": False,
            "properties": {"location": {"type": "string"}, "summary": {"type": "string"}, "quote": {"type": "string"}}}},
    },
}

CLUSTER_PROMPT = """\
同じ差分に対する複数のコードレビューから取り出した指摘の一覧を渡す。同じ問題を指している指摘を、1つのまとまりにする。
ツールは使わない。

- 「同じ問題」とは、同じ場所の、同じ原因についての指摘。場所が同じでも原因が違えば別のまとまり
- 迷ったら分ける(別のまとまりにする)
- 全ての id を、ちょうど1つのまとまりに入れる
- title には、その問題を1文で書く。location には、代表的な場所を書く
"""

CLUSTER_SCHEMA = {
    "type": "object", "required": ["clusters"], "additionalProperties": False,
    "properties": {"clusters": {"type": "array", "items": {
        "type": "object", "required": ["title", "location", "members"], "additionalProperties": False,
        "properties": {"title": {"type": "string"}, "location": {"type": "string"},
                       "members": {"type": "array", "items": {"type": "string"}}}}}},
}

CLASSIFY_PROMPT = """\
このリポジトリの、main から今のブランチ(HEAD)への差分に対して、コードレビューが挙げた指摘を渡す。
指摘の1つ1つについて、正しいかを確かめて分類する。指摘は仮説で、誤っていることもある。

あなた専用の複製なので、このディレクトリの中でファイルを作り、コマンドを実行して構わない。実行して確かめられるものは、
実行して確かめる(失敗するテスト、再現スクリプト、コマンドの出力)。実行は、このディレクトリと一時ディレクトリの中だけで行う。
このディレクトリの外のファイルは変えない。commit と push はしない。

分類(class):
- real: 挙動の問題(誤った結果、失敗、データの消失、セキュリティ、文書とコードの食い違いで利用者が誤るもの)で、
  実行して再現できたか、コードで起きる経路を最後まで追えた
- trivial: 挙動に関わらない(命名、コメント、書き方、重複、構造の好み、テストが無いという指摘、将来の変更があって
  初めて問題になるもの)。指摘の内容が事実でも、挙動に関わらなければこちら
- wrong: 指摘の主張が、コードか実行の結果と食い違う(起きると言っていることが起きない、コードを読み違えている)
- undetermined: 確かめられなかった(必要な環境が無い、狙って起こせないタイミングなど)

範囲(scope): real のときだけ判断する。
- in: main からの差分が原因で起きる(差分の目的の直し残しを含む)
- out: main の時点でも同じように起きる
- na: real 以外

evidence には、分類の根拠を書く。実行したなら、コマンドと出力の要点。実行していないなら、該当するファイルと行、
そこから分かること、実行しなかった理由。ran には、実行して確かめたなら true を入れる。
"""

CLASSIFY_SCHEMA = {
    "type": "object", "required": ["items"], "additionalProperties": False,
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "required": ["id", "class", "scope", "ran", "evidence"], "additionalProperties": False,
        "properties": {"id": {"type": "string"}, "class": {"enum": list(CLASSES)},
                       "scope": {"enum": ["in", "out", "na"]}, "ran": {"type": "boolean"},
                       "evidence": {"type": "string"}}}}},
}


# --- 共通 --------------------------------------------------------------------
def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


MODEL = bench.MODEL  # 採点役と分類役のモデル。main が --model で差し替える


def ask(prompt, schema, cwd, tools=False, system=None, timeout=45 * 60):
    """claude -p に JSON で答えさせ、(答え, 費用) を返す。プロンプトは標準入力で渡す。"""
    args = ["claude", "-p", "--model", MODEL, "--output-format", "json", "--json-schema", json.dumps(schema)]
    if not tools:
        args += ["--tools", ""]
    if system:
        args += ["--append-system-prompt", system]
    r = subprocess.run(args, cwd=cwd, input=prompt, capture_output=True, text=True, timeout=timeout, env=rl.child_env())
    try:
        data = json.loads(r.stdout)
    except ValueError:
        raise RuntimeError(f"採点役の出力を読めない(rc={r.returncode}): {r.stdout[-500:]} {r.stderr[-500:]}")
    if isinstance(data, list):  # 版によっては、メッセージの配列で返る
        data = next((m for m in reversed(data) if isinstance(m, dict) and m.get("type") == "result"), {})
    out = data.get("structured_output")
    if data.get("is_error"):  # 利用枠の上限など
        raise RuntimeError(f"採点役が失敗した: {str(data.get('result'))[:300]}")
    if out is None:
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(data.get("result") or "").strip())
        try:
            out = json.loads(text)
        except ValueError:
            raise RuntimeError(f"採点役が JSON を返さなかった: {text[:500]}")
    return out, data.get("total_cost_usd") or 0


def trials(out):
    """結果の置き場にある試行を (ディレクトリ, meta) で返す。"""
    found = []
    for case in sorted(os.listdir(out)):
        cdir = os.path.join(out, case)
        if not os.path.isdir(cdir) or case.startswith("_"):
            continue
        for config in sorted(os.listdir(cdir)):
            if not os.path.isdir(os.path.join(cdir, config)):  # .DS_Store など
                continue
            for n in sorted(os.listdir(os.path.join(cdir, config))):
                d = os.path.join(cdir, config, n)
                meta = read_json(os.path.join(d, "meta.json")) if os.path.isdir(d) else None
                if meta:
                    found.append((d, meta))
    return found


def answers(case):
    return read_json(os.path.join(ANSWERS, case + ".json"), {"case": case, "bugs": []})


def squash(s):
    return re.sub(r"\s+", "", s)


def quote_ok(quote, text):
    """引用がレビューの出力に実在するか。空白と改行の違いは無視する。"""
    return bool(quote.strip()) and squash(quote) in squash(text)


def pool(jobs, fn, items):
    with concurrent.futures.ThreadPoolExecutor(jobs) as ex:
        for f in concurrent.futures.as_completed([ex.submit(fn, i) for i in items]):
            try:
                f.result()
            except Exception as e:
                print(f"warn: {type(e).__name__}: {e}", file=sys.stderr, flush=True)


# --- score -------------------------------------------------------------------
def cmd_score(args):
    empty = tempfile.mkdtemp(prefix="rb-score-")

    def one(item):
        d, meta = item
        path = os.path.join(d, "score.json")
        if meta["status"] not in SCORED or os.path.exists(path):
            return
        with open(os.path.join(d, "result.md"), encoding="utf-8") as f:
            review = f.read()
        key = answers(meta["case"])
        bugs = [{k: b[k] for k in ("id", "file", "where", "summary", "mechanism", "trigger", "detect_criteria")}
                for b in key["bugs"] if b.get("scope", "in") == "in"]
        prompt = (SCORE_PROMPT + "\n\n===== 正解の一覧 =====\n" + json.dumps(bugs, ensure_ascii=False, indent=1)
                  + "\n\n===== レビューの出力 =====\n" + review + "\n===== ここまで =====\n")
        out, cost = ask(prompt, SCORE_SCHEMA, empty)
        got = {b["id"]: b for b in out["bugs"]}
        score = {"cost_usd": cost, "bugs": [], "extras": []}
        for b in bugs:
            g = got.get(b["id"]) or {"verdict": "missed", "quote": "", "reason": "採点役が判定を返さなかった"}
            ok = g["verdict"] == "missed" or quote_ok(g["quote"], review)
            score["bugs"].append({"id": b["id"], "verdict": g["verdict"], "quote": g["quote"], "reason": g["reason"],
                                  "quote_ok": ok})
        for i, e in enumerate(out["extras"], 1):
            score["extras"].append({"n": i, **e, "quote_ok": quote_ok(e["quote"], review)})
        write_json(path, score)
        print(f"scored {meta['case']} {meta['config']} #{meta['trial']}: "
              + " ".join(f"{b['id']}={b['verdict']}" for b in score["bugs"])
              + f" それ以外 {len(score['extras'])} 件", file=sys.stderr, flush=True)

    try:
        pool(args.jobs, one, trials(args.out))
    finally:
        shutil.rmtree(empty, ignore_errors=True)


# --- cluster -----------------------------------------------------------------
def extras_by_case(out):
    """{題材: [(まとめ用の id, 試行のディレクトリ, meta, 指摘)]}。id は構成が分からない通し番号にする。"""
    by = collections.defaultdict(list)
    for d, meta in trials(out):
        score = read_json(os.path.join(d, "score.json"))
        if score:
            for e in score["extras"]:
                by[meta["case"]].append((d, meta, e))
    result = {}
    for case, items in by.items():
        random.Random(case).shuffle(items)  # 並びから構成を推測できないようにする
        result[case] = [(f"e{i}", d, meta, e) for i, (d, meta, e) in enumerate(items, 1)]
    return result


def cmd_cluster(args):
    empty = tempfile.mkdtemp(prefix="rb-score-")
    os.makedirs(os.path.join(args.out, "_clusters"), exist_ok=True)
    try:
        for case, items in sorted(extras_by_case(args.out).items()):
            path = os.path.join(args.out, "_clusters", case + ".json")
            if os.path.exists(path):
                known = {(m["dir"], m["n"]) for m in read_json(path)["members"].values()}
                if {(os.path.relpath(d, args.out), e["n"]) for _, d, _, e in items} != known:
                    print(f"warn: {case}: まとめたあとに指摘が増減している。{path} を消して、cluster と classify をやり直す",
                          file=sys.stderr, flush=True)
                continue
            listing = [{"id": i, "location": e["location"], "summary": e["summary"]} for i, _, _, e in items]
            out, cost = ask(CLUSTER_PROMPT + "\n\n" + json.dumps(listing, ensure_ascii=False, indent=1),
                            CLUSTER_SCHEMA, empty)
            ids, seen, clusters = {i for i, *_ in items}, set(), []
            for c in out["clusters"]:
                members = [m for m in c["members"] if m in ids and m not in seen]
                seen.update(members)
                if members:
                    clusters.append({"title": c["title"], "location": c["location"], "members": members})
            by_id = {i: e for i, _, _, e in items}
            for i in sorted(ids - seen, key=lambda s: int(s[1:])):  # 入れ忘れは、1件だけのまとまりにする
                clusters.append({"title": by_id[i]["summary"], "location": by_id[i]["location"], "members": [i]})
            for n, c in enumerate(clusters, 1):
                c["id"] = f"{case}/c{n}"
            members = {i: {"dir": os.path.relpath(d, args.out), "config": meta["config"], "trial": meta["trial"],
                           "n": e["n"]} for i, d, meta, e in items}
            write_json(path, {"case": case, "cost_usd": cost, "clusters": clusters, "members": members})
            print(f"clustered {case}: 指摘 {len(items)} 件 → まとまり {len(clusters)} 件", file=sys.stderr, flush=True)
    finally:
        shutil.rmtree(empty, ignore_errors=True)


# --- classify ----------------------------------------------------------------
BATCH = 8  # 1回の分類役に渡すまとまりの数


def cmd_classify(args):
    cdir = os.path.join(args.out, "_clusters")
    root = os.path.realpath(tempfile.mkdtemp(prefix="rb-"))
    work = []
    for name in sorted(os.listdir(cdir)) if os.path.isdir(cdir) else []:
        if not name.endswith(".json"):  # .DS_Store など
            continue
        data = read_json(os.path.join(cdir, name))
        todo = [c for c in data["clusters"] if "class" not in c]
        for i in range(0, len(todo), BATCH):
            work.append((os.path.join(cdir, name), data["case"], [c["id"] for c in todo[i:i + BATCH]]))
    lock = threading.Lock()
    templates = {}
    try:
        for case in sorted({w[1] for w in work}):
            templates[case] = os.path.join(root, "tpl", case)
            bench.build(bench.load_case(case), templates[case])

        def one(item):
            path, case, ids = item
            with lock:
                data = read_json(path)
            extras = {}
            for i, m in data["members"].items():
                score = read_json(os.path.join(args.out, m["dir"], "score.json"))
                extras[i] = next(e for e in score["extras"] if e["n"] == m["n"])
            listing = []
            for c in data["clusters"]:
                if c["id"] in ids:
                    listing.append({"id": c["id"], "title": c["title"], "location": c["location"],
                                    "指摘の原文(抜粋)": [extras[m]["quote"] for m in c["members"][:3]],
                                    "指摘の要約": [extras[m]["summary"] for m in c["members"][:3]]})
            trial, repo = bench.clone_trial(templates[case], root, bench.load_case(case))
            try:
                out, cost = ask(CLASSIFY_PROMPT + "\n\n===== 指摘 =====\n" + json.dumps(listing, ensure_ascii=False, indent=1),
                                CLASSIFY_SCHEMA, repo, tools=True, system=bench.OWN_COPY)
            finally:
                shutil.rmtree(trial, ignore_errors=True)
            got = {i["id"]: i for i in out["items"]}
            with lock:
                data = read_json(path)
                for c in data["clusters"]:
                    g = got.get(c["id"])
                    if g and c["id"] in ids:
                        c.update({"class": g["class"], "scope": g["scope"], "ran": g["ran"], "evidence": g["evidence"],
                                  "classified_by": "llm"})
                data["classify_cost_usd"] = data.get("classify_cost_usd", 0) + cost
                write_json(path, data)
            print(f"classified {case}: {len(got)} 件", file=sys.stderr, flush=True)

        pool(args.jobs, one, work)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- report ------------------------------------------------------------------
def fmt_tokens(n):
    return f"{n / 10000:.0f}万"


def median(xs):
    return statistics.median(xs) if xs else 0


def cmd_report(args):
    out = args.out
    rows = trials(out)
    configs = [c for c in bench.CONFIGS if any(m["config"] == c for _, m in rows)]
    cases = sorted({m["case"] for _, m in rows})
    kinds = {m["case"]: m["kind"] for _, m in rows}
    keys = {c: answers(c) for c in cases}
    bugs = [(c, b) for c in cases for b in keys[c]["bugs"] if b.get("scope", "in") == "in"]
    scores = {d: read_json(os.path.join(d, "score.json")) for d, _ in rows}
    cluster_of, clusters = {}, {}
    for case in cases:
        data = read_json(os.path.join(out, "_clusters", case + ".json"))
        if not data:
            continue
        for c in data["clusters"]:
            clusters[c["id"]] = c
            for m in c["members"]:
                mm = data["members"][m]
                cluster_of[(os.path.join(out, mm["dir"]), mm["n"])] = c["id"]

    # 検出: {(構成, 題材, 不具合): [試行ごとの判定]}
    det = collections.defaultdict(list)
    for d, m in rows:
        s = scores[d]
        if not s or m["status"] not in SCORED:
            continue
        for b in s["bugs"]:
            det[(m["config"], m["case"], b["id"])].append(b["verdict"])

    def rate(config, pred=lambda case, bug: True):
        hit = part = total = 0
        for case, b in bugs:
            if pred(case, b):
                v = det.get((config, case, b["id"]), [])
                hit, part, total = hit + v.count("detected"), part + v.count("partial"), total + len(v)
        return hit, part, total

    def pct(hit, total):
        return f"{hit}/{total}({100 * hit / total:.0f}%)" if total else "—"

    L = ["# 結果", "", f"結果の置き場: `{os.path.relpath(out, HERE)}`", ""]
    L += ["## 試行の数と失敗", "", "| 構成 | 試行 | ok | denied | それ以外の失敗 |", "|---|---|---|---|---|"]
    for c in configs:
        st = collections.Counter(m["status"] for _, m in rows if m["config"] == c)
        bad = "、".join(f"{k} {v}" for k, v in sorted(st.items()) if k not in SCORED) or "なし"
        L.append(f"| {c} | {sum(st.values())} | {st['ok']} | {st['denied']} | {bad} |")
    L += ["", "denied は、レビューの出力はあるが、本番の review_loop.py なら試行を止める権限の拒否(auto mode の分類器など)が"
          "あった試行。本番では、その反復が permission_denied で失敗になる。", "",
          "検出と余計な指摘の集計は、出力のある試行(ok と denied)を数える。", ""]

    L += ["## 検出(埋め込んだ不具合)", "",
          "検出の機会は「不具合 × 出力のある試行」。部分は検出に数えない。", "",
          "| 構成 | 検出 | 部分 | 1回でも検出した不具合 | 毎回検出した不具合 |", "|---|---|---|---|---|"]
    for c in configs:
        hit, part, total = rate(c)
        v = [det.get((c, case, b["id"]), []) for case, b in bugs]
        ran = [x for x in v if x]
        L.append(f"| {c} | {pct(hit, total)} | {part} | {sum('detected' in x for x in ran)}/{len(ran)} | "
                 f"{sum(all(y == 'detected' for y in x) for x in ran)}/{len(ran)} |")
    L += ["", "### 題材の種類ごと", "", "| 構成 | " + " | ".join(sorted(set(kinds.values()))) + " |",
          "|---|" + "---|" * len(set(kinds.values()))]
    for c in configs:
        L.append(f"| {c} | " + " | ".join(pct(*[rate(c, lambda case, b, k=k: kinds[case] == k)[i] for i in (0, 2)])
                                         for k in sorted(set(kinds.values()))) + " |")
    L += ["", "### 不具合の由来ごと(履歴 / 新規)", "", "| 構成 | 履歴 | 新規 |", "|---|---|---|"]
    for c in configs:
        h = rate(c, lambda case, b: b["origin"].startswith("history"))
        n = rate(c, lambda case, b: not b["origin"].startswith("history"))
        L.append(f"| {c} | {pct(h[0], h[2])} | {pct(n[0], n[2])} |")
    L += ["", "### 不具合ごと(検出した試行 / 出力のある試行。p は部分)", "",
          "| 不具合 | 影響 | 由来 | " + " | ".join(configs) + " | 概要 |", "|---|---|---|" + "---|" * (len(configs) + 1)]
    for case, b in bugs:
        cells = []
        for c in configs:
            v = det.get((c, case, b["id"]), [])
            cells.append(f"{v.count('detected')}/{len(v)}" + (f" p{v.count('partial')}" if v.count("partial") else "")
                         if v else "—")
        L.append(f"| {case} {b['id']} | {b['impact']} | {b['origin']} | " + " | ".join(cells) + f" | {b['summary'][:60]} |")

    L += ["", "### 構成を外したときに失うもの", "",
          "「固有」は、その構成だけが1回でも検出した不具合。「残りの構成」は、その構成を外した残り全部で、"
          "1回でも検出した不具合の数。", "", "| 構成 | 固有の検出 | 残りの構成での検出 |", "|---|---|---|"]
    found = {c: {(case, b["id"]) for case, b in bugs if "detected" in det.get((c, case, b["id"]), [])} for c in configs}
    for c in configs:
        others = set().union(*[found[o] for o in configs if o != c]) if len(configs) > 1 else set()
        uniq = sorted(found[c] - others)
        L.append(f"| {c} | {len(uniq)}" + (f"({'、'.join(f'{a} {b}' for a, b in uniq)})" if uniq else "")
                 + f" | {len(others)}/{len(bugs)} |")
    allf = set().union(*found.values()) if found else set()
    L += ["", f"全構成を合わせて、1回でも検出した不具合: {len(allf)}/{len(bugs)}", ""]

    L += ["## 余計な指摘(埋め込んでいない指摘)", "",
          "1試行あたりの平均件数。分類は、同じ指摘をまとめたまとまりごとに付けたもの。「本物」は差分の内 / 外に分ける。", "",
          "| 構成 | 合計 | 本物(内) | 本物(外) | 些末 | 誤り | 未確定 | 未分類 | 不具合のない題材での合計 |",
          "|---|---|---|---|---|---|---|---|---|"]
    clean = {c for c in cases if not [b for b in keys[c]["bugs"] if b.get("scope", "in") == "in"]}
    for c in configs:
        n = cn = 0
        cnt, ctotal = collections.Counter(), 0
        for d, m in rows:
            s = scores[d]
            if m["config"] != c or m["status"] not in SCORED or not s:
                continue
            n += 1
            cn += m["case"] in clean
            for e in s["extras"]:
                cl = clusters.get(cluster_of.get((d, e["n"])), {})
                k = cl.get("class", "unclassified")
                if k == "real":
                    k = "real_out" if cl.get("scope") == "out" else "real_in"
                cnt[k] += 1
                ctotal += m["case"] in clean
        if n:
            L.append(f"| {c} | {sum(cnt.values()) / n:.1f} | " + " | ".join(
                f"{cnt[k] / n:.1f}" for k in ("real_in", "real_out", "trivial", "wrong", "undetermined", "unclassified"))
                + (f" | {ctotal / cn:.1f} |" if cn else " | — |"))

    L += ["", "## 時間とトークン(1試行あたり)", "",
          "| 構成 | 時間の中央値 | 最長 | 入力の中央値 | 出力の中央値 | 費用の中央値 | 費用の合計 |", "|---|---|---|---|---|---|---|"]
    total_cost = 0
    for c in configs:
        ms = [m for _, m in rows if m["config"] == c and m["status"] in SCORED]
        cost = sum(m.get("cost_usd") or 0 for _, m in rows if m["config"] == c)
        total_cost += cost
        if ms:
            L.append(f"| {c} | {median([m['duration_s'] for m in ms]) / 60:.1f}分 | {max(m['duration_s'] for m in ms) / 60:.1f}分 | "
                     f"{fmt_tokens(median([m['tokens']['input'] for m in ms]))} | "
                     f"{fmt_tokens(median([m['tokens']['output'] for m in ms]))} | "
                     f"${median([m.get('cost_usd') or 0 for m in ms]):.2f} | ${cost:.2f} |")
    score_cost = sum((s or {}).get("cost_usd", 0) for s in scores.values())
    cl_cost = sum((read_json(os.path.join(out, "_clusters", c + ".json")) or {}).get(k, 0)
                  for c in cases for k in ("cost_usd", "classify_cost_usd"))
    L += ["", f"レビュー役の費用の合計 ${total_cost:.2f}、採点 ${score_cost:.2f}、まとめと分類 ${cl_cost:.2f}(API 換算)。", ""]

    flagged = [(m, x) for _, m in rows for x in m.get("outside_access") or []]
    changed = [m for _, m in rows if m["config"] != "prove" and (m.get("tree_changed") or m.get("head_changed"))]
    L += ["## 確かめること", "", f"- 題材の外へのアクセスの疑い: {len(flagged)} 件"]
    L += [f"  - {m['case']} {m['config']} #{m['trial']}: `{x[:160]}`" for m, x in flagged[:40]]
    L += [f"- 作業ツリーを変えた試行(prove 以外): {len(changed)} 件"]
    L += [f"  - {m['case']} {m['config']} #{m['trial']}: {(m.get('tree_changed') or ['HEAD が変わった'])[:3]}" for m in changed]
    bad_q = sum(not b["quote_ok"] for s in scores.values() if s for b in s["bugs"]) + \
        sum(not e["quote_ok"] for s in scores.values() if s for e in s["extras"])
    L += [f"- 採点役の引用が、レビューの出力に見つからなかった件数: {bad_q}", ""]
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")

    # 抜き取り用の一覧
    R = ["# 採点の抜き取り用の一覧", "",
         "検出の判定と、余計な指摘の分類を、根拠つきで並べる。★ は乱数(種は固定)で選んだ抜き取りの対象。",
         "レビューの出力の全文は、各試行の `result.md`。基準は `score.py` の SCORE_PROMPT と CLASSIFY_PROMPT。", "",
         "## 検出の判定", ""]
    judged = [(d, m, b) for d, m in rows if scores[d] for b in scores[d]["bugs"]]
    rng = random.Random(20261115)
    pick = set(rng.sample(range(len(judged)), min(12, len(judged))))
    for i, (d, m, b) in enumerate(judged):
        R += [f"- {'★ ' if i in pick else ''}`{os.path.relpath(d, out)}` {b['id']} → **{b['verdict']}**"
              + ("" if b["quote_ok"] else "(引用が出力に見つからない)"),
              f"  - 理由: {b['reason']}"] + ([f"  - 引用: 「{b['quote'][:200]}」"] if b["quote"] else [])
    R += ["", "## 余計な指摘の分類(まとまりごと)", ""]
    cl = sorted(clusters.values(), key=lambda c: c["id"])
    pick = set(rng.sample(range(len(cl)), min(12, len(cl))))
    counts = collections.Counter()
    for (d, n), cid in cluster_of.items():
        meta = read_json(os.path.join(d, "meta.json"))
        if meta:  # まとめたあとに消えた試行は数えない(cluster が警告する)
            counts[(cid, meta["config"])] += 1
    for i, c in enumerate(cl):
        who = "、".join(f"{k} ×{counts[(c['id'], k)]}" for k in configs if counts[(c["id"], k)])
        label = CLASS_JA.get(c.get("class"), "未分類") + (f"・差分の{'外' if c.get('scope') == 'out' else '内'}"
                                                         if c.get("class") == "real" else "")
        R += [f"- {'★ ' if i in pick else ''}`{c['id']}` **{label}**"
              + (f"({'実行して確かめた' if c.get('ran') else '実行していない'}、{c.get('classified_by', '')})" if "class" in c else "")
              + f" — {c['title']}", f"  - 場所: {c['location']} / 挙げた構成: {who}"]
        if c.get("evidence"):
            R.append(f"  - 根拠: {c['evidence']}")
    with open(os.path.join(out, "scoring-review.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(R) + "\n")
    print(os.path.join(out, "report.md"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, jobs in (("score", cmd_score, 4), ("cluster", cmd_cluster, 0), ("classify", cmd_classify, 3),
                           ("report", cmd_report, 0)):
        p = sub.add_parser(name)
        p.add_argument("out")
        p.add_argument("--model", default=bench.MODEL)
        if jobs:
            p.add_argument("--jobs", type=int, default=jobs)
        p.set_defaults(fn=fn)
    args = ap.parse_args()
    args.out = os.path.abspath(args.out)
    global MODEL
    MODEL = args.model
    args.fn(args)


if __name__ == "__main__":
    main()

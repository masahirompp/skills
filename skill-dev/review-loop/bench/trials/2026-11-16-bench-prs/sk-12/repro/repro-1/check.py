"""規則1: つないだテキストは観点の本文としてだけ使い、判定とエラーの詳細は行から取る。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from repro_lib import load, result, Case, Report
try:
    r = load(sys.argv[1])
except SystemExit:
    raise
except Exception as e:
    print(f"読み込めない: {e}"); sys.exit(2)
rep = Report()


def main():
    V = "## 指摘\n\n### F1: s\n- 影響: 中。r\n\n## 競合\n\nなし"
    DRAFT = "## 指摘\n\n### F1: draft\n\n## 競合\n\nなし"


    def judge(steps):
        c = Case(r, {"judge": steps})
        try:
            return c.judge(), None
        except r.AttemptFailed as e:
            return None, e

    # --- 判定の取り出し(run_judge) ---
    out, e = judge([result("下書き:\n" + DRAFT), result("修正版です。\n" + V), result("以上です。")])
    rep("判定: 下書きと修正版を出すと、修正版の判定だけを採る", out == V, out if e is None else f"{e}: {e.detail}")
    out, e = judge([result("以下が判定です。\n\n```markdown\n" + V + "\n```"), result("補足: 以上です。")])
    rep("判定: 後ろに別の result の行があっても、閉じフェンスと無関係な文を混ぜない", out == V,
        out if e is None else f"{e}: {e.detail}")
    # --- 見出しの確認(横展開) ---
    out, e = judge([result("## 指摘\n\nなし"), result("## 競合\n\nなし")])
    rep("見出し: 見出しが別々の行に分かれていて、全てを含む行がなければ no_output", e is not None and e.kind == "no_output",
        out if e is None else f"{e}")
    # --- エラーの詳細(check_result) ---
    LONG = "途中の本文。" * 120
    ERR = "API Error: 529 overloaded_error"
    out, e = judge([result(LONG), result(ERR, subtype="error_during_execution", is_error=True)])
    rep("エラーの詳細(判定役): 失敗した行の文を出す", e is not None and ERR in e.detail,
        out if e is None else e.detail[:120])
    c = Case(r, {})
    p = os.path.join(c.dir, "s.jsonl")
    import json
    with open(p, "w") as f:
        for s in (result(LONG), result(ERR, subtype="error_during_execution", is_error=True)):
            f.write(json.dumps(s["emit"], ensure_ascii=False) + "\n")
    open(os.path.join(c.dir, "x.stderr.txt"), "w").close()
    tail = r.StreamTail(p); tail.poll()
    try:
        r.check_result("review code-review", 1, os.path.join(c.dir, "x"), c.attempt, tail)
        rep("エラーの詳細(レビュー役): 失敗した行の文を出す", False, "成功した")
    except r.AttemptFailed as e:
        rep("エラーの詳細(レビュー役): 失敗した行の文を出す", ERR in e.detail, e.detail[:120])
    # --- 対照 ---
    out, e = judge([result(V)])
    rep("対照: result の行が1つなら、その判定をそのまま返す", out == V, out if e is None else str(e))
    out, e = judge([result("レビューを突き合わせています。"), result(V), result("")])
    rep("対照: 前置きの行と空の最後の行があっても、判定の行を返す", out == V, out if e is None else str(e))
    out, e = judge([result("以下が判定です。\n\n```markdown\n" + V + "\n```")])
    rep("対照: 前置きとコードフェンスで包んだ判定は、中身だけを返す", out == V, out if e is None else str(e))
    out, e = judge([result("done")])
    rep("対照: 見出しのない判定は no_output", e is not None and e.kind == "no_output", out)


rep.run(main)

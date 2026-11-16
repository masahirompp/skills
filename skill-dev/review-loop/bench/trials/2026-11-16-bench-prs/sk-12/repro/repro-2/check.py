"""規則2: 止めない拒否は判定の材料と記録に漏れなく残し、出どころの分からない拒否は止める側に倒す。"""
import os, re, sys
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


    def tool_use(id_, name, inp):
        return {"emit": {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": id_, "name": name, "input": inp}]}}}


    def denied(name, id_=None, source="config"):
        d = {"type": "system", "subtype": "permission_denied", "tool_name": name, "message": "Permission denied."}
        if id_:
            d["tool_use_id"] = id_
        if source:
            d.update(source=source, reason_type="subcommandResults")
        return {"emit": d}


    def attempt(files, judge=False):
        """レビュー役を巡回し(judge なら判定役も動かし)、(Case, 例外) を返す。"""
        c = Case(r, files)
        try:
            reviews = c.reviews()
            if judge:
                c.judge(reviews)
            return c, None
        except r.AttemptFailed as e:
            return c, e


    def lines(c, label):
        return [l for l in c.read("denials.txt").splitlines() if l.startswith(label + ":")]

    # (a) tool_use_id のない止めない拒否が2件
    c, e = attempt({"security_review": [denied("Bash"), denied("Read"), result("security-review: 指摘なし")]})
    got = lines(c, "review security-review")
    rep("(a) id のない止めない拒否が2件あれば、denials.txt に2件とも残る", len(got) == 2, c.read("denials.txt"))
    # (a) id のない止めない拒否 + result にだけ載った出どころの分からない拒否
    c, e = attempt({"security_review": [denied("Bash"), result("security-review: 指摘なし", permission_denials=[
        {"tool_name": "Write", "tool_input": {"file_path": "/etc/x"}}])]})
    rep("(a) result にだけ載った id のない拒否があれば、止める(permission_denied)",
        e is not None and e.kind == "permission_denied", "成功した" if e is None else str(e))
    # 横展開: 止める拒否(tail.denial)に id がない
    c, e = attempt({"security_review": [denied("Bash", source=None), result("security-review: 指摘なし", permission_denials=[
        {"tool_name": "Write", "tool_input": {"file_path": "/etc/x"}}])]})
    rep("横展開: id のない止める拒否のあと、result に id のない拒否があっても止める",
        e is not None and e.kind == "permission_denied", "成功した" if e is None else str(e))
    # (b) 止めなかった拒否が判定役への入力に入る
    c, e = attempt({"security_review": [tool_use("t1", "Bash", {"command": "grep -n KEY .env"}), denied("Bash", "t1"),
                                         result("security-review: 指摘なし", permission_denials=[
                                             {"tool_name": "Bash", "tool_use_id": "t1", "tool_input": {}}])]}, judge=True)
    inp = c.read("judge-input.md")
    m = re.search(r"===== 観点: security-review =====(.*?)===== ここまで: security-review =====", inp, re.S)
    rep("(b) 止めなかった拒否が、その観点の区切りの中で判定役への入力に入る",
        e is None and m is not None and "grep -n KEY .env" in m.group(1), inp if e is None else str(e))
    # 横展開: 判定役自身の止めない拒否
    c, e = attempt({"judge": [tool_use("j1", "Bash", {"command": "cat .env"}), denied("Bash", "j1"),
                              result("## 指摘\n\nなし\n\n## 競合\n\nなし", permission_denials=[
                                  {"tool_name": "Bash", "tool_use_id": "j1", "tool_input": {}}])]}, judge=True)
    rep("横展開: 判定役自身の止めない拒否は、試行を止めず denials.txt に残る",
        e is None and any("cat .env" in l for l in lines(c, "judge")), c.read("denials.txt") if e is None else str(e))
    # (c) 先に見た子が失敗する直前に、ほかの子が止めない拒否を書いた
    r.POLL_SECONDS = 1.0
    c0 = Case(r, {})
    marker = os.path.join(c0.dir, "marker")
    c, e = attempt({"code_review": [{"wait": marker}, {"exit": 1}],
                    "security_review": [{"sleep": 0.2}, tool_use("t1", "Bash", {"command": "grep -n KEY .env"}),
                                        denied("Bash", "t1"), {"touch": marker}, {"sleep": 30}],
                    "mattpocock_skills_code_review": [{"sleep": 30}]})
    r.POLL_SECONDS = 0.05
    rep("(c) 1つが失敗して止めるときも、ほかの子の止めない拒否を denials.txt に残す",
        e is not None and e.kind == "child_error" and len(lines(c, "review security-review")) == 1,
        f"{e}; denials.txt={c.read('denials.txt')!r}")
    # 対照
    c, e = attempt({"security_review": [tool_use("t1", "Bash", {"command": "grep -n KEY .env"}), denied("Bash", "t1"),
                                         result("security-review: 指摘なし", permission_denials=[
                                             {"tool_name": "Bash", "tool_use_id": "t1", "tool_input": {}}])]})
    rep("対照: id の揃った止めない拒否は、止めずに1件だけ残す", e is None and len(lines(c, "review security-review")) == 1,
        f"{e}; {c.read('denials.txt')!r}")
    c, e = attempt({}, judge=True)
    rep("対照: 拒否がなければ成功し、denials.txt を作らない", e is None and c.read("denials.txt") == "", str(e))
    c, e = attempt({"security_review": [tool_use("t1", "Bash", {"command": "rm x"}), denied("Bash", "t1", source=None),
                                         result("x")]})
    rep("対照: source のない拒否は止める", e is not None and e.kind == "permission_denied", str(e))


rep.run(main)

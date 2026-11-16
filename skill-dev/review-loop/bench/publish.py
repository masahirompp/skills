#!/usr/bin/env python3
"""題材を、GitHub の検証用の非公開リポジトリと PR にする(本番と同じく、PR がある状態でレビューさせるため)。

    publish.py create [題材...]     題材ごとに <owner>/rlbench-<題材> を作り、main にベース、PR にレビュー対象の差分を置く
    publish.py delete [題材...]     作ったリポジトリを消す(gh に delete_repo の権限が要る)

題材ごとに、作ったリポジトリと PR 番号を cases/<題材>/github.json に書く。既にあれば作り直さない。

PR の本文は、元の PR を**作った時点**の本文を、GitHub の編集履歴から取り出して使う(今の本文は、レビューで見つかった
修正を反映して書き直されていて、答えが混ざる)。不具合のない題材(レビュー後の最終形)は、今の本文から
「レビューの経緯」を外したもの(cases/<題材>/message.txt)を使う。
元の PR の本文が参照する issue は、PR を作った時点の本文で写し、本文の中の番号を新しい番号に書き換える。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
import bench  # noqa: E402

PREFIX = "rlbench-"
MAX_ISSUES = 4

QUERY = """
query($owner:String!,$name:String!,$n:Int!){ repository(owner:$owner,name:$name){ issueOrPullRequest(number:$n){
  __typename
  ... on PullRequest { title createdAt body userContentEdits(first:100){ nodes{ editedAt diff } } }
  ... on Issue { title createdAt body userContentEdits(first:100){ nodes{ editedAt diff } } }
}}}"""


def gh(*args, input=None):
    r = subprocess.run(["gh", *args], input=input, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:4])} が失敗した: {r.stderr.strip()[-600:]}")
    return r.stdout


def fetch(repo, number):
    """PR か issue を取る。無ければ None。"""
    owner, name = repo.split("/")
    try:
        out = gh("api", "graphql", "-f", "query=" + QUERY, "-F", f"owner={owner}", "-F", f"name={name}", "-F", f"n={number}")
    except RuntimeError:
        return None
    return json.loads(out)["data"]["repository"]["issueOrPullRequest"]


def body_at(item, when):
    """when(ISO の時刻)の時点の本文。編集履歴の diff は、その編集の後の本文の全体。when が None なら今の本文。"""
    if when is None:
        return item["body"]
    edits = sorted((e for e in item["userContentEdits"]["nodes"] if e["diff"] is not None), key=lambda e: e["editedAt"])
    before = [e for e in edits if e["editedAt"] <= when]
    if before:
        return before[-1]["diff"]
    return edits[0]["diff"] if edits else item["body"]


def strip_footer(body):
    return re.sub(r"\n+🤖 Generated with.*\Z", "\n", body.replace("\r\n", "\n"), flags=re.S).strip() + "\n"


def create(case_id, owner):
    case = bench.load_case(case_id)
    out_path = os.path.join(case["dir"], "github.json")
    if os.path.exists(out_path):
        print(f"{case_id}: 作成済み({json.load(open(out_path))['repo']})")
        return
    src = case.get("pr")
    if not src:
        raise RuntimeError(f"{case_id}: case.json に元の PR(pr)が無い")
    pr = fetch(src["repo"], src["number"])
    if src.get("final"):  # レビュー後の最終形。今の本文から「レビューの経緯」を外したものを使う
        with open(os.path.join(case["dir"], "message.txt"), encoding="utf-8") as f:
            title, _, body = f.read().partition("\n\n")
        when = None
    else:
        title, when = pr["title"], pr["createdAt"]
        body = strip_footer(body_at(pr, when))
    # 本文が参照する issue を写す(PR を作った時点の本文で)。参照が PR なら写さない
    issues = []
    for n in dict.fromkeys(int(x) for x in re.findall(r"(?<![\w/])#(\d+)\b", body)):
        if n == src["number"] or len(issues) >= MAX_ISSUES:
            continue
        item = fetch(src["repo"], n)
        if item and item["__typename"] == "Issue" and (when is None or item["createdAt"] <= when):
            issues.append((n, item["title"], strip_footer(body_at(item, when))))

    repo = f"{owner}/{PREFIX}{case_id}"
    tmp = tempfile.mkdtemp(prefix="rb-pub-")
    try:
        local = bench.build({k: v for k, v in case.items() if k != "setup"}, os.path.join(tmp, "t"))
        gh("repo", "create", repo, "--private", "--description", "review-loop の検証用の題材(自動生成。消してよい)")
        bench.git(local, "remote", "set-url", "origin", f"git@github.com:{repo}.git")
        bench.git(local, "push", "-q", "-u", "origin", "main", case["branch"])
        mapping = {}
        for old, ititle, ibody in issues:
            url = gh("issue", "create", "-R", repo, "--title", ititle, "--body-file", "-", input=ibody).strip()
            mapping[old] = int(url.rsplit("/", 1)[1])
        # 1回で書き換える(番号ごとに順に書き換えると、新しい番号が、後で書き換える古い番号と重なったときに二重に変わる)
        body = re.sub(r"(?<![\w/])#(\d+)\b", lambda m: f"#{mapping.get(int(m.group(1)), m.group(1))}", body)
        url = gh("pr", "create", "-R", repo, "--base", "main", "--head", case["branch"], "--title", title,
                 "--body-file", "-", input=body).strip()
        info = {"repo": repo, "pr": int(url.rsplit("/", 1)[1]), "issues": {str(k): v for k, v in mapping.items()},
                "head": bench.git(local, "rev-parse", "HEAD").strip()}
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"{case_id}: {url}(issue {len(mapping)} 件、本文 {len(body)} 文字)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def delete(case_id):
    case = bench.load_case(case_id)
    path = os.path.join(case["dir"], "github.json")
    if not os.path.exists(path):
        return
    repo = json.load(open(path))["repo"]
    if not repo.split("/")[1].startswith(PREFIX):
        raise RuntimeError(f"{repo} は検証用のリポジトリの名前ではない。消さない")
    gh("repo", "delete", repo, "--yes")
    os.remove(path)
    print(f"{case_id}: {repo} を消した")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["create", "delete"])
    ap.add_argument("cases", nargs="*")
    args = ap.parse_args()
    cases = args.cases or [c for c in bench.all_cases() if "pr" in bench.load_case(c)]
    owner = gh("api", "user", "--jq", ".login").strip()
    for c in cases:
        try:
            create(c, owner) if args.cmd == "create" else delete(c)
        except Exception as e:
            print(f"{c}: 失敗: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()

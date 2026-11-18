# 親が、修正前の写しや一時ディレクトリに触れたコマンド

## 00-e6e0f822-0ce1-4bee-8b9b-a4a5aadf748e.jsonl:138(01:12:36、修正役のあと: False、終了コード 0)

````
F=$(mktemp -d); mkdir $F/before $F/work; git archive -o $F/before.tar HEAD && tar -xf $F/before.tar -C $F/before; echo $F; ls $F/before
````

出力:

````
/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/tmp.rb0SI4uuMp
LICENSE
README.md
skill-dev
skills
````

## 00-e6e0f822-0ce1-4bee-8b9b-a4a5aadf748e.jsonl:186(01:17:34、修正役のあと: True、終了コード 0)

````
F=/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/tmp.rb0SI4uuMp; cat $F/work/repro.py; git status --short; git log --oneline -3
````

出力:

````
#!/usr/bin/env python3
"""使い方: python3 repro.py <a|b> <対象のルート>
対象の review_loop.py iterate を、対象の skill-dev/review-loop/fakes の偽 claude・gh で1回動かし、
状態コメントの表を調べる。症状を見たら 1、無ければ 0。
  a: 既定と引数だけ違う観点(code-review のレベルを high から medium に)で回す。表に観点の違いが載らなければ症状
  b: 既定と同じ観点を並び順だけ変えて回す。表に観点が載れば症状
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

mode, target = sys.argv[1], os.path.abspath(sys.argv[2])
scripts = os.path.join(target, "skills/review-loop/scripts")
fakes = os.path.join(target, "skill-dev/review-loop/fakes")
here = os.path.dirname(os.path.abspath(__file__))
root = os.path.realpath(tempfile.mkdtemp(prefix=f"repro-{mode}.", dir=here))

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


try:
    os.makedirs(os.path.join(root, "fake"))
    sh("git", "init", "-q", "--bare", "-b", "main", os.path.join(root, "origin.git"))
    wt = os.path.join(root, "wt")
    sh("git", "clone", "-q", os.path.join(root, "origin.git"), wt)
    sh("git", "config", "user.name", "t", cwd=wt)
    sh("git", "config", "user.email", "t@example.com", cwd=wt)
    with open(os.path.join(wt, "a.txt"), "w") as f:
        f.write("a\n")
    sh("git", "add", "-A", cwd=wt)
    sh("git", "commit", "-qm", "i
````

## 00-e6e0f822-0ce1-4bee-8b9b-a4a5aadf748e.jsonl:194(01:17:39、修正役のあと: True、終了コード 0)

````
F=/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/tmp.rb0SI4uuMp; W=$(pwd); for m in a b; do python3 $F/work/repro.py $m $F/before >/dev/null 2>&1; echo "$m before=$?"; python3 $F/work/repro.py $m $W >/dev/null 2>&1; echo "$m after=$?"; done; python3 skill-dev/review-loop/test.py 2>&1 | tail -5; echo test=$?; git status --short
````

出力:

````
a before=1
a after=0
b before=1
b after=0
ok    --perspective で外した観点への --instruct: 終了コード2(2) 
ok    空の --perspective: 終了コード2(2) 
ok    観点の指定の誤りは状態に記録しない

全て成功
test=0
````

# push と、PR 本文の書き換え

## 00-e6e0f822-0ce1-4bee-8b9b-a4a5aadf748e.jsonl:207(01:20:35、終了コード 0)

````
gh pr view 5 --json body -q .body > /Users/masahirompp/.claude/jobs/e6e0f822/tmp/body.md && grep -c "レビューループの経緯" /Users/masahirompp/.claude/jobs/e6e0f822/tmp/body.md; cat >> /Users/masahirompp/.claude/jobs/e6e0f822/tmp/body.md <<'EOF'

## レビューループの経緯

### 反復 1(レビューした SHA: ca40dc8)
- 直した: 既定と違う観点かをスキル名だけで、並び順込みで比べていたため、引数だけ違う観点(レベルの変更など)が表に載らず、並び順だけ違う既定の観点が載っていた(db9514f。再現: `python3 repro.py a|b <ルート>` — 偽の claude/gh で iterate を回し、表の行を調べる)
- 未決: `--perspective`/`--instruct` を反復ごとに同じに付けるのが親任せで、付け忘れると黙って既定に戻る。状態コメントに記録して食い違いで止める、という設計の代案が挙がった(今の設計の範囲外として未採用)

<details><summary>対象でない指摘</summary>

- SKILL.md の例が、`--perspective` で外した `security-review` に `--instruct` を付けていて、そのまま流すと終了コード2(影響が低い defect。明確なメッセージで止まり、状態も変えない)
- JUDGE_PROMPT が、追加の指示のブロックの扱いを判定役に伝えていない。観点の出力と取り違えたり、指示で外した範囲を欠落と見たりしうる(doc。プロンプトの読み方に依る)
- `--instruct` の内容が状態コメントに残らない(影響が低い。終了時の報告は SKILL.md で親に求めている)
- `--perspective` の先頭の空白や `/` を正規化しない(影響が低い defect)
- `valid_state` が `perspectives` を list か確かめない(影響が低い defect。手で編集された状態に限る)
- 追加の指示が区切り行を含むと、判定役の入力の区切りが崩れる(影響が低い。利用者自身の入力)
- 追加の指示が「スキルの手順より優先」とされ、変更を禁じる制約まで上書きしうる(doc。混入は contamination で検出される)
- スキル名の一覧の再計算の重複、指示のつなぎ方(style)
- security-review: 該当なし

</details>
EOF
gh pr edit 5 --body-file /Users/masahirompp/.claude/jobs/e6e0f822/tmp/body.md >/dev/null && git push -q origin HEAD && sleep 5 && gh pr view 5 --json headRefOid -q .headRefOid; git rev-parse HEAD
````

出力:

````
0
db9514f651726f554fa00b5d3fb0b9c01553d04a
db9514f651726f554fa00b5d3fb0b9c01553d04a
````

## 00-e6e0f822-0ce1-4bee-8b9b-a4a5aadf748e.jsonl:274(01:23:13、終了コード 0)

````
git status --short && git rev-parse --short HEAD && gh pr view 5 --json body -q .body > /Users/masahirompp/.claude/jobs/e6e0f822/tmp/body2.md && python3 - <<'EOF'
p='/Users/masahirompp/.claude/jobs/e6e0f822/tmp/body2.md'
s=open(p).read()
add='''
### 反復 2(レビューした SHA: db9514f)
- 対象なし。反復 1 で対象でなかった指摘(SKILL.md の例、JUDGE_PROMPT、`--instruct` の記録、正規化、`valid_state` の型、オプションの引き継ぎの設計、style)が再び挙がったが、新しい事情はなく、反復 1 の扱いのまま

<details><summary>対象でない指摘</summary>

- 空白だけ違う観点を既定と違うと扱う(影響が低い。子に渡る文字列が違う)
- `--instruct` の `{pr}` を置き換えない(doc / 影響が低い)
- テストの `by_name.get(..., "x")` が何も確かめずに通りうる(test_gap)
- スキル名だけの記録への互換が、PR の途中のコミットの形にしか当たらない(style)
- 表の結果の列に観点の長さの上限がない(影響が低い)
- security-review: 該当なし

</details>
'''
assert '### 反復 1' in s and '### 反復 2' not in s
open(p,'w').write(s.rstrip('\n')+'\n'+add)
EOF
gh pr edit 5 --body-file /Users/masahirompp/.claude/jobs/e6e0f822/tmp/body2.md >/dev/null && echo ok
````

出力:

````
db9514f
ok
````


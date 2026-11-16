差分を壊しに行き、実行で確かめられたものが3件ありました。3件のうち2件はテストが検出力を持たないという問題です。もう1件は、SKILL.md の記述と実際の動作が食い違っている点です。今回直したかった不具合(macOS で TMPDIR が無視される件)を、本番コードの側で再現できたものはありません。元の `skill-dev/housekeeping/test.sh` は、このマシン(macOS、bash 3.2)で全件成功しました。

---

## 1. scan.sh が `HOUSEKEEPING_TMPDIR` を無視しても、テストが全件成功する

`lib.sh` に変異を入れたコピーを `scratch/mut` に作りました。変異は「指定ディレクトリが存在するかだけ確かめ、実際にはテンプレートなしの `mktemp -d` で `/var/folders/...` に作る」というものです。今回のコミットが直そうとした挙動そのものです。

実行したコマンド:
```
cd /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-1t_d3kns/w/4793324e4d/skills/scratch; rm -rf mut && mkdir mut && git -C .. archive HEAD skills skill-dev | tar -x -C mut && cd mut && sed -i '' 's|d=$(mktemp -d "${base%/}/housekeeping.XXXXXX")|[ -d "$base" ] \|\| return 1; d=$(mktemp -d)|' skills/housekeeping/scripts/lib.sh && grep -n 'd=\$(mktemp' skills/housekeeping/scripts/lib.sh && bash skill-dev/housekeeping/test.sh 2>&1 | grep -E 'FAIL|一時|全件|失敗'
```
出力:
```
19:  [ -d "$base" ] || return 1; d=$(mktemp -d) || return 1
ok    scan: 一時ディレクトリを作れなければ止まる
ok    scan: 一時ディレクトリを片付ける
全件成功
```
出るべきだった出力: 追加したテストのコメントには「一時ディレクトリは HOUSEKEEPING_TMPDIR の下に作り、終了時に消すこと」とあります。その通りなら、この変異で `FAIL` が出るはずでした。実際のテストは、走査の後で `$root/hk-tmp` が空かどうかしか見ていません。そのため、そもそも `$root/hk-tmp` の下に作られなかった場合と見分けがつきません。

## 2. apply.sh の「TMPDIR に依存しない」テストが、macOS では変更前の apply.sh でも成功する

新しい `test.sh` を、main 版の `skills/` と組み合わせて実行しました。main 版の apply.sh は `input=$(mktemp)` を使います。

実行したコマンド:
```
cd scratch && rm -rf old && mkdir old && git -C .. archive main skills | tar -x -C old && mkdir -p old/skill-dev/housekeeping && cp ../skill-dev/housekeeping/test.sh old/skill-dev/housekeeping/ && cd old && bash skill-dev/housekeeping/test.sh 2>&1 | grep -v '^ok' ; echo rc=$?
```
出力:
```
FAIL  scan: 一時ディレクトリを作れないのに止まらない(rc=0)

失敗 1 件
rc=0
```
失敗したのは scan のテストだけでした。apply の全項目は、`TMPDIR="$root/no-such-dir"` を指定した状態でも変更前のコードのまま成功しています。原因は、lib.sh のコメントにある通り、macOS の `mktemp` が TMPDIR を見ないことです。次のコマンドで確かめました。
```
cd .../skills/scratch; mkdir -p mt; TMPDIR=$PWD/mt mktemp; TMPDIR=$PWD/mt mktemp -d; TMPDIR=$PWD/no-such mktemp; echo rc=$?; ls mt
```
```
/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/tmp.nPSvhfB8v5
/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/tmp.r49ZN3pA1s
/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/tmp.cUAX2NctSe
rc=0
```
出るべきだった出力: 変更前の apply.sh に対しては、apply のテストのどれかが `FAIL` になるべきでした。今のままだと、apply.sh に一時ファイルを使うコードが戻っても、macOS では検出できません。Linux の `mktemp` は TMPDIR を見るので、Linux なら検出できる可能性があります。ただし今回は試していません。

## 3. 「作れなければ何もせずに止まる」と書いてあるが、止まる前に `git fetch --prune` が実行される

scan.sh では fetch(27行目より前)が `hk_mktemp_dir` より先に走ります。そのため、一時ディレクトリを作れずに止まる場合でも、リモート追跡ブランチの刈り込みは済んでいます。

実行したコマンド:
```
cd .../skills/scratch; rm -rf fx && mkdir fx && cd fx && S=$PWD/../../skills/housekeeping/scripts/scan.sh && git init -q --bare -b main origin.git && git clone -q origin.git work 2>/dev/null && cd work && git commit -q --allow-empty -m init && git push -q origin main && git push -q origin main:feature && git fetch -q && git remote set-head origin main && git -C ../origin.git branch -D feature >/dev/null && echo "before:" && git branch -r && HOUSEKEEPING_TMPDIR=$PWD/no-such-dir "$S"; echo "rc=$?"; echo "after:"; git branch -r
```
出力:
```
before:
  origin/HEAD -> origin/main
  origin/feature
  origin/main
mktemp: mkdtemp failed on /private/var/folders/.../scratch/fx/work/no-such-dir/housekeeping.L1hfh3: No such file or directory
error: 一時ディレクトリを作れない(/private/var/folders/.../scratch/fx/work/no-such-dir)。HOUSEKEEPING_TMPDIR で書き込める場所を指定する
rc=1
after:
  origin/HEAD -> origin/main
  origin/main
```
出るべきだった出力: SKILL.md に足された「作れなければ何もせずに止まる」が正しいなら、`after:` の後にも `origin/feature` が残っているはずでした。

影響は小さいです。刈り込みは SKILL.md に書いてある scan.sh の唯一の副作用で、ローカルブランチや worktree が消えるわけではありません。直し方は二つあります。SKILL.md の文言を実際の動作に合わせるか、`hk_mktemp_dir` の呼び出しを fetch より前に移すかです。

---

ほかに次のケースも調べましたが、変更前と同じ動作か、問題が出ませんでした。
- apply.sh に空の入力やヘッダー行だけを渡した場合
- 入力の末尾に改行があるかどうか
- `${base%/}` で末尾のスラッシュを取り除く処理

いずれも実行による証明はできていないので、指摘には含めていません。

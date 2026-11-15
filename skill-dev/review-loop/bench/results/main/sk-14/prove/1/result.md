## 結論

差分に入った本体のコード(`scan.sh` / `apply.sh` / `lib.sh`)には、実行で証明できた不具合はありませんでした。証明できたのは、追加されたテスト3件のうち2件が、直す前のコードでも成功してしまう(修正を検証できていない)ことです。

確認のため、`scratch/mut` に複製を作り、本体だけを main 相当に戻して、新しい `test.sh` を流しました。

---

### 指摘1: 「scan: 一時ディレクトリを片付ける」が、`HOUSEKEEPING_TMPDIR` の下に作っていることを確かめていない

テストのコメントには「一時ディレクトリは HOUSEKEEPING_TMPDIR の下に作り、終了時に消すこと」とあります。しかし判定は「`hk-tmp` が空か」だけです。`HOUSEKEEPING_TMPDIR` を無視して `/var/folders/...` に作る旧来の `mktemp -d` でも `hk-tmp` は空のままなので、このテストは成功します。

**実行したコマンド**
```
R=/private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-v3u49r_y/w/1a43ffebb5/skills; cd $R; rm -rf scratch/mut; mkdir -p scratch/mut scratch/tmp
cp -R skills skill-dev scratch/mut/
# 変異1: scan.sh の一時ディレクトリだけ、失敗時の停止は残したまま main と同じテンプレートなし mktemp に戻す
perl -0pi -e 's/tmp=\$\(hk_mktemp_dir\)/tmp=\$(mktemp -d)/' scratch/mut/skills/housekeeping/scripts/scan.sh
grep -n 'tmp=\$(' scratch/mut/skills/housekeeping/scripts/scan.sh
# 変異2: apply.sh を main の版(テンプレートなし mktemp で一時ファイルを使う)に戻す
git show main:skills/housekeeping/scripts/apply.sh > scratch/mut/skills/housekeeping/scripts/apply.sh
grep -n mktemp scratch/mut/skills/housekeeping/scripts/apply.sh
TMPDIR=$R/scratch/tmp bash scratch/mut/skill-dev/housekeeping/test.sh 2>&1 | grep -E 'scan: 一時|FAIL|全件|件失敗|apply: worktree wt-merged'
```

**出力**
```
30:tmp=$(mktemp -d) || {
20:input=$(mktemp)
FAIL  scan: 一時ディレクトリを作れないのに止まらない(rc=0)
ok    scan: 一時ディレクトリを片付ける
ok    apply: worktree wt-merged を削除
```

**出るべきだった出力**
`HOUSEKEEPING_TMPDIR` を無視する変異なので、`FAIL  scan: 一時ディレクトリが残っている`、またはそれに相当する「`HOUSEKEEPING_TMPDIR` の下に作られていない」という FAIL が出るべきでした。実際に失敗したのは、同じ変異で別に引っかかった「作れなければ止まる」のテストだけです。

### 指摘2: apply.sh を「書き込めない TMPDIR でも動く」で検証しても、旧版の apply.sh で成功する

テストでは `TMPDIR="$root/no-such-dir"` を渡し、「一時ファイルを使わないので、書き込めない TMPDIR でも動くこと」を確かめるつもりです。しかし main の `apply.sh` は `input=$(mktemp)` で、テンプレートを付けていません。macOS の mktemp はテンプレートが無いと TMPDIR を見ないので、旧版もこの条件で普通に動きます。そのため、このテストは修正の前後を区別できません。macOS が TMPDIR を見ないことは、次のコマンドで確かめました。

```
TMPDIR=$R/scratch mktemp -d; TMPDIR=$R/scratch mktemp
```
```
/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/tmp.cF64fNYVox
/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/tmp.4A61VfdrIa
```
(作られた2つは、確認のあと削除しました。)

**実行したコマンド**(指摘1の変異のまま、apply の結果を全部表示)
```
R=/private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-v3u49r_y/w/1a43ffebb5/skills; cd $R; TMPDIR=$R/scratch/tmp bash scratch/mut/skill-dev/housekeeping/test.sh 2>&1 | grep -E '^(FAIL|ok    apply)|件|成功' ; ls -A scratch/tmp
```

**出力**(抜粋なし)
```
FAIL  scan: 一時ディレクトリを作れないのに止まらない(rc=0)
ok    apply: 飛ばした行があるので終了コード 1
ok    apply: branch nopr-ff を削除
ok    apply: branch squashed を削除
ok    apply: branch wt-merged を削除
ok    apply: branch wt-gone を削除
ok    apply: branch nopr-merge は残す
ok    apply: branch entire/checkpoints/v1 は残す
ok    apply: branch entire/abc1234-e3b0c4 は残す
ok    apply: branch fresh は残す
ok    apply: branch unverifiable は残す
ok    apply: branch more-after は残す
ok    apply: branch wt-dirty は残す
ok    apply: branch wt-busy は残す
ok    apply: branch main は残す
ok    apply: worktree wt-merged を削除
ok    apply: detached worktree を削除
ok    apply: worktree wt-dirty は残す
ok    apply: worktree wt-untracked は残す
ok    apply: worktree wt-locked は残す
ok    apply: worktree wt-busy は残す
ok    apply: wt-gone を prune
ok    apply: リモートの squashed を削除
ok    apply: リモートの entire/checkpoints/v1 は残す
ok    apply: 走査後に更新されたブランチを飛ばす
ok    apply: 偽装した保護対象の行を拒否
失敗 1 件
hk-test.686hm3
hk-test.SZRrON
```

**出るべきだった出力**
一時ファイルを使う旧版の apply.sh なので、apply の検証が1件以上 FAIL になるべきでした。macOS で区別するには、テンプレート付きの mktemp を偽装して失敗させる必要があります。たとえば、失敗する `mktemp` を置いたディレクトリを `PATH` の先頭に入れる方法です。

---

## 確認したが、壊れなかったもの
- 現在の HEAD で `test.sh` を流すと「全件成功」でした。
- 指摘1の変異では「作れなければ止まる」のテストが正しく FAIL になりました(上の出力の1行目)。このテストは修正を検証できています。

## 差分の外で見つけたこと(指摘ではない)
`TMPDIR=<scratch の下>` で `test.sh` を流すと、終了コードが 143(SIGTERM)になり、`hk-test.*` の作業ディレクトリが消えずに残ります。main の版(`scratch/main`)でも、`rc=143` と `全件成功` が出て、同じく残りました。この差分が原因ではないので、指摘には入れていません。

## 後片付けをお願いしたいもの
`scratch/tmp` の中身を消そうとしたところ、安全確認で止められたので、そのまま残しています。残っているのは `scratch/mut`、`scratch/main`、`scratch/tmp`・`tmp2`・`tmp3`(それぞれの中の `hk-test.*` を含む)、`scratch/main.out` です。不要であれば `scratch/` をまるごと削除してください。

# 判定:証明できた指摘が1件あります

前提条件をはっきりさせておきます。再現できたのは、TMPDIR とカレントディレクトリのどちらにも書き込めない環境だけです。書き込めるのは HOUSEKEEPING_TMPDIR と `.git` だけ、という条件です。

カレントディレクトリに書き込めると、macOS 標準の bash 3.2 はヒアドキュメントの一時ファイルをそこに作ります。そのため、sandbox で `/tmp` と `/var/folders` への書き込みを禁じただけでは、scan も apply も正しく動きました(確認用プロファイル `deny.sb` で実行し、保護対象はすべて `skipped`)。

なお、差分に含まれるテスト `skill-dev/housekeeping/test.sh` はすべて成功しました(`全件成功`)。

再現に使ったファイルはすべて `scratch/` にあります。
- `setup.sh`:最小のリポジトリと bare の origin を作る。`entire/checkpoints/v1` と `release/x` のブランチを含む
- `run2.sh`:書き込める場所を `$F/hk-tmp`、`$F/repo/.git`、`$F/origin.git`、`/dev/null` に限る `deny2.sb` の下で、`TMPDIR` に書けない場所を、`HOUSEKEEPING_TMPDIR` に書ける場所を与えて scan.sh と apply.sh を実行する。apply.sh には保護対象を偽装した行を流す
- `run2-main.sh`:同じ手順を main 版のスクリプトで実行する

---

## 指摘 1:apply.sh はヒアドキュメントで一時ファイルを使う。作れないと保護判定が外れ、保護対象のブランチをローカルとリモートから削除する(main からの退行)

差分の説明には「apply.sh は一時ファイルを使わない」「書き込めない TMPDIR でも動く」とあります。しかし `lib.sh` の `hk_is_protected` はヒアドキュメント(`<<EOF`)で保護パターンを読んでいます。bash 3.2 はヒアドキュメントに一時ファイルを使うので、それが作れないと保護パターンが空になり、関数は「保護対象ではない」(戻り値 1)を返します。

main 版では、最初の `mktemp` が失敗した時点で入力が空になり、何も削除しませんでした。この変更でその歯止めがなくなり、保護対象を削除するようになりました。

**実行したコマンド**
```
cd /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-v3u49r_y/w/b989a81f5c/skills/scratch; F=$PWD/ok/fx
cat > deny2.sb <<X
(version 1)
(allow default)
(deny file-write* (subpath "/private/tmp") (subpath "/private/var/folders") (subpath "/private/var/tmp") (subpath "/usr/tmp"))
(allow file-write* (subpath "$F/hk-tmp") (subpath "$F/repo/.git") (subpath "$F/origin.git") (literal "/dev/null"))
X
sed "s#scratch/deny.sb#scratch/deny2.sb#" run.sh > run2.sh; chmod +x run2.sh
./setup.sh $F >/dev/null 2>&1; ./run2.sh $F 1 2>&1
```

**出力**
```
== scan
action	kind	name	sha	path	reason
/private/var/folders/.../skills/skills/housekeeping/scripts/scan.sh: line 203: cannot create temp file for here document: Operation not permitted
/private/var/folders/.../skills/skills/housekeeping/scripts/scan.sh: line 209: action: unbound variable
scan rc=1
== apply (偽装した保護対象の行)
/private/var/folders/.../skills/skills/housekeeping/scripts/lib.sh: line 43: cannot create temp file for here document: Operation not permitted
done	branch entire/checkpoints/v1 (242a19bf797692964ea5368f7c1c38365be9dcbf)
/private/var/folders/.../skills/skills/housekeeping/scripts/lib.sh: line 43: cannot create temp file for here document: Operation not permitted
done	branch release/x (242a19bf797692964ea5368f7c1c38365be9dcbf)
/private/var/folders/.../skills/skills/housekeeping/scripts/lib.sh: line 43: cannot create temp file for here document: Operation not permitted
done	remote origin/entire/checkpoints/v1 (242a19bf797692964ea5368f7c1c38365be9dcbf)
apply rc=0
== 残っている ref
refs/heads/main
origin refs/heads/main
```
(パスの途中は `...` に省きました。省略のない形は `/private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-v3u49r_y/w/b989a81f5c/skills/...` です。)

**main 版で同じ手順を実行した結果(比較用)**
```
cd /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-v3u49r_y/w/b989a81f5c/skills/scratch; mkdir -p main-scripts; for f in apply.sh lib.sh scan.sh; do git show main:skills/housekeeping/scripts/$f > main-scripts/$f; done
sed "s#^S=.*#S=$PWD/main-scripts#" run2.sh > run2-main.sh; chmod +x run2-main.sh; F=$PWD/ok/fx
./setup.sh $F >/dev/null 2>&1; ./run2-main.sh $F 1 2>&1 | sed -n '/== apply/,$p'
```
```
== apply (偽装した保護対象の行)
mktemp: mkstemp failed on /var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/tmp.z5tUQigEVp: Operation not permitted
/private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-v3u49r_y/w/b989a81f5c/skills/scratch/main-scripts/apply.sh: line 22: : No such file or directory
apply rc=0
== 残っている ref
refs/heads/entire/checkpoints/v1
refs/heads/main
refs/heads/release/x
origin refs/heads/entire/checkpoints/v1
origin refs/heads/main
```

**出るべきだった出力**
変更の意図(一時ファイルが作れない環境で、壊れたまま先へ進まない)と既存の保護の仕様に従えば、結果は次のどちらかになるべきです。
- 保護対象を拒否する(`skipped	branch entire/checkpoints/v1: 保護対象`、`release/x` とリモートも同じ)。`残っている ref` には `entire/checkpoints/v1`、`release/x`、`origin entire/checkpoints/v1` が残る
- 一時ファイルを作れないことを error として報告し、何も削除せずに止まる

同じ実行で、scan.sh も `rc=1` で止まっています。ただしエラー文は `action: unbound variable` で、案内している「HOUSEKEEPING_TMPDIR で書き込める場所を指定する」を実行済みでも失敗します。また標準出力にはヘッダー行だけが出ています。新しいテストは「止まるなら標準出力は空」を前提にしていますが、この経路ではその前提が成り立ちません。scan.sh は止まるので、実害は apply.sh より小さいです。

---

## 補足
- **影響が出る条件**:カレントディレクトリにも書けない環境だけです。Claude Code の通常の sandbox はプロジェクトのディレクトリに書き込めるので、この条件に当たる可能性は低いと考えます。ただし起きた場合は、保護対象(`entire/*`、設定で保護したブランチ)をリモートまで削除します。元に戻しにくい結果です。
- **ヒアドキュメントを使う他の関数**:`hk_path_in_use` も `<<EOF` を使っているので、同じ条件で「使用中」の判定が外れると予想します。ただし実行して確かめていないので、指摘には入れていません。
- **lib.sh のコメント**:「macOS の mktemp はテンプレートを付けないと TMPDIR を見ない」の内容は正しいです。`TMPDIR=$PWD/scratch/t mktemp -d` を実行すると `/var/folders/.../T/tmp.aCKljzQ2pY` に作られました。

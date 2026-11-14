コミットメッセージには「挙動は変えない」とありますが、実行して確かめたところ、挙動が変わっている箇所が 2 つありました。どちらも、残すべきブランチを削除候補(`delete`)に回してしまいます。比較には、`main` 版の `scan.sh` を `scratch/scan.main.sh` に取り出したものを使いました。既存の `skill-dev/housekeeping/test.sh` は「全件成功」でした。つまり既存のテストでは、次の 2 つはどちらも検出されません。

---

## 1. `verify_pr_merged` の祖先判定の向きが逆になり、マージ後に足したコミットのあるブランチが削除候補になる

`git merge-base --is-ancestor "$sha" "$oid"` が `is_ancestor "$oid" "$sha"` に置き換わり、引数の順が入れ替わっています(`scan.sh:93`)。

再現の手順(`scratch/repro.sh`):
- `extra`:PR #1 がマージされた後に、手元でコミット `e2-after-merge` を 1 件足した
- `behind`:手元が PR の head より 1 コミット古い

**実行したコマンド**
```
echo "=== HEAD ==="; scratch/repro.sh "$PWD/skills/housekeeping/scripts/scan.sh"
echo "=== main ==="; scratch/repro.sh "$PWD/scratch/scan.main.sh"
```

**出力**
```
=== HEAD ===
action	kind	name	sha	path	reason
keep	branch	behind	93b16fb33462c59fbda962e034bcc18ba5959aeb		PR #2 のマージ後に追加コミットが 0 件ある
delete	branch	extra	aa5d26a07f9c20b45e75d60b4ab4d0d5c06fdb40		PR #1 マージ済み
--- 追加コミットの内容: e2-after-merge
=== main ===
action	kind	name	sha	path	reason
delete	branch	behind	7f2dc81bfa26bf8b44320ff86e972129e511fc09		PR #2 マージ済み
keep	branch	extra	33e66786926a64feeb951d347bd1563cb2661dc4		PR #1 のマージ後に追加コミットが 1 件ある
--- 追加コミットの内容: e2-after-merge
```

**出るべきだった出力**(`main` 版と同じ)
```
delete	branch	behind	...	PR #2 マージ済み
keep	branch	extra	...	PR #1 のマージ後に追加コミットが 1 件ある
```

HEAD 版では、まだどこにも取り込まれていないコミット `e2-after-merge` を持つ `extra` が `delete` になります。逆に `behind` は「追加コミットが 0 件ある」という矛盾した理由で `keep` になります。この関数はリモートブランチの判定(`scan.sh:230`)にも使われています。

---

## 2. ローカルに既定ブランチが無いと first-parent 履歴が空になり、未着手のブランチが「merge コミットで取り込み済み」として削除候補になる

変更前は、存在する ref だけを `rev-list` に渡していました。履歴が空なら `exit 1` で止まっていました。変更後は 2 つの ref を無条件に渡すので、片方が無いだけで `rev-list` が失敗し、空のファイルができます。さらに `exit 1` で止まる処理も消えています(`scan.sh:82`)。その結果、`on_first_parent` は「読めない」を表す 2 ではなく 1(first-parent 上に無い)を返します。そして `delete`(merge コミットで取り込み済み)の分岐に入ります。

再現の手順(`scratch/repro2.sh`):ローカルの `main` を削除して `origin/main` だけにし、`origin/main` から `fresh` を作ってコミットしない。

**実行したコマンド**
```
echo "=== HEAD ==="; scratch/repro2.sh "$PWD/skills/housekeeping/scripts/scan.sh"
echo "=== main ==="; scratch/repro2.sh "$PWD/scratch/scan.main.sh"
```

**出力**
```
=== HEAD ===
branch 'fresh' set up to track 'origin/main'.
refs/heads/main: なし
action	kind	name	sha	path	reason
delete	branch	fresh	ddcc345c50a4ee74be1654140d6072ce52a7a25f		PR なし・merge コミットで main に取り込み済み
keep	branch	work	ddcc345c50a4ee74be1654140d6072ce52a7a25f		worktree /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-inxy031r/w/9ffacf5861/skills/scratch/r.cR5f4n/repo で使用中
exit=0
=== main ===
branch 'fresh' set up to track 'origin/main'.
refs/heads/main: なし
action	kind	name	sha	path	reason
ask	branch	fresh	ddcc345c50a4ee74be1654140d6072ce52a7a25f		PR なし・main に含まれるが、作成後にコミットした記録がない(未着手の可能性)
keep	branch	work	ddcc345c50a4ee74be1654140d6072ce52a7a25f		worktree /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-inxy031r/w/9ffacf5861/skills/scratch/r.zrzQN1/repo で使用中
exit=0
```

**出るべきだった出力**(`main` 版と同じ)
```
ask	branch	fresh	...	PR なし・main に含まれるが、作成後にコミットした記録がない(未着手の可能性)
```

`fresh` は `origin/main` の先端そのものなので、実際は first-parent 上にあります。それなのに first-parent 履歴が空だったため、merge コミットで取り込まれたと誤って判定されました。本来は確認(`ask`)に回るはずのものが、`delete` になっています。

---

再現に使ったスクリプトと使い捨てリポジトリは `scratch/` に残しています。どちらの再現ケースも既存テストには含まれていないので、`test.sh` に加えておくと同じ後退を防げます。

「挙動は変えない」というコミットの意図に反する挙動の変化を、3件証明しました。うち1件は、main に取り込まれていないコミットをローカルとリモートの両方から消します。

既存の `skill-dev/housekeeping/test.sh` は HEAD でも「全件成功」のままで、3件とも検出しません。

再現には `scratch/repro.sh <scripts-dir> <場面>` を使いました。使い捨てリポジトリを `scratch/tmp/` に作り、bare の origin と偽の PR 一覧で `scan.sh` を走らせます。比較用に main 版のスクリプトを `scratch/main-scripts/` へ `git show main:...` で取り出しています。

## 1. PR マージ後に追加コミットがあるブランチを delete と判定し、apply で消える

`verify_pr_merged` で `is_ancestor` の引数が逆になっています(`scan.sh:93`)。元は `git merge-base --is-ancestor "$sha" "$oid"`、変更後は `is_ancestor "$oid" "$sha"` です。

場面: PR #1 を squash マージしたあと、`feat` にコミットを1件積んで push した。

実行したコマンド:
```
scratch/repro.sh skills/housekeeping/scripts extra
```

出力:
```
PR head: e9dfadf / feat: 8194a49 / main に無いコミット: 2 件(うち PR 後は 1 件)
scan.sh rc=0
delete	branch	feat	PR #1 マージ済み
delete	remote	feat	PR #1 マージ済み
done	branch feat (8194a496bee9fb0242fa46b33716b7e725c8ef8b)
done	remote origin/feat (8194a496bee9fb0242fa46b33716b7e725c8ef8b)
local feat: 消えた
remote feat: 消えた
after-merge-work は main に無い
```

出るべきだった出力(`scratch/repro.sh scratch/main-scripts extra` の実出力):
```
PR head: 9e8f3dc / feat: 5e8ce9a / main に無いコミット: 2 件(うち PR 後は 1 件)
scan.sh rc=0
keep	branch	feat	PR #1 のマージ後に追加コミットが 1 件ある
local feat: 残っている
remote feat: 残っている
after-merge-work は main に無い
```

`apply.sh` は先端の sha が走査時と同じかしか確かめないので、scan の誤判定がそのまま削除になります。

## 2. PR の head より古いだけのローカルブランチを keep と判定し、理由が「追加コミットが 0 件」になる

原因は 1 と同じ引数の逆転です。

場面: 手元の `feat` が PR の head より1コミット古い。PR は squash マージ済み。

実行したコマンド:
```
scratch/repro.sh skills/housekeeping/scripts behind
```

出力:
```
PR head: 3b457bc / local feat: 355c090 / PR head に無い手元のコミット: 0 件
scan.sh rc=0
keep	branch	feat	PR #1 のマージ後に追加コミットが 0 件ある
delete	remote	feat	PR #1 マージ済み
```

出るべきだった出力(`scratch/repro.sh scratch/main-scripts behind` の実出力):
```
PR head: d221f13 / local feat: 6c78b7a / PR head に無い手元のコミット: 0 件
scan.sh rc=0
delete	branch	feat	PR #1 マージ済み
delete	remote	feat	PR #1 マージ済み
```

## 3. ローカルの既定ブランチが無いと、PR なしのブランチがすべて「merge コミットで取り込み済み」の delete になる

`git rev-list --first-parent` に、存在を確かめずに ref を2つ渡しています(`scan.sh:82`)。片方が無いと rev-list 全体が失敗し、`first-parent` は空のファイルになります。元にあった「存在する ref だけ渡す」処理と、空なら `error: … の履歴を読めない` で止まる処理は、どちらも消えています。空のファイルに対する grep は 1 を返すので、「first-parent 上に無い」と読まれます。

場面: `refs/heads/main` が無く、`origin/main` だけがある。`fresh` は `origin/main` から作っただけで未着手、`ffed` は fast-forward で取り込み済み。

実行したコマンド:
```
scratch/repro.sh skills/housekeeping/scripts nolocal
```

出力:
```
branch 'fresh' set up to track 'origin/main'.
refs/heads/main: 無し / origin/main: 92b0db9
fresh の reflog: branch: Created from origin/main
scan.sh rc=0
delete	branch	fresh	PR なし・merge コミットで main に取り込み済み
delete	branch	ffed	PR なし・merge コミットで main に取り込み済み
```

出るべきだった出力(`scratch/repro.sh scratch/main-scripts nolocal` の実出力):
```
branch 'fresh' set up to track 'origin/main'.
refs/heads/main: 無し / origin/main: bcb5a5a
fresh の reflog: branch: Created from origin/main
scan.sh rc=0
ask	branch	fresh	PR なし・main に含まれるが、作成後にコミットした記録がない(未着手の可能性)
delete	branch	ffed	PR なし・main に取り込み済み(このブランチでコミットした記録がある)
```

`fresh` は ask から delete に変わり、未着手かどうかの確認が飛ばされます。`ffed` は delete のままですが、理由が事実と違います(merge コミットは存在しません)。

## 補足

- 作業ツリーの変更は `scratch/` の追加だけです。commit も push もしていません。
- 3 の逆向き(ローカルの main はあるが `origin/main` が無い)は実行していないので、指摘に含めていません。

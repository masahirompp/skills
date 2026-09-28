---
name: housekeeping
description: >-
  git リポジトリの後片付け。PR マージ済み・ローカルでマージ済みのブランチと、その worktree をまとめて削除する。
  作業中のもの(未コミットの変更、オープン PR、マージ後の追加コミット、使用中の worktree など)と監査用ブランチ(entire.io の entire/*)は残す。
  マージ済みブランチや不要になった worktree の掃除・整理を頼まれたときに使う。
---

# housekeeping — マージ済みブランチと worktree の後片付け

判定は `scripts/scan.sh` が行い、削除は `scripts/apply.sh` がユーザーの承認した行だけに対して行う。どれを消すかは scan.sh の出力を正とし、エージェントの目視判断で候補を足さない。消しすぎは取り返せないが、消し残しは次回の走査で拾える。

## 手順

### 1. 走査する

対象リポジトリの中(どの worktree からでもよい)で実行し、結果をファイルに残す。

```sh
<skill-dir>/scripts/scan.sh > "$TMPDIR/housekeeping-scan.tsv"
```

scan.sh は何も削除しない。副作用は、リモート追跡ブランチを最新にする `git fetch --prune` だけ。出力は TSV で、列は `action kind name sha path reason`。

| action | 意味 |
| --- | --- |
| `delete` | 削除候補 |
| `prune` | ディレクトリが消えた worktree の管理情報。`git worktree prune` で消える |
| `ask` | 判断材料が足りない。ユーザーに個別に確認する |
| `keep` | 残す |

`kind` は `worktree` / `branch` / `remote`(リモートブランチ)のいずれか。error で終了したらその内容を伝えて止まる。よくある原因は gh の未認証で、ユーザーに `! gh auth login` を案内する。

完了条件: scan.tsv の全行が、次の手順の4区分のどれかに入っている。

### 2. 一覧を提示する

次の4区分で見せる。worktree とそのブランチは1項目にまとめる(reason が「worktree … と一緒に消す」になっている branch 行が対応する)。

1. **削除するもの**(ローカルの `delete` と `prune`): 名前と reason。reason に「一緒に消える ignored ファイル」があれば必ず添える。`.env` など git 管理外のファイルは worktree と一緒に消え、復元できない
2. **確認が必要なもの**(`ask`): reason と、判断材料として最終コミットの日時とメッセージ(`git log -1 --format='%cr %s' <sha>`)
3. **リモートブランチ**(`kind` が `remote` の `delete` / `ask`): GitHub 上のブランチを消す外部操作なので、ローカルとは別枠にする
4. **残すもの**: reason ごとの件数の要約。監査用ブランチ(`entire/*`)を残したことは明記する

候補が1件も無ければ、残したものの要約を伝えて終わる。

### 3. 承認を得る

区分1はまとめて、区分2は項目ごとに、区分3はまとめて、それぞれ承認を取る。承認された行だけが次の手順に進む。

### 4. 削除する

承認された行を scan.tsv から抜き出して apply.sh に渡す。区分1をすべて承認した場合の例:

```sh
awk -F'\t' '$2 != "remote" && ($1 == "delete" || $1 == "prune")' "$TMPDIR/housekeeping-scan.tsv" \
  | <skill-dir>/scripts/apply.sh
```

`ask` の行やリモートブランチの行も、承認されたものは同じように行ごと渡す。apply.sh は、worktree → ローカルブランチ → リモートブランチの順に削除する。各行について削除の直前に、走査時から状態が変わっていないかを確かめ直す。変わっていれば、その行を `skipped` として飛ばす。

### 5. 報告する

- `done` の行: 削除したもの。ブランチは `git branch <name> <sha>` で復元できる(コミットが gc されるまで)ので、sha も一緒に伝える
- `skipped` の行: 走査後に作業が再開されたなど、消すべきでない状態に変わったもの。そのまま残し、理由を伝える

## 判定基準

「作業中」と「監査用」は、次の順で最初に当てはまった理由で残す。

1. 保護対象の名前: 既定ブランチ、`main` `master` `develop` `gh-pages`、`entire/*`、ユーザー設定のパターン(後述)
2. worktree の状態: メインの作業ツリー、ロック中(Claude Code のセッションが使っている worktree もこれに当たる)、scan.sh を実行している場所、プロセスがカレントディレクトリにしている、rebase / merge などが進行中、未コミットの変更や未追跡ファイルがある、`git status` を読めない
3. PR の状態: オープンな PR がある、別のオープン PR のベースになっている(消すとその PR が閉じる)、未マージのままクローズされた

残りを次のように判定する。

| 状況 | 判定 |
| --- | --- |
| PR マージ済みで、手元の先端が PR の head に含まれる(squash マージも含む) | `delete` |
| PR マージ済みだが、マージ後に追加コミットがある | `keep` |
| PR マージ済みだが、PR の head コミットを取得できず照合できない | `ask` |
| PR なし。merge コミットで既定ブランチに取り込み済み | `delete` |
| PR なし。既定ブランチに含まれ、このブランチでコミットした記録が reflog にある(fast-forward マージ) | `delete` |
| PR なし。既定ブランチに含まれるが、コミットした記録が無い(作成直後で未着手の可能性) | `ask` |
| PR なし。既定ブランチに未取り込みのコミットがある | `keep` |
| detached HEAD の worktree で、既定ブランチに含まれるコミットを指している | `delete` |

リモートブランチは、PR マージ済みで先端が PR の head に含まれるものだけを候補にする。PR の無いリモートブランチは一覧にも出さない。

entire.io は、記録用のブランチ `entire/checkpoints/v1` と、セッション中だけ使う一時ブランチ `entire/<commit>-<worktree>` を作る。どちらも `entire/*` として保護する。一時ブランチの後始末は Entire 自身(`entire clean`)に任せる。ref 方式で使う `refs/entire/...` は、scan.sh の走査範囲(`refs/heads` と `refs/remotes`)の外にある。

## 設定と前提

- 保護するブランチ名は glob パターンで足せる。リポジトリごとの設定は `git config --add housekeeping.protect 'release/*'` で、その場限りなら環境変数 `HOUSEKEEPING_PROTECT='release/* sandbox'` で指定する
- 対象のリモートは `origin`。変えるときは `HOUSEKEEPING_REMOTE` を使う。PR は、そのリモートの GitHub リポジトリから `gh` で取得する
- fork から upstream へ PR を出す運用には対応していない。PR が見つからないので「PR なし」として判定され、未取り込みのコミットがあるブランチは残る

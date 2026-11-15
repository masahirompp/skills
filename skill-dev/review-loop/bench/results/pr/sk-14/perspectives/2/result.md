PR #1 は全体として妥当です。原因を「macOS の `mktemp` はテンプレートを付けないと TMPDIR を見ない」と特定した点は手元で再現できました(`TMPDIR=/nonexistent mktemp` が `/var/folders/...` に作る)。対処も原因に合っています。`skill-dev/housekeeping/test.sh` は全件成功しました。ただし、追加された apply.sh のテストは macOS では修正前のコードでも通ってしまい、回帰を検出できません。

## 正確性

- **`skill-dev/housekeeping/test.sh:185-186` — apply.sh のテストが macOS で回帰を検出できない(要修正)**
  - 修正前の `mktemp` はテンプレートなしなので、macOS では `TMPDIR` を見ずに `/var/folders/...` に作れてしまいます。そのため `TMPDIR="$root/no-such-dir"` を渡しても失敗しません。
  - 一時ディレクトリに test.sh 一式をコピーし、apply.sh だけ `main` 版に戻して走らせたところ、apply のテストは全件 ok でした。
  - つまりこのテストが修正前のコードで落ちるのは GNU mktemp の環境(Linux)だけで、不具合が起きる macOS では意味がありません。
  - 直し方の案: macOS では `sandbox-exec -p '(version 1)(allow default)(deny file-write* (subpath "/private/tmp") (subpath "/private/var/folders"))'` の下で apply.sh を実行し、実際の失敗条件を再現します。手元では、この条件で `mktemp` が `Operation not permitted` で失敗することを確認しました。
- `skills/housekeeping/scripts/apply.sh:21,29` — 変数に持つ方式に問題は見当たりません。
  - 入力が空なら `printf '%s\n' ""` は空行1行になりますが、`$2 == k` に一致しないので動作は変わりません。
  - `grep` が1行も出さず終了コード 1 になっても、`set -e` が無いので止まりません。
- 確認済みで問題なし: lib.sh の 48・67 行目と scan.sh のヒアドキュメント。
  - bash 3.2 は一時ファイルを使うのではと疑いましたが、`/tmp` と `/var/folders` への書き込みを禁止した sandbox-exec の中でも、300KB のヒアドキュメントが正常に動きました。
  - したがって、`hk_path_in_use` が失敗して「使用中ではない」と誤判定する経路はありません。
- `skill-dev/housekeeping/test.sh:172-175`(軽微)— 「片付ける」テストは、`hk-tmp` に一度も作られなかった場合でも空なので通ります。
  - 「HOUSEKEEPING_TMPDIR を使う」ことは 162-170 行目のエラー経路のテストで間接的に担保されているので、実害は小さいです。
  - 厳密にするなら、`HOUSEKEEPING_PR_JSON` の読み込み中に `hk-tmp` の下にディレクトリがあることを確かめる方法があります。

## セキュリティ

- `skills/housekeeping/scripts/lib.sh:19` — `/tmp` に落ちた場合も `mktemp -d` が推測できない名前と 0700 で作るので、ほかのユーザーに先回りされる心配はありません。
- **`skills/housekeeping/SKILL.md:35` — `!` がサンドボックスの外で動くことを確認してください(確認事項)**
  - この案内は「`!` で実行すればサンドボックスの外で動く」ことを前提にしています。私はこの前提を検証していません。
  - 外で動かないなら、案内しても同じエラーが繰り返されるだけです。Claude Code での実際の挙動を確かめておくべきです。

## 並行性

- `skills/housekeeping/scripts/lib.sh:19` — 実行ごとに名前の違うディレクトリを作るので、scan.sh を同時に走らせても衝突しません。指摘はありません。
- `skills/housekeeping/scripts/scan.sh:30-34` — `mktemp` から `trap` 設定までの間にシグナルを受けると、ディレクトリが残ります。理屈の上だけの話で、対応は不要です。

## プライバシー

- `skills/housekeeping/SKILL.md:35`(軽微)— `! scan.sh > <ファイル>` で出力したファイルには、ブランチ名・worktree の絶対パス・PR 番号が入ります。
  - 読み終えたあと消す手順が書かれていないので、エージェント側の `$TMPDIR` に残り続けます。
  - 「読み込んだら削除する」の一文を足すと、このスキル(後片付け)の趣旨とも合います。

## 設計

- **`skills/housekeeping/SKILL.md:35` — apply.sh を `!` で実行するときのコマンドの形が書かれていない**
  - 「手順4の apply.sh が同じ理由で失敗したときも、同じように `!` で実行してもらう」とありますが、apply.sh は承認した行を標準入力で受け取ります。scan.sh のように `! <script> > <file>` では実行できません。
  - `! awk -F'\t' '$1=="delete"||$1=="prune"' <承認済みTSV> | <skill-dir>/scripts/apply.sh` のような具体的な形を書かないと、エージェントがそのつど組み立てることになり、そこで間違える余地が生まれます。
  - apply.sh は一時ファイルを使わなくなったので、サンドボックスで失敗するとすれば理由は別です(push の通信、worktree の外への書き込みなど)。「同じ理由で」という書き方も正確ではありません。
- `skills/housekeeping/scripts/lib.sh:6`(軽微)— `HOUSEKEEPING_TMPDIR` を使うのは scan.sh だけなのに、lib.sh の共通の環境変数一覧に載っています。
  - 一覧は「scan.sh と apply.sh の共通部分」と説明されているので、apply.sh でも効くように読めてしまいます。
  - scan.sh の環境変数一覧(12-14 行目)に移すか、「scan.sh のみ」と書き添えるのがよいです。
- 専用の環境変数が必要かどうか: テンプレートを付けた時点で `TMPDIR` は効くようになるので、`HOUSEKEEPING_TMPDIR` が無くても今回の問題は直ります。
  - 一方で、`TMPDIR` を変えると git や gh にも影響します。スクリプトの一時ディレクトリだけを変えられる専用の変数には意味があり、残してよいと判断します。

## 優先度

1. `test.sh:186` のテストを、macOS でも修正前のコードで落ちる形にする
2. `SKILL.md:35` の apply.sh を `!` で実行するときのコマンドの形を明記する
3. `!` がサンドボックスの外で動くか確認する

残りの指摘は軽微です。作業ツリーは変更していません。検証用のコピーは一時ディレクトリに作り、終わったあと削除しました。

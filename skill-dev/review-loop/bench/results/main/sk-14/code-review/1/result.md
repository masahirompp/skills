差分(main...HEAD)を 8 つの観点で確認しました。いちばん重いのは、「apply.sh は一時ファイルを使わない」という前提が macOS 標準の bash 3.2 では成り立たない点です。この環境の bash は `/bin/bash` 3.2.57 の 1 つだけで、bash 3.2 の here-document は一時ファイルとして作られます。`sandbox-exec` で `/tmp`・`/var` 以下への書き込みを禁じて試すと、`cannot create temp file for here document` で `while ... done <<EOF` が一度も回らず、保護判定の関数が「保護対象ではない」(戻り値 1)を返しました。下の 1〜3 はこの挙動から出てくる問題です。

なお、リポジトリ内に CLAUDE.md はありません。ユーザー側の CLAUDE.md は対話の方針だけでコードの規約を含まないので、規約違反の指摘はありません。

8 findings, most severe first:

1. `skills/housekeeping/scripts/apply.sh:21`: apply.sh は一時ファイルを使わないという前提が誤っている。lib.sh の hk_is_protected は here-document で保護パターンを読むが、bash 3.2 ではこれが一時ファイルになり、作れないと保護判定が『保護対象ではない』側に倒れる。

   Failure scenario: /usr/bin/env bash が macOS の bash 3.2 を指し、TMPDIR・/tmp・/var/tmp のどれにも書けないサンドボックスで apply.sh を実行する。hk_is_protected の `done <<EOF` が失敗して return 1 になり、承認済み入力に紛れた `delete branch entire/checkpoints/v1` の行や保護パターンに当たるリモートブランチが『保護対象』で止まらずに削除される(sandbox-exec で here-document の失敗と return 1 になることを再現した)。

2. `skills/housekeeping/scripts/lib.sh:67`: hk_path_in_use も here-document で lsof の結果を awk に渡している。一時ファイルを作れないと空を返し、使用中の worktree を『未使用』と判定する。

   Failure scenario: 上と同じ書き込めない環境で apply.sh を実行する。apply.sh の 42 行目で proc が空になり、別プロセスがカレントディレクトリにしている worktree を git worktree remove で消してしまう。

3. `skills/housekeeping/scripts/scan.sh:34`: HOUSEKEEPING_TMPDIR は mktemp の場所だけを変え、bash の here-document(classify_branch の read、hk_is_protected、pr_info の受け取りなど)は TMPDIR か /tmp 系に作られる。エラーメッセージの案内どおり HOUSEKEEPING_TMPDIR を指定すると、走査は進むが判定が壊れる。

   Failure scenario: TMPDIR と /tmp が書けないので HOUSEKEEPING_TMPDIR=~/hk を指定して scan.sh を実行する。mktemp は成功するが here-document の作成に失敗する。`IFS=$'\t' read -r action reason <<EOF` が実行されず、ブランチのループでは前のブランチの action=delete が残ったまま emit され、hk_is_protected も main を保護しない。誤った delete 行がユーザーへの承認に回る。根本的な直し方は、作った $tmp を `TMPDIR=$tmp` として子プロセスにも渡すことと、lib.sh の here-document をパイプに置き換えて失敗時に止まる作りにすること。

4. `skill-dev/housekeeping/test.sh:186`: 『書き込めない TMPDIR でも apply.sh が動く』テストは、bash が存在しない TMPDIR を無視して /tmp に切り替えるため、一時ファイルを作れない状況を再現できていない。

   Failure scenario: TMPDIR=$root/no-such-dir でも bash 3.2 は here-document を /tmp に作るので、テストは常に通る。apply.sh が lib.sh 経由で一時ファイルに頼っていること(1・2)を見逃し、SKILL.md の『apply.sh は一時ファイルを使わない』を誤って裏付けている。

5. `skill-dev/housekeeping/test.sh:175`: 『一時ディレクトリは HOUSEKEEPING_TMPDIR の下に作る』テストは、終了後に hk-tmp が空かどうかしか見ていない。HOUSEKEEPING_TMPDIR が無視されても通る。

   Failure scenario: hk_mktemp_dir が HOUSEKEEPING_TMPDIR を読まなくなる退行が入っても、hk-tmp は空のままなので『片付ける』テストは pass し、退行に気づけない。

6. `skills/housekeeping/SKILL.md:98`: 『作れなければ何もせずに止まる』は事実と違う。scan.sh は一時ディレクトリを作る前に git fetch --prune を実行し、hk_default_branch 経由で gh repo view を呼ぶこともある。

   Failure scenario: 一時ディレクトリを作れない環境で scan.sh を実行すると、エラーで止まるまでにリモート追跡ブランチの prune が済んでいる。文書を信じたユーザーやエージェントは副作用がないと誤解する。mktemp を fetch より前に移すか、記述を直す必要がある。

7. `skills/housekeeping/scripts/scan.sh:31`: エラーメッセージで `${HOUSEKEEPING_TMPDIR:-${TMPDIR:-/tmp}}` を組み直しており、hk_mktemp_dir 内の base の決め方と重複している。

   Failure scenario: hk_mktemp_dir の既定の場所を変えたときにメッセージ側を直し忘れると、実際とは違うディレクトリ名を案内してしまう。hk_mktemp_dir が失敗時に場所を含むエラーを自分で出せば、重複がなくなる。

8. `skills/housekeeping/SKILL.md:35`: apply.sh を `!` で実行してもらう案内には、承認済みの行を標準入力に流す形(awk ... scan.tsv | apply.sh)と絶対パスの書き方が示されていない。

   Failure scenario: エージェントが scan.sh と同じ形で `! <skill-dir>/scripts/apply.sh` だけを案内すると、apply.sh は端末からの入力を待って止まるか、入力が空のまま何もせずに終わる。ユーザーは削除が終わったと誤解しうる。

直し方は 3 の説明に書いた方針(子プロセスに TMPDIR を渡すことと、here-document をパイプに置き換えて失敗時に止めること)が中心になります。

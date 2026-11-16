PR #1(ブランチ `housekeeping-mktemp`、コミット be0ad06)の差分をレビューし、7件の指摘が残りました。最も重いのは1件目です。macOS 標準の bash 3.2 ではヒアドキュメントが一時ファイルを使うため、「apply.sh は一時ファイルを使わない」という記述は成り立ちません。しかも書けなかったときは、保護ブランチや使用中の worktree を消してしまう側に倒れます。

確かめたこと:
- `/usr/bin/env bash` はこの環境で bash 3.2.57 に解決されます。
- `TMPDIR=/nonexist` でもヒアドキュメントは `/tmp` に退避して動きます(rc=0)。
- テンプレートなしの macOS `mktemp -d` は TMPDIR を見ずに `/var/folders/...` を使います。`lib.sh` のコメントどおりです。

指摘2〜3は、どちらもテストが本来確かめたい性質を確かめていないという問題です。CLAUDE.md は、ユーザー直下のものが思考スタイルの指示だけで、リポジトリ側には無いため、規約違反はありません。

7 findings, most severe first:

1. `skills/housekeeping/scripts/lib.sh:48`: hk_is_protected と hk_path_in_use(67行目)はヒアドキュメントを使っている。bash 5.1 未満(macOS 標準の 3.2)ではヒアドキュメントが TMPDIR か /tmp に一時ファイルを作るので、SKILL.md 98行目の『apply.sh は一時ファイルを使わない』は誤り。作れなかったときは保護・使用中の判定が素通りになる。

   Failure scenario: サンドボックスで TMPDIR も /tmp も書けない状態で apply.sh を実行すると『cannot create temp file for here-document』で while/awk が実行されない。hk_is_protected は return 1(保護対象でない)を返し、hk_path_in_use は空(使用中でない)を返す。その結果、entire/* や main の偽装行、プロセスが使っている worktree が削除に進む。

2. `skill-dev/housekeeping/test.sh:186`: TMPDIR を存在しないディレクトリにして apply.sh を走らせても『一時ファイルを使わない』ことは確かめられない。bash はヒアドキュメント用の一時ファイルを /tmp に退避して作るため、テストは常に通る。

   Failure scenario: apply.sh に一時ファイルへの依存が戻っても(既存のヒアドキュメントも含めて)、TMPDIR=/nonexist で bash は /tmp を使って成功するのでこのテストは pass し、回帰を見逃す。

3. `skill-dev/housekeeping/test.sh:175`: 『HOUSEKEEPING_TMPDIR の下に作り、終了時に消す』のテストは hk-tmp が空かどうかしか見ていない。HOUSEKEEPING_TMPDIR が無視されて別の場所に作られても pass する。

   Failure scenario: hk_mktemp_dir が HOUSEKEEPING_TMPDIR を読まずに TMPDIR を使うよう壊れても、hk-tmp には何も作られないので `ls -A` は空になり『片付ける』が pass する。作成場所の検証になっていない。

4. `skills/housekeeping/scripts/scan.sh:22`: 一時ディレクトリの作成が git fetch --prune と hk_default_branch(gh を呼ぶ)の後にある。作れずに止まる場合もリモート追跡ブランチの prune は済んでおり、SKILL.md の『作れなければ何もせずに止まる』と食い違う。

   Failure scenario: HOUSEKEEPING_TMPDIR が書けない状態で scan.sh を実行すると、fetch --prune でリモート追跡ブランチを消してから『一時ディレクトリを作れない』で終了する。文書と違う副作用が残る。hk_mktemp_dir を fetch より前に移せば解消する。

5. `skills/housekeeping/SKILL.md:35`: apply.sh を『同じように ! で実行』と案内しているが、手順4の例は "$TMPDIR/housekeeping-scan.tsv" をそのまま使っている。ユーザーのシェルでは別のパスに展開され、apply.sh に何も渡らないまま成功で終わりうる。

   Failure scenario: エージェントが手順4のパイプラインをそのまま `!` で案内すると、ユーザー側の $TMPDIR に scan.tsv は無いので awk はファイル無しのエラーを出し、apply.sh は空入力で exit 0 になる。何も削除されないのに失敗の行が出ず、エージェントが完了と誤認しうる。apply のパイプラインでも絶対パスに展開するよう明記すべき。

6. `skills/housekeeping/scripts/scan.sh:31`: エラーメッセージが一時ディレクトリの場所の決め方 `${HOUSEKEEPING_TMPDIR:-${TMPDIR:-/tmp}}` を lib.sh の hk_mktemp_dir と二重に持っている。

   Failure scenario: hk_mktemp_dir の既定値の順序や場所を変えたときに scan.sh 側を直し忘れると、実際に試した場所とは違うパスをエラーに表示し、利用者が誤った HOUSEKEEPING_TMPDIR を設定する。hk_mktemp_dir 自身が決めた場所を含めてエラーを出せば重複は消える。

7. `skills/housekeeping/scripts/lib.sh:20`: mktemp -d が成功した直後の `[ -n "$d" ] && [ -d "$d" ]` は余分な確認で、`d=$(mktemp ...) || return 1` だけで同じ働きになる。

   Failure scenario: 実害はないが、成功時に空や非ディレクトリが返る前提の防御コードが残り、何を防いでいるのか読み手が追う手間が増える。

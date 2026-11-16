レビューしたのは現在のブランチ `housekeeping-mktemp` の PR(main...HEAD の差分)です。指定の `1` に対して `gh pr view 1` がこのブランチの PR を返したので、これを対象としました。

いちばん重い指摘は1件目で、実際に再現しています。`sandbox-exec` で `/tmp` と `/var` への書き込みを禁止すると、bash 3.2 がヒアドキュメント用の一時ファイルを作れなくなり、`hk_is_protected main main` は保護なしを返し、`hk_path_in_use` は空を返しました。どちらも安全側ではなく危険側に倒れます。PR と SKILL.md は「apply.sh は一時ファイルを使わない」としていますが、実際は lib.sh のヒアドキュメントが一時ファイルを使っています。

対照的に、lib.sh のコメントにある「macOS の mktemp はテンプレートなしだと TMPDIR を見ない」は手元で確かめて正しいとわかりました。指摘には含めていません。適用される CLAUDE.md は ~/.claude/CLAUDE.md だけで、コード規約にあたる規則は無いため、規約の観点では指摘なしです。

8 findings, most severe first:

1. `skills/housekeeping/scripts/lib.sh:48`: hk_is_protected と hk_path_in_use はヒアドキュメントを使い、bash 3.2 ではヒアドキュメントが一時ファイルを作る(bash 5.1 以降でもパイプの容量を超える lsof の出力なら一時ファイルになる)。このため一時ディレクトリに書けない環境では、保護判定と使用中判定がどちらも危険側に倒れる。PR は apply.sh から mktemp を除いて『一時ファイルを使わない』としたが、本当の弱点はここに残っている。

   Failure scenario: TMPDIR・/tmp・/var/tmp のどれにも書けないサンドボックス(sandbox-exec で再現済み)で apply.sh を実行すると、『cannot create temp file for here document』で while/awk が動かない。hk_is_protected は return 1(保護対象でない)を、hk_path_in_use は空(使用中でない)を返す。その結果、entire/* や develop の行が入力に混ざれば git branch -D / push --delete まで進み、プロセスが使っている worktree も git worktree remove に進む。

2. `skills/housekeeping/scripts/scan.sh:30`: HOUSEKEEPING_TMPDIR が効くのは scan.sh の作業ディレクトリだけで、bash のヒアドキュメント(lib.sh の hk_is_protected、scan.sh の 98・156・197・218 行など)の一時ファイルは引き続き TMPDIR か /tmp に作られる。エラーメッセージは HOUSEKEEPING_TMPDIR を指定するよう案内しているが、それに従うと走査が先へ進み、判定だけが壊れた TSV を出してしまう。

   Failure scenario: TMPDIR と /tmp に書けない環境で、エラーの案内に従って HOUSEKEEPING_TMPDIR=~/writable を指定して scan.sh を実行する。mktemp は成功するが、ヒアドキュメントは失敗する。そのため hk_is_protected が main や develop を保護対象と判定できず、マージ済みの develop が delete として出力される。また `read st num oid <<EOF` も空になり、PR の状態が NONE 扱いになる。tmp を作った直後に `export TMPDIR="$tmp"` すれば、ヒアドキュメントも同じ場所を使う。

3. `skill-dev/housekeeping/test.sh:186`: 『一時ファイルを使わないので、書き込めない TMPDIR でも動く』テストは、bash が存在しない TMPDIR を無視して /tmp に戻るから通っているだけで、主張していることを検証できていない。

   Failure scenario: TMPDIR=$root/no-such-dir にすると、bash 3.2 の get_tmpdir は TMPDIR を捨てて /tmp にヒアドキュメント用の一時ファイルを作るので、テストは通る。しかし /tmp にも書けない本当のサンドボックスでは、1件目の指摘のとおり保護判定が危険側に倒れる。テストが通ることで、この退行が見えなくなる。

4. `skills/housekeeping/SKILL.md:98`: 『apply.sh は一時ファイルを使わない』という記述が事実と違う。lib.sh を source して使うヒアドキュメントが一時ファイルを作る。

   Failure scenario: エージェントやユーザーがこの記述を信じ、一時ディレクトリに書けない環境でも apply.sh なら安全だと考えてそのまま実行する。その結果、保護判定と使用中判定が黙って無効になったまま削除が進む。

5. `skills/housekeeping/SKILL.md:35`: apply.sh がサンドボックスの制限で失敗したときに『同じように ! で実行してもらう』と書いてあるが、apply.sh は承認済みの行を標準入力で受け取るので、scan.sh と同じ形(`! <path>/apply.sh`)では動かない。awk でフィルタしてパイプで流す形と、絶対パスへの展開をどうするかが書かれていない。

   Failure scenario: エージェントが `! /abs/skills/housekeeping/scripts/apply.sh` だけを案内する。標準入力が端末なら grep が入力待ちで止まり、空入力なら何も消さずに終わる。scan.tsv の場所を相対パスや $TMPDIR で書くと、ユーザーのシェルでは別の場所を指してしまう。

6. `skill-dev/housekeeping/test.sh:175`: 『一時ディレクトリを HOUSEKEEPING_TMPDIR の下に作り、終了時に消す』テストは、終了後に hk-tmp が空であることしか見ていない。HOUSEKEEPING_TMPDIR が無視されて別の場所に作られても通る。

   Failure scenario: hk_mktemp_dir が後の変更で HOUSEKEEPING_TMPDIR を見なくなり、/var/folders に作るように戻っても、hk-tmp は空のままなので pass になり、退行を検出できない。走査中に hk-tmp/housekeeping.* が存在することを確かめる(たとえば HOUSEKEEPING_PR_JSON の読み込み時に見る)などの検証が必要。

7. `skills/housekeeping/scripts/scan.sh:31`: 一時ディレクトリの既定値を決める式 `${HOUSEKEEPING_TMPDIR:-${TMPDIR:-/tmp}}` が、lib.sh の hk_mktemp_dir と scan.sh のエラーメッセージの2か所にそのまま重複している。

   Failure scenario: 既定値の決め方(たとえば /var/tmp も候補に足す)を lib.sh だけ直すと、エラーメッセージが実際に試した場所と違うパスを表示し、ユーザーが誤った場所を直してしまう。hk_mktemp_dir の中でエラーを出すか、base を lib.sh の変数にすれば1か所で済む。

8. `skills/housekeeping/scripts/lib.sh:20`: `[ -n "$d" ] && [ -d "$d" ] || return 1` は、直前の mktemp -d が成功している以上は常に真で、実質的に意味のない検査になっている。

   Failure scenario: 保守するときに、mktemp が成功しても空を返す場合があるかのように読めて、余計な防御コードを増やす根拠になる。`mktemp -d ... || return 1` の1行で同じ役割を果たせる。

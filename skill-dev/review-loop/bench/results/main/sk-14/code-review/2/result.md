8 findings, most severe first:

1. `skills/housekeeping/scripts/lib.sh:49`: SKILL.md とテストは「apply.sh は一時ファイルを使わない」としているが、hk_is_protected と hk_path_in_use は here-doc を使っており、/bin/bash 3.2 では here-doc ごとに $TMPDIR(書けなければ /tmp)に一時ファイルを作る。作成に失敗したときは安全側でなく危険側に倒れる。

   Failure scenario: サンドボックスで $TMPDIR が access() では書き込み可と判定されるのに実際の書き込みは拒否される環境で apply.sh を実行する。here-doc のリダイレクトが失敗して while read が1回も回らず、hk_is_protected は return 1(保護対象ではない)を返す。main や entire/* の行が混ざっていれば git branch -D / push :ref が実行される。hk_path_in_use も空を返すので、使用中の worktree が「使用中ではない」として remove される。

2. `skills/housekeeping/scripts/lib.sh:18`: HOUSEKEEPING_TMPDIR は mktemp のテンプレートにしか効かない。scan.sh の here-doc(98, 110, 156, 197, 203, 218, 222 行)と子プロセス(gh, git, jq)は元の TMPDIR を使い続けるため、エラーメッセージが勧める回避策では根本原因が解決しない。

   Failure scenario: $TMPDIR に書けないサンドボックスで、ユーザーがエラーメッセージに従って HOUSEKEEPING_TMPDIR=書ける場所 を指定する。mktemp は通るが、here-doc の一時ファイルは書けない $TMPDIR に作ろうとして失敗し、read が空の action/reason を受け取って誤った判定行や空行が TSV に出る。export TMPDIR="$base" で一本化するか、独自の変数をやめて TMPDIR だけを尊重するほうが根本的な修正になる。

3. `skills/housekeeping/scripts/scan.sh:30`: 一時ディレクトリを作る処理と失敗時の停止が、git fetch --prune と hk_default_branch(gh repo view を呼ぶことがある)の後にある。そのため SKILL.md の「作れなければ何もせずに止まる」と食い違う。

   Failure scenario: 一時ディレクトリを作れない環境で scan.sh を実行すると、ネットワーク越しの fetch --prune でリモート追跡ブランチを消したり gh を呼んだりした後に error で終わる。副作用と待ち時間が発生したうえで止まり、ドキュメントの記述とも合わない。hk_mktemp_dir を 19 行目の直後に移すべき。

4. `skill-dev/housekeeping/test.sh:186`: apply.sh に TMPDIR=存在しないディレクトリ を渡すテストは回帰を検出できない。macOS の mktemp はテンプレートが無いと TMPDIR を無視するため、変更前のコード(input=$(mktemp))でも成功する。

   Failure scenario: 誰かが apply.sh に mktemp を戻しても、macOS ではこのテストは pass のままになる。here-doc についても bash は存在しない TMPDIR を見ると /tmp に切り替えるので、「一時ファイルを使わない」という主張はまったく検証されていない。

5. `skill-dev/housekeeping/test.sh:175`: 「一時ディレクトリを片付ける」テストは hk-tmp が空かどうかしか見ていない。scan.sh が HOUSEKEEPING_TMPDIR を無視して別の場所に作っても pass してしまい、テストの意図(HOUSEKEEPING_TMPDIR の下に作ること)を検証していない。

   Failure scenario: hk_mktemp_dir がテンプレート無しの mktemp -d に戻され、/var/folders に作るようになっても hk-tmp は空のままなので ok になる。実行中に hk-tmp の下にディレクトリができたことを確かめる必要がある(例: HOUSEKEEPING_PR_JSON の読み込み時に ls するフックを入れる、trap を無効にして残ったものを確認する)。

6. `skills/housekeeping/SKILL.md:35`: 「apply.sh が同じ理由で失敗したときも、同じように `!` で実行してもらう」とあるが、apply.sh は承認済みの行を標準入力で受け取る。リダイレクトを含むコマンドの形が示されていないので、ユーザーが入力無しで実行しうる。

   Failure scenario: ユーザーが `! .../apply.sh` とだけ実行すると、標準入力が空なら input が空になり、何も消さずに exit 0 で終わる(成功に見える)。端末につながっていれば入力待ちで止まる。scan.sh と同様に `! awk -F'\t' '$1=="delete"||$1=="prune"' <承認済みファイル> | <skill-dir>/scripts/apply.sh` のような完成形を示すべき。

7. `skills/housekeeping/scripts/scan.sh:31`: 一時ディレクトリの場所を決める式 ${HOUSEKEEPING_TMPDIR:-${TMPDIR:-/tmp}} が lib.sh の hk_mktemp_dir とエラーメッセージに重複しており、片方だけ変えると表示と実際の場所がずれる。

   Failure scenario: 既定値の決め方を lib.sh 側で変えても scan.sh のメッセージは古い式のままで、ユーザーに誤ったパスを案内する。hk_mktemp_dir の中でエラーを出すか、場所を返す関数(例: hk_tmp_base)に切り出して両方から呼ぶとよい。

8. `skills/housekeeping/scripts/lib.sh:20`: mktemp -d が成功した後の [ -n "$d" ] && [ -d "$d" ] の検査は冗長で、mktemp の終了コードの確認で足りる。

   Failure scenario: 実害は無いが、守っているのが何なのか読み手に分かりにくい。d=$(mktemp -d ...) || return 1 と printf だけで同じ働きになる。

レビュー対象は PR #1(ブランチ `housekeeping-mktemp`、`main...HEAD`、5ファイル)です。既存のテスト `skill-dev/housekeeping/test.sh` はローカルで全件通りました。

明確なバグは見つかっていません。下の6件は、ドキュメントと実際の動作のずれ、テストの穴、細かな整理点です。

確認して指摘から外したものが2点あります。
- `lib.sh` のコメント(macOS の `mktemp -d` はテンプレートが無いと TMPDIR を見ない)は、この環境で実際に試して正しいと分かりました。`TMPDIR=/tmp/hkx mktemp -d` を実行しても `/var/folders/...` に作られます。
- 該当する CLAUDE.md はユーザー全体用の1つだけで、内容は応答の姿勢についての規則です。この diff に当てはまるコーディング規約はありません。

6 findings, most severe first:

1. `skills/housekeeping/scripts/scan.sh:30`: 一時ディレクトリの作成が `git fetch --prune` の後にあるため、SKILL.md の「作れなければ何もせずに止まる」と食い違い、サンドボックスでは本来のエラーに届く前にネットワーク処理を走らせてしまう。

   Failure scenario: HOUSEKEEPING_TMPDIR や TMPDIR に書き込めない環境で scan.sh を実行すると、先に `git fetch --prune` が動いてリモート追跡ブランチが削除される(副作用が起きる)。その後で「一時ディレクトリを作れない」と止まる。サンドボックス内では fetch 自体も失敗したり待たされたりし、warn が出てから本来の原因が出るので診断が遅れる。hk_mktemp_dir の呼び出しを fetch より前(git rev-parse の直後)に移せば、文書どおり何もせずに止まる。

2. `skills/housekeeping/SKILL.md:98`: 「作れなければ何もせずに止まる」と書いてあるが、現在の実装では fetch --prune を済ませてから止まるので、記述が実際の動作と合っていない。

   Failure scenario: エージェントやユーザーがこの記述を信じ、一時ディレクトリのエラーで止まった scan.sh は副作用を起こしていないと判断する。実際にはリモート追跡ブランチの prune がもう反映されている。上の指摘どおり順序を直すか、文書を「fetch のあと止まる」に直す必要がある。

3. `skill-dev/housekeeping/test.sh:174`: 後片付けのテストは HOUSEKEEPING_TMPDIR の下が空かどうかしか見ていない。scan.sh が HOUSEKEEPING_TMPDIR を無視して別の場所に作っても通ってしまい、コメントにある「HOUSEKEEPING_TMPDIR の下に作り」を検証していない。

   Failure scenario: 将来の変更で hk_mktemp_dir が HOUSEKEEPING_TMPDIR を見なくなり、$TMPDIR の下に作って消し忘れるようになっても、hk-tmp は最初から空なので `[ -z "$(ls -A ...)" ]` が成り立ち pass になる。作られる場所の検証は、直前の no-such-dir のテストに間接的に頼っているだけになっている。HOUSEKEEPING_TMPDIR を外した場合に TMPDIR が使われる経路のテストも無い。

4. `skills/housekeeping/scripts/scan.sh:31`: 一時ディレクトリの場所を決める式 `${HOUSEKEEPING_TMPDIR:-${TMPDIR:-/tmp}}` が、lib.sh の hk_mktemp_dir とエラーメッセージの2か所に重複している。

   Failure scenario: 既定値の決め方を lib.sh 側だけ変えると(例えば /tmp に戻す条件を足すと)、エラーメッセージには実際とは違うパスが出て、ユーザーが間違った場所を調べることになる。hk_mktemp_dir がエラーを自分で出すか、場所を返す hk_tmp_base を作って両方から呼ぶ形にすれば、重複は1か所にまとまる。

5. `skills/housekeeping/scripts/lib.sh:18`: HOUSEKEEPING_TMPDIR で直るのはスクリプト自身の一時ディレクトリだけで、子プロセス(gh、jq、git)は書き込めない TMPDIR をそのまま引き継ぐ。サンドボックスの問題を根本から避けられていない。

   Failure scenario: TMPDIR に書き込めず、HOUSEKEEPING_TMPDIR だけを書き込める場所にしたサンドボックスで、`gh pr list` などが TMPDIR に一時ファイルを書こうとすると Operation not permitted で失敗し、「PR 一覧を取得できない」で止まる。作成した $tmp を `export TMPDIR="$tmp"` として子プロセスにも渡せば、同じ仕組みでまとめて避けられる。

6. `skills/housekeeping/SKILL.md:35`: apply.sh を `!` で実行してもらう場合の案内が「同じように」だけで、標準入力に承認済みの行を流す形や、実行する場所(対象リポジトリ)が書かれていない。

   Failure scenario: エージェントが scan.sh と同じ形で `! <skill-dir>/scripts/apply.sh` だけを案内すると、apply.sh は `grep -v` で標準入力を待ったまま止まる。または、承認していない行まで流すようなコマンドを組み立ててしまう。`! awk -F'\t' '$1=="delete"||$1=="prune"' <承認済みファイル> | <skill-dir>/scripts/apply.sh` の形(絶対パス、リポジトリ内で実行)を明記する必要がある。

PR #1 の差分を確認しました。中心の変更はどれも妥当で、マージを止めるほどの欠陥は見つかっていません。指摘は、文書の主張が実際より強い点と、テストが確かめているつもりの内容を確かめていない点です。

**前提として確認したこと**
- macOS の `mktemp` が TMPDIR を見ない件は、手元で再現しました。`TMPDIR=<別dir> mktemp -d` も `mktemp -d -t foo` も `/var/folders/.../T/` に作られます。テンプレートで場所を明示する方針は正しいです。
- `apply.sh:21` の `input=$(grep -v '^action	')` は、入力が空で grep が 1 を返しても問題ありません。`set -e` が無く、`rows` も空行しか返さないためです。動作は変更前と同じです。

**指摘**

- **`skills/housekeeping/SKILL.md:98`、`skill-dev/housekeeping/test.sh:185` 「apply.sh は一時ファイルを使わない」は正しくない**
  - apply.sh は `lib.sh:48`(`hk_is_protected`)と `lib.sh:66-69`(`hk_path_in_use`)のヒアドキュメントを使っています。この環境の bash は `/bin/bash` 3.2.57 です。bash は 5.1 より前だと、ヒアドキュメントを一時ファイルで実装します。
  - bash は TMPDIR が書き込めないと `/var/tmp` や `/tmp` へ切り替えます。そのため `TMPDIR="$root/no-such-dir"` のテストは通ります。ただしこのテストが示すのは「切り替え先に書ければ動く」ことだけで、「一時ファイルを使わない」ことは示していません。
  - 修正案: 文言を「apply.sh は mktemp を使わない」に弱めます。またはヒアドキュメントをやめて `printf ... | ...` やプロセス置換に置き換えます。scan.sh にもヒアドキュメントが多くあります(`scan.sh:98,110,156,197,203,218,222`)。サンドボックスで書ける場所があることは、どちらにしても前提として残ります。

- **`skill-dev/housekeeping/test.sh:172-175` 「HOUSEKEEPING_TMPDIR の下に作る」ことを確かめていない**
  - このテストは、実行後に `$root/hk-tmp` が空かどうかだけを見ています。scan.sh が `HOUSEKEEPING_TMPDIR` を無視して `/var/folders` に作っていても、`hk-tmp` は空のままなので成功します。後でこの部分が壊れても検出できません。
  - 修正案: 作られたことも確かめます。たとえば `HOUSEKEEPING_PR_JSON` を読ませるとき、`cp` の前の時点で `$tmp` がどこにあるかを観測する仕組みが要ります。手軽なのは `hk_mktemp_dir` だけを単体で呼び、返ったパスが `"$root/hk-tmp/housekeeping."` で始まるかを見るテストを足す方法です。そのうえで現行の「空になっている」検証を残します。

- **`skills/housekeeping/scripts/scan.sh:31` 既定値を求める式が lib.sh と重複している**
  - `${HOUSEKEEPING_TMPDIR:-${TMPDIR:-/tmp}}` が `lib.sh:18` と同じ形で書かれています。片方だけ変えると、エラーメッセージが実際の場所とずれます。
  - 修正案: `hk_tmp_base()` を切り出して両方から呼ぶか、`hk_mktemp_dir` が失敗時にエラーメッセージを出すようにします。

- **`skills/housekeeping/SKILL.md:35` apply.sh を `!` で実行する案内に、具体的な形が無い**
  - scan.sh は `! <skill-dir>/scripts/scan.sh > <ファイル>` と形を示しています。一方 apply.sh は「同じように」だけです。apply.sh は標準入力で承認済みの行を受け取るので、同じ形にはなりません。
  - 修正案: `! awk -F'\t' '$1=="delete" || $1=="prune"' <絶対パスのscan.tsv> | <skill-dir>/scripts/apply.sh > <ファイル>` のように書きます。承認した行だけを入れたファイルを作る手順も添えると、エージェントの誤りが減ります。scan.sh と同じく、展開済みの絶対パスにすることも明記が要ります。

- **`skills/housekeeping/SKILL.md:35` 軽微: `!` で実行するときのカレントディレクトリへの言及が無い**
  - scan.sh も apply.sh も、カレントディレクトリのリポジトリを対象にします(`scan.sh:19`)。ユーザーのシェルが別のディレクトリにいると、別のリポジトリを走査してしまいます。
  - 修正案: `cd <repo> && ...` の形で案内します。

**検討してほしい点**

サンドボックスの外で実行してもらうなら、`HOUSEKEEPING_TMPDIR` をエージェント側から渡すだけで済む場面もあるはずです。たとえば Claude Code のサンドボックスでは TMPDIR が書き込める場所に設定されています。`hk_mktemp_dir` が TMPDIR に従うようになったので、実際にはそれだけで解決している可能性があります。`!` で外に出てもらう案内がまだ必要になる状況を一度実機で確かめると、SKILL.md の案内を短くできるかもしれません。

`skill-dev/housekeeping/test.sh` は実行していません。全件成功という結果は、PR 本文に書かれているものです。

7件見つかりました。正しさに関わる検証漏れが2件、テストの弱さが1件、ドキュメントの不整合が2件、整理が2件です。重いバグは見つかっていません。`skill-dev/housekeeping/test.sh` はローカル(macOS、bash 3.2.57)で全件通ります。

macOS の `mktemp` がテンプレートなしだと `TMPDIR` を見ないというコメントは正しいことを確かめました。`TMPDIR=/tmp/` を export しても `/var/folders/...` に作ります。また、`sandbox-exec` で `/tmp` と `/var/folders` への書き込みを禁じても、bash 3.2 のヒアドキュメントは失敗しませんでした。`hk_is_protected` と `hk_path_in_use` は正しく動くので、apply.sh の保護判定が黙って外れる心配はありません。リポジトリに CLAUDE.md は無く、ユーザー側の CLAUDE.md にはコードの規約が無いため、規約違反の指摘はありません。

7 findings, most severe first:

1. `skill-dev/housekeeping/test.sh:186`: apply.sh の『書き込めない TMPDIR でも動く』テストは、macOS では修正前のコードでも通るので、この PR が直した不具合を検出できない。

   Failure scenario: macOS で修正前の apply.sh(テンプレートなしの `mktemp`)に戻しても、`mktemp` は TMPDIR=$root/no-such-dir を無視して /var/folders に作って成功するので、テストは ok のまま。直したい環境(macOS のサンドボックスで /var/folders に書けない)での退行を捕まえられない。Linux でしか意味のないテストになっている。

2. `skills/housekeeping/scripts/scan.sh:30`: 一時ディレクトリを作る前に `git fetch --prune` を実行しているので、SKILL.md の『作れなければ何もせずに止まる』は事実と違う。安く確かめられる一時ディレクトリの作成が、副作用のある処理の後に来ている。

   Failure scenario: HOUSEKEEPING_TMPDIR が書き込めない場所を指していると、scan.sh はリモート追跡ブランチの prune(と、場合によっては gh を呼ぶ hk_default_branch)を済ませてから error で止まる。利用者は『何もしていない』と思うが、refs/remotes はもう書き換わっている。hk_mktemp_dir を fetch より前に置けば、記述どおりになる。

3. `skills/housekeeping/SKILL.md:35`: 『一時ディレクトリを作れない』ときの案内が、scan.sh の error 文と食い違っている。SKILL.md はサンドボックスの外で走らせてもらう手順しか書いておらず、error 文が勧める HOUSEKEEPING_TMPDIR の指定に触れていない。

   Failure scenario: エージェント側の $TMPDIR 以外に書き込める場所があっても(作業ディレクトリの下など)、エージェントは SKILL.md に従ってユーザーに `!` での手動実行を頼む。HOUSEKEEPING_TMPDIR=<書ける場所> を付けて再実行すれば済む場面で、ユーザーの手を煩わせる。error 文と手順書が違うことを言っているので、どちらに従うかも曖昧になる。

4. `skill-dev/housekeeping/test.sh:174`: 『HOUSEKEEPING_TMPDIR の下に作り、終了時に消す』のテストは、空になったことしか見ていないので、実際にその下に作られたかを確かめていない。

   Failure scenario: scan.sh が HOUSEKEEPING_TMPDIR を無視して $TMPDIR に作るよう退行しても、$root/hk-tmp は最初から空なので pass する。今は直前の no-such-dir のテストが代わりに捕まえているが、このテスト単体では見出しの主張を検証していない。trap の中でディレクトリの存在を記録する、mktemp をフックするなどして、作成先を確かめる必要がある。

5. `skills/housekeeping/scripts/scan.sh:31`: error 文が一時ディレクトリの場所を `${HOUSEKEEPING_TMPDIR:-${TMPDIR:-/tmp}}` で計算し直していて、lib.sh の hk_mktemp_dir と同じ既定値のロジックが2か所にある。

   Failure scenario: 将来 hk_mktemp_dir の既定値(たとえば /tmp の代わりの値)や優先順位を変えると、error 文は古いパスを表示し、利用者は試された場所とは別の場所を直そうとする。base を返す hk_tmp_base を lib.sh に置くか、hk_mktemp_dir が自分で error を出すようにすれば、重複は1か所にまとまる。

6. `skills/housekeeping/SKILL.md:35`: apply.sh を `!` で実行してもらう案内に、承認済みの行を標準入力に渡すことが書かれていない。apply.sh は stdin を `$(grep ...)` で最後まで読むので、パイプしないと止まる。

   Failure scenario: エージェントが文面どおり `! <skill-dir>/scripts/apply.sh` だけを案内すると、ユーザーの端末で grep が TTY からの入力を待ち続け、何も起きないように見える。手順4と同じ `awk -F'\t' '$1=="delete" || $1=="prune"' <scan.tsv の絶対パス> | <skill-dir>/scripts/apply.sh` の形をここでも明示する必要がある。

7. `skills/housekeeping/scripts/lib.sh:20`: `mktemp -d` が成功した直後の `[ -n "$d" ] && [ -d "$d" ] || return 1` は冗長な確認になっている。

   Failure scenario: `mktemp -d` は、ディレクトリを作れたときにだけ 0 を返してパスを出力するので、この2つの確認が偽になる経路はない。読み手に『mktemp が成功しても空のことがあるのか』と誤解させる。`mktemp -d "${base%/}/housekeeping.XXXXXX"` の終了コードをそのまま返せば足りる。

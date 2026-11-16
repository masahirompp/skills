PR「housekeeping: mktemp の失敗で止まり、一時ディレクトリを TMPDIR に従わせる」の差分(`main...HEAD`)をレビューし、指摘は5件でした。テストスイート `skill-dev/housekeeping/test.sh` はこの環境(GNU bash 3.2.57、macOS)で全件成功しています。

- **一番重い指摘(1件目)**: 「lsof が自分自身(`$$`)を見られれば、ほかのプロセスも見えている」という前提で使用中判定をしている点です。サンドボックスが同じサンドボックス内のプロセスしか見せない場合、使用中の worktree が「未使用」と判定されて消されます。
- **2件目**: SKILL.md の `${TMPDIR:-/tmp}` が、TMPDIR の無い Linux では誰でも書ける `/tmp` 直下の決まった名前になる点です。リポジトリ内の `review_loop.py` の `make_workdir` は、この共有 `/tmp` の危険をすでに扱っています。
- **macOS の mktemp の挙動**: テンプレートを付けないと TMPDIR を見ないことを実機で確かめました(`-t` を付けても同じ)。`hk_mktemp_dir` のコメントのとおりです。
- **repo の CLAUDE.md**: 存在しません。ユーザー全体の CLAUDE.md はコードの規約を含まないので、規約違反の指摘はありません。

5 findings, most severe first:

1. `skills/housekeeping/scripts/lib.sh:96`: hk_process_cwds は lsof の一覧に自分自身($$)が出るかどうかだけで『プロセスを見られる』と判断している。自分や同じサンドボックス内のプロセスは見えるが、外のプロセスは見えない、という制限のされ方を見分けられない。

   Failure scenario: Seatbelt などの same-sandbox 型の制限の中で apply.sh を実行し、ユーザーがサンドボックス外のターミナルで wt-merged を cd している場合。lsof には apply.sh の bash が出るので自己チェックは通るが、外のシェルは一覧に出ない。その結果 hk_path_in_use は空を返し、git worktree remove で使用中の worktree が消える。今回の変更が防ごうとしている失敗そのものが、この経路では防げない。自分の親より上のプロセスや別セッションのプロセスが見えるかで判定するか、サンドボックスの中では常に『確かめられない』に倒す必要がある。

2. `skills/housekeeping/SKILL.md:20`: 走査結果の保存先を `${TMPDIR:-/tmp}/housekeeping-scan.tsv` に変えたため、TMPDIR の無い Linux では誰でも書ける /tmp 直下の決まった名前のファイルになる(61行目の apply への受け渡しも同じパス)。

   Failure scenario: 共有マシンで別ユーザーが /tmp/housekeeping-scan.tsv を先に作り、自分に書ける権限(0666)にしておく。scan.sh > の出力はそのファイルに書かれ、相手は scan から apply までの間に『delete branch <name> <現在の sha>』の行を書き足せる(sha は同じファイルから読める)。手順4の awk は delete と prune の行をすべて apply.sh に渡すので、保護対象でない任意のブランチが消される。相手が書き込めない権限で先に作っておけば、走査がそもそも失敗する。review_loop.py の make_workdir が同じ脅威に 0700 の自分所有ディレクトリで対処しているのに、ここは揃っていない。mktemp で一意な名前にすれば避けられる。

3. `skills/housekeeping/scripts/scan.sh:165`: 本当に使用中の worktree と、lsof で確かめられなかった worktree が、どちらも『使用中か、確かめられない(...)』という同じ文言の理由になった。apply.sh の43行目も同じ。

   Failure scenario: wt-busy に sleep プロセスが実際にいるのに、理由は『使用中か、確かめられない(pid 123 sleep)』になる。ユーザーもエージェントも『確かめられないだけなら、サンドボックスの外で流し直せば消せる』と受け取りやすい。SKILL.md の手順5は『確かめられない』を外での再実行に誘導しているので、本当に使用中の worktree まで外で再実行の対象になる。hk_path_in_use の戻り値を分け、使用中と確認不能で別々の理由を出すべき。

4. `skills/housekeeping/scripts/lib.sh:9`: ヒアドキュメントの禁止と、それを grep で確かめるテスト(test.sh 204行目)は対症療法になっている。scan.sh では hk_mktemp_dir が TMPDIR に実際に作れたことを確かめてから進むので、同じ TMPDIR に一時ファイルを置く bash のヒアドキュメントも作れるはずで、scan.sh 側の禁止は冗長に見える。

   Failure scenario: テストは `<<` という文字列を探しているだけなので、`$((x << 2))` のような算術シフトや行末コメントに誤反応し、同じ問題を持つ別の書き方は見逃す。将来の修正のたびに、根拠の弱い書き方の制約を守り続ける保守コストがかかる。より一般的な直し方は、apply.sh の冒頭でも hk_mktemp_dir(または TMPDIR に書けるかの確認)で止めることにして、書き方の禁止と grep のテストをやめること。

5. `skills/housekeeping/scripts/scan.sh:119`: on_fp を得る grep が merged_into_default の判定より前に、PR なしのブランチすべてで走る。さらに first-parent のファイルは86行目で空でないことを確かめてから進むので、`on_fp -gt 1` の分岐は、実行中にファイルが消されない限りまず通らない。

   Failure scenario: 未取り込みのブランチ(最初の if で keep になる)でも、毎回 first-parent の全履歴を grep する。また『履歴を読めない』の分岐は事実上到達しないコードとして残る。merged_into_default の後で `elif ! grep -qxF ...` を直接使う元の形でも、安全性は86行目の確認で担保されている。

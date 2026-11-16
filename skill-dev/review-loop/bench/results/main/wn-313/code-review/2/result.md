9 findings, most severe first:

1. `lib/tmux/tmux.ts:54`: 案内のペインの起動し直しの回数(`@wn_respawned`)は、ペインが長く動いても0に戻りません。そのため上限の5回は短時間の連続ではなく、セッションの一生の累計になっています。上限を超えたときは、作業台の画面を逃がさずに `kill-pane` で案内のセッションを畳むので、直したはずの不具合が再び起きます。

   Failure scenario: 数日動かしている間に案内のプログラムが間をおいて6回落ちると、6回目で `kill-pane` が走り、案内のセッションが消えます。作業台の画面のクライアントは案内に attach しているので、`detach-on-destroy on` によってクライアントごと離れ、作業台の画面(Ghostty の分割)がエラーも出さずに閉じます。`sh-*` の分岐のような `switch-client` での退避もありません。直したはずの「開いた直後に閉じる」と同じ症状がまた出ます。

2. `src/cli/workbench.ts:33`: attach に成功したあとで tmux が 0 以外で終わった場合も、一覧がまだあれば「つなげなかった」として扱います。その経路では誤った文言を出し、OSC 2 でのタイトル消しも飛ばします。

   Failure scenario: 手で開いた端末で `whatnext workbench` を使っていて、tmux のクライアントが `[lost tty]` や `[terminated]` など 0 以外で終わったとします。一覧は生きているので `could not open the workbench screen` が出ます。さらに `\x1b]2;\x07` が送られないので、端末のタイトルが `whatnext workbench` のまま残ります。次の `ctrl+q ctrl+w` では、`focusWorkbench` がこの古い端末へフォーカスを移します。DESIGN.md が避けると書いている挙動です。

3. `docs/lib/tmux.md:43`: 今回の修正は「`exec` は `splitWorkbench` だけが付ける」という前提に立っています。しかし昇格済みモジュールの契約 docs では `splitWorkbench(run, command, env)` が「`command` を打ち込む」としか書かれておらず、先頭に ` exec ` を付けることも、末尾の改行も書かれていません。

   Failure scenario: /…/whatnext/CLAUDE.md には「仕様が収束したモジュールは…インターフェース契約を docs に置く」「実装セッションは契約 docs 経由で使い、中身のコードは読まない」とあります。この契約を読んで実装すると、`workbenchCommand` に `exec` を付けるのが自然で、0.20.2 の ` exec exec` の不具合がまた起きます。今回の差分は docs/lib/tmux.md の `pane-died` の項は直していますが、この項は直していません。

4. `src/cli/guide.ts:20`: `whatnext workbench` が案内のセッションを作り直すときは、`paneCommand(env, 'guide')` に workbench のプロセスの `env.node`、`env.cli`、PATH などを使います。そのため、動いている一覧とは別の版の案内のプログラムが動くことがあります。

   Failure scenario: 一覧を 0.20.2 で起動したまま npm で版を上げ、案内のセッションが消えたあとで `whatnext workbench` を実行したとします。新しい版の `cli.js` で案内が作られ、古い一覧が置く `@wn_guide` やスクリプトとの間で版がずれます。しかも `respawn-pane` は以後もこの新しい版のコマンドで起動し直します。launch の側にある `@wn_version` と `NEWER` による版の確認は、この経路では効きません。

5. `src/cli/workbench.ts:43`: `askListToRefreshGuide` は、頼みごとを `@wn_req_<秒>_<pid>` に書いて `@wn_pid` に SIGUSR2 を送る処理です。これは src/cli/guide.ts の Enter の処理(74-80行)とほぼ同じで、tmux.ts の `@wn_req_sh` も同じことをしています。

   Failure scenario: 頼みごとの名前の形式(`takeRequests` が `_` で区切って秒で並べる前提)や知らせの送り方を変えるときは、3か所を揃えて直す必要があり、1か所でも漏れると頼みごとが取りこぼされます。`Tmux` に `request(line)` のようなメソッドを1つ置き、両方の呼び出しをそこへ寄せれば済みます。

6. `src/ops/app.ts:1156`: 作り直した案内のセッションに名前がないことへの対処を、workbench から一覧への専用の頼みごと(`guide`)と `lastGuide` の取り消しで補っています。根本の原因は、名前(`@wn_name`)だけがセッションのオプションで、中身(`@wn_guide`)はサーバ全体のオプションだという非対称です。

   Failure scenario: 案内の名前もサーバ全体のオプションに置くか `GuideState` に含め、ステータス行がそれを読むようにすれば、作り直しても名前が残ります。そうすれば `GUIDE_REFRESH`、`askListToRefreshGuide`、知らせが届くまでの名前の空白(作り直した直後のステータス行が `workbench: ` だけになる)がまとめて要らなくなります。手で畳んだときや、ほかの経路で作り直したときにも、それぞれ特別な扱いを足さずに済みます。

7. `lib/tmux/tmux.ts:48`: 案内のプログラムがなぜ終わるかが分からないまま、`pane-died` で起動し直す処理で症状を抑えています。DESIGN.md も原因は「まだ分かっていない」と認めています。

   Failure scenario: 原因(SIGUSR 受信時の未処理の例外、`setInterval` の reload の中の reject など)が残る限り、案内は落ちるたびに1秒ほど「Pane is dead」を映し、`@wn_respawned` を消費します(1件目の上限に向かいます)。`@wn_guide_died` で手がかりを取るのはよいのですが、原因を追う issue(learning か bug)と、guide のプロセスに `uncaughtException` と `unhandledRejection` のログを足すことが修正に含まれていません。

8. `src/cli/list.ts:67`: `ensureGuide` は作ったときに `workbenchOptions(GUIDE, '')` を呼びます。そのすぐあとで startList がもう一度同じ `workbenchOptions(GUIDE, '')` を呼ぶので、作った場合は二重に送っています。

   Failure scenario: 一覧の起動のたびに、無駄な tmux の呼び出しが1回増えます。どちらで入れるのが正なのかも読み手には分かりません。`ensureGuide` が既存の場合も含めて常にオプションを入れる(起動時に版のオプションを入れ直す目的にも合う)ようにするか、一覧の側で `'exists'` のときだけ呼ぶようにすれば、1か所にまとまります。

9. `test/unit/cli.test.ts:26`: `it.each(['bash', 'zsh', 'sh'])` は、zsh が入っている環境を前提にしています。`npm test`(`vitest run lib test/unit`)の単体テストなのに、外部のシェルの有無に結果が左右されます。

   Failure scenario: zsh のない Linux のコンテナや CI で `npm test` を走らせると、`execFileSync('zsh', ...)` が ENOENT で失敗します。ローカルチェックの条件である「テストがあればテスト」を通せなくなり、main にマージできません。シェルがないときは skip するようにするべきです。

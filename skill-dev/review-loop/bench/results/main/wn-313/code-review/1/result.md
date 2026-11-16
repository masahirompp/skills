9 findings, most severe first:

1. `lib/tmux/tmux.ts:52`: `@wn_respawned` には「短い間に続けて落ちた」という条件がなく、リセットもされないので、上限の5回は「起動してすぐ終わるとき」ではなく、ペインが生きている間の通算の回数として効く。

   Failure scenario: 案内のプログラムが数日おきに1回落ちる場合、6回目で kill-pane になり、案内のセッションが消える。このとき案内に attach している作業台の画面は `detach-on-destroy on` で離れて終了コード 0 で終わり、Ghostty の分割は何も示さずに閉じる。今回直そうとしている「開いた直後に閉じる」が再発する。前回落ちた時刻を残し、数秒以内に続けて落ちたときだけ数える形にすべき。

2. `lib/tmux/tmux.ts:43`: 作り直し(ensureGuide)は `whatnext workbench` の起動時だけで、作業台の最後のシェルが終わるときの `switch-client -t =wbguide` と App.killSafely の `switchClient(c.tty, GUIDE)` は、案内のセッションがあることを前提にしたまま。

   Failure scenario: 案内のセッションが消えた状態(5回を使い切った、または手で畳んだ)で、作業台の画面が sh-<id> を映している。最後のシェルで exit すると switch-client が失敗し、続く kill-session でクライアントごと離れ、分割が閉じる。切り替えの前に案内を確かめて作り直す処理を、共通の仕組みの側に置くべき。

3. `src/ops/app.ts:1156`: 頼みごと `guide` は lastGuide を消して follow() を呼ぶだけで、doFollow は `!this.wbTty` のときと、mainSession が claude の画面でも list でもないとき(trust-xxx など)に何も書かずに戻る。そのため、作り直した案内に @wn_name が入らないことがある。

   Failure scenario: myTty() が undefined で WB_TTY が入らなかったとき、または whatnext の画面が信頼の確認のセッションを映しているときに、`whatnext workbench` が案内を作り直す。@wn_name は ensureGuide が入れた '' のままになり、ステータス行は名前のない `workbench: ` になる。lastGuide を消していても、カーソルを動かすまで直らない。

4. `src/cli/workbench.ts:22`: ensureGuide が失敗したときの早期 return は、WB_TTY をこの端末に書き換え、MAIN_TTY を外したあとにある。つなげないまま、作業台の画面の tty の記録だけが書き換わる。

   Failure scenario: 案内のセッションを作れずに 1 で終わると、一覧が覚えている作業台の画面の tty は存在しないクライアントを指したままになる。前に開いていた作業台の画面へは追従(switchClient)しなくなる。書き換えは ensureGuide が成功したあとに移すべき。

5. `src/cli/guide.ts:19`: `whatnext workbench` の側で案内のセッションを作り直すと、案内のペインのコマンドは一覧の版ではなく workbench を起動した版の node と cli.js(env.node / env.cli)になる。

   Failure scenario: 利用者がグローバルに入れた版と npx の版を混ぜて、`whatnext workbench` を手で実行する。作り直した案内のプログラムは別の版になり、一覧が書く @wn_guide の JSON の形や、キーの頼みごと(GUIDE_CREATE)の約束が食い違ったまま動く。一覧の版のコマンドをサーバのオプションに残して使うなどで、版を揃えるべき。

6. `test/unit/cli.test.ts:27`: `it.each(['bash', 'zsh', 'sh'])` は zsh が入っていることを前提にしていて、`npm test`(vitest run lib test/unit)の単体テストに含まれる。

   Failure scenario: zsh のない Linux の環境や CI で `npm test` を実行すると、execFileSync('zsh') が ENOENT で失敗する。CLAUDE.md がマージの条件にしているローカルチェックが通らない。シェルがないときは skip すべき。

7. `src/cli/workbench.ts:43`: askListToRefreshGuide は、`@wn_req_<秒>_<pid>` に書いて @wn_pid に SIGUSR2 を送る処理を、guide.ts の 74〜80 行目(Enter の頼みごと)から写していて、同じ処理が3か所目になる(`@wn_req_sh` の sh 版もある)。

   Failure scenario: 頼みごとのキーの形や知らせ方を変えるとき、guide.ts と workbench.ts の両方を直す必要があり、片方が古い形のまま残りうる。`Tmux.request(text)` のような共通のメソッドにまとめるべき。

8. `src/cli/list.ts:67`: ensureGuide は案内を作ったときに workbenchOptions(GUIDE, '') を呼ぶが、list.ts はその直後に同じ呼び出しを無条件で繰り返す。

   Failure scenario: 起動するたびに、作ったときは同じ設定を2回 tmux に送る。オプションを入れる責任が ensureGuide と呼び出し側に分かれているので、どちらかを変えるとずれる。ensureGuide が常にオプションを入れ直す形か、呼び出し側が 'exists' のときだけ入れる形のどちらかにすべき。

9. `src/cli/workbench.ts:57`: 観測できる挙動の変更が DESIGN.md にだけ書かれ、PRODUCT.md は直されていない(Ghostty の分割で失敗したときに「Press any key to close.」でキーを待つこと、新しいエラーの文言、案内のプログラムが自動で起動し直すこと)。

   Failure scenario: CLAUDE.md の「`docs/PRODUCT.md` は要件(何を実現するか。観測できる振る舞い…)」と、層2の「観測可能な挙動・仕様の変更: 人間へのエスカレーション必須」に反する。PRODUCT.md の 490 行目とシナリオ 59 は「示して終了する（終了コード 1）」のままで、分割ではキーを待つという今の挙動と食い違う。

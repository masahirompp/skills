10 findings, most severe first:

1. `lib/tmux/tmux.ts:50`: `pane-died` の `wbguide)` の分岐はセッション名だけで判定するので、案内のプログラム以外のペイン(案内のセッションで利用者が `ctrl+q %` / `ctrl+q c` で作ったシェル)も起動し直してしまう。

   Failure scenario: 作業台の画面が案内を映しているときに `ctrl+q c`(または `%`)でシェルを開き、`exit` する。0.20.2 までは `kill-pane` で閉じたが、今は 1 秒後に `respawn-pane` でシェルが出直し、6 回 `exit` するまで閉じない。PRODUCT.md が避けるとしている「新しいシェルが出直して閉じられなくなる」に当たる。そのたびに `@wn_guide_died` もシェルの画面で上書きされ、案内の落ちた手がかりが消える。5 回を超えて案内のペインだけ `kill-pane` されると、利用者のペインだけの `wbguide` が残り、`ensureGuide` は 'exists' を返して案内のないセッションにつなぐ。

2. `src/cli/workbench.ts:33`: 案内のセッションが畳まれてクライアントが離れたとき、tmux は 0 で終わるので成功扱いになり、理由も出さずキーも待たずに分割が閉じる。

   Failure scenario: 案内のプログラムが起動直後に毎回落ちる環境(node のパスが消えた、起動時の例外など)。attach は成功し、5 回の起動し直しのあと `kill-pane` で `wbguide` が消える。`detach-on-destroy on` でクライアントは `[exited]`(status 0)で終わり、`\x1b[1A\x1b[2K` で行を消して 0 を返す。`exec` なので分割は約 5〜6 秒後に無言で閉じる。`ctrl+q ctrl+w` を押し直しても `ensureGuide` が回数 0 の新しいペインを作り、同じことを繰り返す。このコミットが直そうとした「開いた直後に閉じる」が、遅れて同じ形で残る。

3. `lib/tmux/tmux.ts:55`: 起動し直しの回数 `@wn_respawned` はペインの寿命を通して増えるだけで、安定して動いたあとも戻らない。

   Failure scenario: whatnext を数日動かし続け、原因不明の案内の終了が間をあけて 6 回起きる(DESIGN.md も原因は未解明と書いている)。6 回目は「起動してすぐ終わる」ではないのに `kill-pane` され、`wbguide` が消える。案内を映していた作業台の画面は離れ、Ghostty の分割は閉じる。回数は、一定時間生きていたら 0 に戻すか、直近の終了時刻との間隔で数えるべき。

4. `src/ops/app.ts:1496`: 案内のセッションを作り直すのは `whatnext workbench` の attach の前だけで、一覧や `pane-died` が案内へ切り替える経路(`doFollow`、`killSafely`、`@wn_paned_sh` の `switch-client -t =wbguide`)は、案内がないと黙って失敗する。

   Failure scenario: 作業台の画面が `sh-a` を映している間に `wbguide` が消える(起動し直しの回数を使い切る)。そのあと (1) 一覧のカーソルを作業台のない行へ動かすと `switchClient(wb, GUIDE)` が失敗し、`lastGuide` だけ更新されて、画面は別のセッションの `sh-a` を映し続ける(打ったコマンドが違うセッションの作業台に入る)。(2) `sh-a` の最後のシェルを `exit` すると、`switch-client` が失敗したまま `kill-session` され、作業台の画面ごと離れて分割が閉じる。

5. `src/cli/workbench.ts:27`: 頼みごと `guide` の SIGUSR2 を attach より前に送るので、一覧は `wbChanged` による唯一の `follow()` をクライアントがつながる前に使ってしまうことがある。

   Failure scenario: 案内を作り直した起動で、カーソルの行にすでに作業台 `sh-<id>` がある。一覧は 1 回目の知らせで `wbTty` を覚えて `follow()` を予約する。`doFollow` の `t.clients()` が `tmux attach` の完了より先に走ると(負荷が高いときなど)、作業台の画面のクライアントが見つからず切り替えない。続く `client-attached` の知らせでは `wbChanged` が false なので `follow()` は呼ばれない。作業台の画面は、カーソルを動かすか次の定期更新(最大 60 秒)まで、作業台ではなく古い案内を映す。知らせは attach のあとに届くようにするか、`client-attached` で必ず `follow()` する。

6. `lib/tmux/tmux.ts:51`: 原因が分からないまま症状(セッションの消失)だけを起動し直しで覆っており、原因を突き止めるための `@wn_guide_died` は肝心の情報を落としやすい。

   Failure scenario: node が例外で落ちると、画面はエラーの本文、スタック、`Node.js vXX`、tmux の `Pane is dead (...)` の順になる。空行を除いた `tail -5` に残るのはスタックの末尾と `Pane is dead` で、エラーの本文は入らない(`capture-pane` に `-J` がないので、幅 80 で折り返した行も行数を食う)。値はサーバ全体のオプション 1 つなので、次の終了で上書きされる(項目 1 のシェルの `exit` でも)。利用者が不調で whatnext を終了すると `kill-server` で消える。`WHATNEXT_DEBUG_LOG` にも出ない。起動し直しで症状が見えなくなる分、原因の調査はかえって遠のく。

7. `src/cli/workbench.ts:58`: 利用者に見える挙動の追加(新しいエラー文言 2 つ、`Press any key to close.` のキー待ち、案内の自動の作り直し)が DESIGN.md にしかなく、PRODUCT.md にない。

   Failure scenario: プロジェクトの CLAUDE.md は「`docs/PRODUCT.md` は要件(何を実現するか。観測できる振る舞い、受け入れシナリオ、Out of Scope)」と定める。PRODUCT.md「作業台」は「`whatnext is not running. Start whatnext first.` と示して終了する（終了コード 1）」と書くが、Ghostty の分割から起動したときは 14 行目の `fail()` がキーを待つので、記述と実際が食い違う。次のサイクルは docs だけから書き直すので、この挙動は引き継がれない。同じ CLAUDE.md の「観測可能な挙動・仕様の変更: 人間へのエスカレーション必須」にも当たる変更である。

8. `src/cli/workbench.ts:43`: `askListToRefreshGuide` は、`src/cli/guide.ts` の Enter の処理(74〜80 行)と同じ「`@wn_req_<秒>_<pid>` を書いて `@wn_pid` に SIGUSR2」を写している。

   Failure scenario: 頼みごとの名前の形(`takeRequests` の並べ替えが頼る)と知らせ方が、`@wn_req_sh`、guide.ts、workbench.ts の 3 か所に重複する。形を変えるときに 1 か所を直し忘れると、その頼みごとだけ順序が狂うか届かない。`sendRequest(tmux, text)` のような共通の関数 1 つにまとめられる。

9. `src/cli/list.ts:67`: `ensureGuide` が作ったときに `workbenchOptions(GUIDE, '')` を入れるのに、直後に同じ呼び出しをもう一度しており、`'failed'` の戻り値も捨てている。

   Failure scenario: 通常の起動(案内を新しく作る経路)のたびに、9 個の `set` を並べた tmux の起動が 1 回余分に走る。`new-session` が失敗しても記録に残らず、続く `workbenchOptions` も黙って失敗するので、案内なしで一覧が立ち上がった理由を `WHATNEXT_DEBUG_LOG` から追えない。`ensureGuide` の戻り値で分け、'exists' のときだけ入れ直し、'failed' は `log` に出す。

10. `test/e2e/workbench.test.ts:255`: 追加したテストが macOS の環境に依存している(`signal=kill` の小文字の名前、`zsh` があること)。

    Failure scenario: tmux の `#{pane_dead_signal}` は `sys_signame` がある macOS/BSD では `kill` だが、Linux では数字の `9` になり、`/signal=kill/` が落ちる。`test/unit/cli.test.ts` 26 行目の `it.each(['bash', 'zsh', 'sh'])` は、zsh のない環境では `execFileSync` が ENOENT で落ち、コミット前のローカルチェック `npm test` が通らなくなる。

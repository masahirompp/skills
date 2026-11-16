9 findings, most severe first:

1. `lib/tmux/tmux.ts:50`: `pane-died` の `wbguide)` の分岐が、案内のプログラムのペインに限らず、案内のセッションにあるすべてのペインを起動し直してしまう。

   Failure scenario: 案内のセッションでも prefix は `C-q` で、tmux の既定のキー(`%`、`"`、`c`)が効く。利用者が作業台の画面で案内を映しているときに `^Q%` や `^Qc` でシェルのペインを作り、そこで `exit` すると、0.20.2 までは `*)` の分岐で閉じていたペインが、1秒後にシェルとして起動し直される。これが5回続くので、作ったペインを閉じられない。分岐の中で、ペインが案内のプログラムかどうか(`#{pane_start_command}` に `WHATNEXT_ROLE=guide` を含むか、など)を確かめるべき。

2. `lib/tmux/tmux.ts:56`: `@wn_respawned` を元に戻す処理がないので、上限の5回は「立て続けに落ちた回数」ではなく、ペインの一生の合計になっている。

   Failure scenario: 数日動かしている間に、案内のプログラムが散発的に6回落ちたとする。6回目は `kill-pane` でセッションごと消える。`detach-on-destroy on` なので、案内を映していた作業台の画面は離れ、tmux は 0 で終わるので、理由も出さずに Ghostty の分割が閉じる。そのあと一覧の `doFollow` の `switchClient(wb, GUIDE)` と、`sh-*` の最後のシェルの `switch-client -t =wbguide` はどちらも失敗する。このため、作業台を畳んだときにも作業台の画面ごと離れる。コメントの意図(起動してすぐ終わるときに回り続けない)に合わせるなら、起動から一定時間生きたら数え直すか、時刻の窓で数えるべき。

3. `src/ops/app.ts:1475`: 頼みごと `guide` は `lastGuide` を消して `follow()` を呼ぶだけで、`doFollow` が早く戻る経路では、作り直した案内に名前(`@wn_name`)が入らない。

   Failure scenario: `myTty()` が取れずに `WB_TTY` が置かれないと、`doFollow` は `if (!wb) return` で戻る。whatnext の画面が `trust-*` のセッションを映しているときも `else return` で戻る。どちらの場合も、作り直した案内のステータス行は `workbench: ` のまま空になる。頼みごとの処理の中で、`setSessionName(GUIDE, ...)` を直接書き直すほうが確実。

4. `src/cli/workbench.ts:22`: `whatnext workbench` が案内のセッションを作り直すとき、`paneCommand(env, 'guide')` には、一覧ではなく `whatnext workbench` のプロセスの `node`、`cli`、`PATH`、`LANG` が入る。

   Failure scenario: 一覧は npx の版で動いていて、利用者が別に入れた global の `whatnext workbench` を打ったとする。このとき案内は別の版の cli で作られ、そのまま起動し直しの対象にもなる。一覧の側の `@wn_paned_sh` や `@wn_guide` の形と版がずれる。一覧の `@wn_version` と比べるか、一覧が置いたコマンドを使うべき。

5. `src/cli/workbench.ts:43`: `askListToRefreshGuide` は、`guide.ts` の Enter の処理と同じ手順(`@wn_req_<秒>_<pid>` を置き、`@wn_pid` を読み、SIGUSR2 を送る)をもう一度書いている。`Tmux.signalGuide` の形もほぼ同じ。

   Failure scenario: 頼みごとを送る処理が、ts に2か所(guide.ts の keypress と workbench.ts)、sh に1か所(`@wn_req_sh`)ある。名前の形や知らせ方を変えると、ずれて一部だけ届かなくなる。`Tmux` に `request(line)` のような共通の関数を置き、両方から呼ぶべき。

6. `src/cli/list.ts:67`: `ensureGuide` は作ったときに `workbenchOptions(GUIDE, '')` を呼ぶのに、`startList` がその直後にもう一度同じ呼び出しをしている。

   Failure scenario: 一覧の起動時に案内を作ると、同じオプションを tmux に2回送る。ensureGuide の「作ったときだけオプションを入れる」という約束と、呼ぶ側の「いつも入れる」が重なっていて、どちらが責任を持つのかが読み取れない。ensureGuide がいつも入れるようにして、list.ts の呼び出しを消すほうが単純。

7. `lib/tmux/tmux.ts:48`: 根本の原因(案内のプログラムがなぜ終わるか)を調べないまま、起動し直しで症状を抑えている。原因の手がかりも画面の末尾5行に限られる。

   Failure scenario: guide.ts の `reload` や `draw` が例外や `stdout` の 'error' で落ちても、案内のプログラムは `uncaughtException` と `unhandledRejection` を `WHATNEXT_DEBUG_LOG` に残さない。`frame` で描き直した画面の末尾5行には、スタックが入りきらないことがある。起動し直しが5回で尽きると、また同じ不具合として出る。案内のプログラムの側で例外を記録するほうが、原因に近い直し方になる。

8. `docs/DESIGN.md:229`: 観測できる挙動の変更(新しいエラーの文言、分割でキーを待つこと、案内の作り直し)を DESIGN.md にだけ書き、PRODUCT.md(490行、シナリオ 59)を直していない。

   Failure scenario: /Users/.../whatnext/CLAUDE.md には「`docs/PRODUCT.md` は要件(何を実現するか。観測できる振る舞い、受け入れシナリオ…)」とあり、「観測可能な挙動・仕様の変更: 人間へのエスカレーション必須」ともある。ところが `whatnext: could not open the workbench screen ...` と `Press any key to close.` は PRODUCT.md にない。PRODUCT.md の「whatnext が動いていないときは … 示して終了する（終了コード 1）」も、Ghostty の分割から起動したときにはキーを待つ挙動と食い違う。

9. `test/e2e/workbench.test.ts:255`: `/signal=kill/` は、macOS の `sys_signame`(小文字)に頼っている。test/unit/cli.test.ts の `it.each(['bash','zsh','sh'])` も、zsh が入っている前提になっている。

   Failure scenario: Linux で動かすと、tmux の `#{pane_dead_signal}` の名前の形が違い、zsh も既定では入っていない。そのため e2e と単体テストが、挙動に関係なく落ちる。

確認していない点は2つあります。

- 1件目では、prefix が根の `C-q` の割り当てより先に効くことを前提にしています。この前提は tmux のコードの記憶によるもので、実機で `^Q%` を押しては確かめていません。
- 「`detach-on-destroy` でセッションが消えたとき、tmux は 0 で終わる」(2件目)も記憶によるもので、実測していません。

ほかに1点、今回の差分の外ですが、`@wn_guide_pid` を書いている箇所がどこにもありません。そのため `signalGuide` は何もせず、案内は300msごとに読み直す処理だけで更新されています。

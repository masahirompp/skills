8 findings, most severe first:

1. `lib/tmux/tmux.ts:55`: 案内のペインの起動し直しの回数 `@wn_respawned` は、案内が正常に動いたあとも戻らない。このため「起動してすぐ終わるときの5回」ではなく「ペインが生きている間の通算5回」の上限になっている。

   Failure scenario: whatnext を数日動かしたままで、案内のプログラムが原因不明のまま(PR でも未特定)ときどき落ちるとする。6回目に落ちた時点で、時間が空いていても `kill-pane` で wbguide が消え、直そうとした症状(案内のセッションの消失)が戻る。起動から一定時間たっていれば数え直す、時刻と比べる、などの区別がない。

2. `lib/tmux/tmux.ts:43`: 案内のセッションがないときの作り直しは `whatnext workbench` の attach 前にしかない。`pane-died` の sh-* の分岐と一覧の doFollow は、wbguide があるものとしてそのまま `switch-client -t =wbguide` する。

   Failure scenario: 5回の上限に達するか手で畳んで wbguide が消え、作業台の画面は sh-X を映しているとする。その作業台の最後のシェルを exit すると、switch-client が失敗したまま kill-session が走り、detach-on-destroy で作業台の画面ごと離れて Ghostty の分割が閉じる。根本の『案内は常にある』を、使う側の1か所だけで補っている。

3. `src/cli/workbench.ts:34`: 失敗の経路で早く return するため、以前は必ず出していたタイトル消し(OSC 2)が飛ばされる。

   Failure scenario: 利用者が普通の端末で `whatnext workbench` を手で動かし、一度つながったあとに tmux が 0 以外で終わったとする(一覧は残っている)。端末のタイトルが 'whatnext workbench' のまま残り、一覧で `w` を押すと focusWorkbench がこの古い端末へ移ってしまう。分割は作られない。DESIGN.md の『終わるときに OSC 2 でタイトルを消す』に反する。

4. `src/cli/workbench.ts:27`: attach の前に askListToRefreshGuide で一覧に知らせるので、WB_TTY が変わったこと(wbChanged)がクライアントのつながる前に使われてしまう。あとの client-attached の知らせでは wbChanged が false になり、follow が走らない。

   Failure scenario: wbguide を作り直したとき、一覧のカーソルの行には作業台 sh-X があるとする。doFollow(60ms 後)の時点でまだ attach していないと、クライアントが見つからず switchClient をしない。そのあと attach しても follow が呼ばれないので、作業台の画面は sh-X ではなく案内を映したままになる。カーソルを動かすまで直らない。

5. `src/cli/guide.ts:19`: `whatnext workbench` から呼ぶ ensureGuide は、paneCommand(env, 'guide') が既定で読む process.env として、一覧ではなく Ghostty の分割のシェルの環境を使う。

   Failure scenario: 利用者が `WHATNEXT_DEBUG_LOG=... XDG_STATE_HOME=... whatnext` で起動したとする。作り直された案内はそれらを持たない(PATH や LANG も分割のシェルのもの)。一覧が作った案内とは違う環境で動くので、案内が落ちる原因を探すためのログが、肝心の作り直したあとに残らない。

6. `src/cli/workbench.ts:34`: `res.status !== 0` は、tmux がシグナルで終わったとき(status が null)も『つなげなかった』と判定する。

   Failure scenario: 作業台の画面の tmux クライアントが SIGTERM などで終わり、一覧は動いているとする。実際にはつながっていたのに 'could not open the workbench screen' を出し、Ghostty の分割では 'Press any key to close.' で止まる。res.signal を区別していない。

7. `src/cli/list.ts:67`: ensureGuide が 'created' のときに workbenchOptions(GUIDE, '') を入れたあと、startList がもう一度同じものを入れる。

   Failure scenario: 一覧を起動して案内のセッションを作るたびに、同じオプションを入れる tmux の呼び出しが2回走る。オプションを入れる責務が ensureGuide と呼び出し側に分かれ、どちらで入れるかの約束があいまいになる(既にある場合の入れ直しだけ呼び出し側に残せば足りる)。

8. `src/cli/workbench.ts:44`: askListToRefreshGuide は、guide.ts の Enter の処理にある頼みごとの送り方(`@wn_req_<秒>_<pid>` を set して `@wn_pid` に SIGUSR2)をそのまま写している。

   Failure scenario: 頼みごとの書式(キー名や並べ方)を変えると、`@wn_req_sh`、guide.ts、workbench.ts の3か所を揃えて直す必要があり、どれかが取り残されると頼みごとが読まれない。Tmux に `request(text)` のような共通の関数を置けば1か所で済む。

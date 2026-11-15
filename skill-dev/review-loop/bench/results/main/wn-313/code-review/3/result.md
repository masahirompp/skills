10件見つけました。いちばん重いのは2件です。1件目は、案内のプログラムが落ちた原因を残すつもりの `@wn_guide_died` に、肝心のエラー文がほぼ残らないこと。2件目は、起動し直しの上限が「すぐ落ちるとき」ではなく、ペインの生涯の回数になっていることです。指摘を確かめる検証は回していないので、どれも確定ではなく候補です。

10 findings, most severe first:

1. `lib/tmux/tmux.ts:51`: `@wn_guide_died` に残すのは画面の空でない最後の5行だけで、Node が落ちたときに出すエラー文(`TypeError: ...` などスタックの先頭)がほとんど残らない。

   Failure scenario: 案内のプログラムが例外で落ちると、Node は「エラー文 → at ... を最大10行 → 空行 → Node.js v24.x」を出し、tmux はその下に `Pane is dead (...)` を描く。`grep -v '^$' | tail -5` で残るのは at ... の2〜3行、`Node.js v24`、`Pane is dead` だけになる。DESIGN.md が書く目的「なぜ終わったかの手がかり」になる例外の種類とメッセージが消える。

2. `lib/tmux/tmux.ts:55`: 起動し直しの回数 `@wn_respawned` は戻されず、ペインの生涯で5回までになっている。docs が言う「起動してすぐ終わるときに回り続けないため」の制限(時間あたりの回数)になっておらず、まれに落ちるだけでもいずれ案内のセッションが畳まれる。

   Failure scenario: whatnext を何日も動かし、案内のプログラムが1日1回落ちるとする。6回目で `kill-pane` が走り、案内のセッションが消える。作業台の画面がそれを映していると、`detach-on-destroy on` でクライアントが離れる。tmux はたぶん 0 で終わるので `whatnext workbench` は失敗の扱いにならず、Ghostty の分割が何も出さずに閉じる。0.20.2 と同じ症状が遅れて出る。起動してからの時間で回数を戻すか、`@wn_guide_died` の時刻との差で判定するとよい。

3. `src/cli/workbench.ts:27`: 頼みごと `guide` の SIGUSR2 を attach の前に送るので、一覧は WB_TTY が変わったことをこの知らせで使い切る。そのあとの `client-attached` の知らせでは `wbChanged` が false になり、follow が走らない。

   Failure scenario: 案内のセッションを作り直した直後、doFollow(60ms まとめてから)が tmux attach の完了より先に走ると、`clients()` に作業台の画面がまだなく、switch-client が飛ばされる。続く client-attached の知らせでは wbTty が同じ値なので follow しない。カーソルの行に `sh-<id>` があっても、作業台の画面は案内のセッションに残る。知らせを attach の後に送るか、一覧が client-attached のたびに follow するとよい。

4. `src/cli/guide.ts:19`: `whatnext workbench` から作り直す案内のペインは、workbench のプロセスの node と cli と process.env(PATH、CLAUDE_CONFIG_DIR、XDG_STATE_HOME、WHATNEXT_DEBUG_LOG など)で起動するので、一覧が起動した案内と版や環境が違いうる。

   Failure scenario: npm で更新したあと(古い一覧が動いていて `@wn_newer` が立つ状態)に、新しい `whatnext workbench` が案内を作り直す。案内は新しい版の cli.js で動き、古い一覧が書く `@wn_guide` を新しい版の parseGuide で読む。また WHATNEXT_DEBUG_LOG は、分割のシェルの環境では渡らない。一覧の node と cli(`@wn_version` のような server のオプション)から組むほうが一貫する。

5. `src/cli/workbench.ts:33`: tmux attach がシグナルで終わったとき(`res.status === null`)も `!== 0` で失敗とみなし、hasSession(LIST) が真ならエラーを出して fail() でキーを待つ。

   Failure scenario: tmux のクライアントだけが SIGTERM などで終わったとき、または SIGHUP を受けて tty を失ったとき(node 側が生き残る場合)に、閉じた tty へ setRawMode(true) を呼び、EIO の例外か、来ないキー入力を待ち続ける。status が null の場合を分けて扱うとよい。

6. `src/cli/workbench.ts:43`: askListToRefreshGuide は、guide.ts の Enter の処理(`@wn_req_<秒>_<pid>` を書き、`@wn_pid` を読んで SIGUSR2)と、`@wn_req_sh` の手順をもう一度写している。

   Failure scenario: 頼みごとの名前の形(takeRequests は `_` で分けた3つ目を秒として並べる)や知らせ方を変えると、3か所を揃えて直す必要があり、どれか1つがずれると頼みごとが届かないか順がずれる。`Tmux.request(line)` のような1つの関数にまとめ、guide.ts と workbench.ts から呼ぶとよい。

7. `src/cli/list.ts:67`: ensureGuide が案内のセッションを作ったときはもう workbenchOptions(GUIDE, '') を入れているのに、startList はそのあと同じ呼び出しをもう一度している。

   Failure scenario: 一覧の起動のたびに、設定8つ分の tmux の呼び出しが余分に1回走る。どちらで入れるのが正なのかも読み取りにくい。ensureGuide を「あれば入れ直す、なければ作って入れる」にまとめるか、list.ts の重複を消すとよい。

8. `src/ops/app.ts:1156`: 根の原因は、案内の名前をセッションのオプション `@wn_name` に置いていて、セッションを作り直すと消えることにある。それを新しい頼みごと `guide` と lastGuide の消去でつくろっている。

   Failure scenario: 案内のセッションを作り直す経路が増えるたびに、知らせ忘れると、ステータス行の `workbench: ` の名前が空になる。案内の名前をサーバ全体のオプション(`@wn_guide` と同じ扱い)に置くか、`@wn_guide` の JSON から出すかすれば、作り直しても名前が残る。`sh-<id>` のセッションのオプションはサーバ全体の値より優先されるので、そちらには影響しない。そうすれば `GUIDE_REFRESH` の約束ごと要らなくなる。

9. `docs/DESIGN.md:229`: 観測できる振る舞いの変更を DESIGN.md にだけ書き、PRODUCT.md を直していない。変更は、つなげなかったときに標準エラーへ理由を出すこと、Ghostty の分割では `Press any key to close.` でキーを待つこと、案内のプログラムが落ちても起動し直すこと。

   Failure scenario: リポジトリの CLAUDE.md の「`docs/PRODUCT.md` は要件(何を実現するか。観測できる振る舞い、受け入れシナリオ、Out of Scope)、`docs/DESIGN.md` は設計(どう実現するか…)を書く」に反する。同じ CLAUDE.md の「観測可能な挙動・仕様の変更: 人間へのエスカレーション必須」を経たかも、差分からは追えない。次のサイクルや監査で PRODUCT.md だけを読むと、この挙動が要件に見えない。

10. `test/e2e/workbench.test.ts:255`: `@wn_guide_died` を `/signal=kill/` で確かめているが、`pane_dead_signal` の文字列は tmux の sig2name の実装、つまり OS に依存する。

    Failure scenario: macOS の sys_signame では小文字の `kill` になるが、Linux の compat の実装では `KILL` や番号の `9` になりうる。macOS 以外で e2e を流すとこのアサーションが落ちる。`/signal=(kill|KILL|9)/i` のように幅を持たせるとよい。

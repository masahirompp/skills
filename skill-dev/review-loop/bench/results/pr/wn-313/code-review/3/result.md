レビュー対象の `2` は、現在のブランチ `wbguide-recover` の PR として解決しました(`main...HEAD`、コミット d212b82)。下に8件を、重いものから順に並べます。この回は検証の工程を通していないので、1、2、4件目には実際に起きるかの確認が要ります。

8 findings, most severe first:

1. `src/cli/workbench.ts:27`: 案内を作り直したときだけ、attach の前に頼みごと guide で一覧に知らせている。このため、作業台の画面のクライアントがつながる前に、一覧が wbChanged を使い切り、follow も済ませてしまう。

   Failure scenario: 一覧のカーソルが sh-<id> のある行にある状態で、wbguide が消えていて `whatnext workbench` を新しい tty で起動したとする。SIGUSR2 → onSignal → afterSignal の順で wbChanged が true になって消費され、follow が60ms後に doFollow を走らせる。この時点でクライアントがまだ attach していないと、clients() に見つからず switch-client が行われない。続く client-attached の知らせでは wbChanged が false なので follow が呼ばれず、作業台の画面は sh-<id> ではなく wbguide(古い @wn_guide の中身)を映したまま止まる。

2. `src/ops/app.ts:1497`: 案内のセッションを作り直す処理(ensureGuide)を、`whatnext workbench` の attach の前という入口にだけ置いた。作業台の画面がつながっている間に案内が消えると、doFollow と、pane-died の sh-* の分岐の switch-client -t =wbguide は、何も言わずに失敗する。

   Failure scenario: 案内のプログラムが5回終わって kill-pane で wbguide が消えたあと、利用者が作業台の画面で sh-a を開いたまま、一覧で作業台のない行に移る。doFollow の switchClient(wb, GUIDE) が失敗して、画面は sh-a のまま変わらない。または sh-a の最後のシェルを exit すると、pane-died の switch-client が失敗し、kill-session で作業台の画面ごと離れて Ghostty の分割が閉じる。DESIGN.md に書いた「回数を使い切ったときや手で畳んだときにも開ける」は、つなぎ直すまで成り立たない。doFollow で GUIDE に切り替える前、または pane-died の後始末の中で作り直すほうが根に近い。

3. `lib/tmux/tmux.ts:52`: 起動し直した回数 @wn_respawned は、ペインの寿命の間ずっと増えるだけで戻らない。このため「起動してすぐ終わるときに回り続けない」ための上限が、長く動いた末の合計5回の上限として働く。

   Failure scenario: 数日続けて使う間に、案内のプログラムが間隔をあけて5回落ちる(どれも長く正常に動いたあと)。6回目では起動し直さずに kill-pane し、wbguide が消える。つながっていた作業台の画面は detach-on-destroy で離れ、分割は何も知らせずに閉じる(終了コードは 0)。短い間に続けて終わったときだけ数える(前回の時刻を残し、一定時間あけば数え直す)形にすれば、意図どおりになる。

4. `src/cli/workbench.ts:33`: 以前は、attach のあとにタイトル(OSC 2)を必ず消していた。いまは失敗の分岐が先に return するので、tmux が 0 以外で終わり、一覧が残っているときはタイトルが消えない。加えて、attach が成功したあとに 0 以外で終わった場合も、「つなげなかった」と誤った理由を出す。

   Failure scenario: 利用者が手で `whatnext workbench` を起動して attach に成功し、set-titles で端末のタイトルが 'whatnext workbench' になる。その後 tmux のクライアントが 0 以外で終わる(シグナルや、端末の不調による lost tty)と、'could not open the workbench screen' と出て return 1 し、タイトルは残る。あとで別の作業台の画面を開いたとき、focusWorkbench が名前で探して、この古い分割へフォーカスを移しうる。DESIGN.md の「終わるときに OSC 2 でタイトルを消し、古いタイトルの分割へ移らないようにする」が崩れる。

5. `src/cli/guide.ts:19`: `whatnext workbench` が作り直す案内のペインは、workbench のプロセス自身の node・cli・process.env から paneCommand で組み立てている。一覧の側が持つ版と環境ではない。

   Failure scenario: 一覧は古い版で動いていて、利用者が手で、別の場所に入った新しい版(npx やグローバルの更新)の `whatnext workbench` を起動する。wbguide は新しい版の guide.js で作られ、そのあとも起動し直しで同じ版が動き続ける。@wn_guide の JSON の形が版の間で違えば、parseGuide が {kind:'empty'} に落ちて、案内が 'No session is selected' になる。一覧の起動時に一覧が使う paneCommand をサーバのオプションに置き、それを使うほうが安全。

6. `src/cli/workbench.ts:43`: askListToRefreshGuide は、guide.ts のキー処理にある頼みごとを送る手順(@wn_req_<秒>_<pid> を set し、@wn_pid を読んで SIGUSR2 を送る)を、そのまま写している。

   Failure scenario: 頼みごとの書式(名前の付け方や知らせ方)を変えるときに、guide.ts、workbench.ts、tmux.ts の @wn_req_sh の3か所を揃えて直す必要があり、直し漏れると頼みごとが届かない。lib/tmux の Tmux に request(text) を1つ置き、両方から呼べば済む。

7. `src/cli/list.ts:67`: ensureGuide は、作った場合はすでに workbenchOptions(GUIDE, '') を呼んでいる。そのすぐあとで、list.ts がもう一度 workbenchOptions(GUIDE, '') を呼ぶ。

   Failure scenario: 一覧の起動時に案内を新しく作るたびに、同じ設定をまとめた tmux の呼び出しが2回走る。どちらがオプションを入れる責任を持つのかも、コードから読み取れない。ensureGuide を常にオプションを入れる形にして list.ts の呼び出しを消すか、ensureGuide から外して list.ts と workbench.ts の両方で呼ぶかの、どちらかに寄せる。

8. `test/e2e/workbench.test.ts:255`: `signal=kill` を確かめているが、これは tmux の pane_dead_signal が sys_signame を使い、小文字の名前を返す前提(macOS)に頼っている。

   Failure scenario: glibc には sys_signame がないので、Linux の tmux では sig2name が '9' を返し、`signal=9` になる。このため、macOS 以外の環境で e2e を流すとこのテストが落ちる。/signal=(kill|9)/ のように、両方を許す形にすれば避けられる。

この PR の見出しにある exec の重複(` exec exec <node> ...`)の直しは正しく、退行は見つかりませんでした。`splitWorkbench` を呼んでいるのは `src/ops/app.ts` だけです。

1件目の競合は、新しい tty で作業台の画面を開いたときだけに起きます。WB_TTY が前と同じ tty なら、以前の流れでも attach で follow が呼ばれないので、この変更で生じた問題ではありません。

CLAUDE.md の約束に明らかに反する箇所はありませんでした。`lib/` を変えた分は `docs/lib/tmux.md` に書かれ、テストも `lib/tmux/tmux.test.ts` に置かれています。

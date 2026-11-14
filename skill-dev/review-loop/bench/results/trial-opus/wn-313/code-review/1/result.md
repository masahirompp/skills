レビューは高い労力で行い、検証の段は通していません。対象は `main...HEAD` の差分(コミット d212b82)です。正しさの指摘を先に、整理と規約の指摘を後に並べました。

10 findings, most severe first:

1. `lib/tmux/tmux.ts:60`: 起動し直しを5回使い切ると、案内のペインを kill-pane して wbguide のセッションが消える。detach-on-destroy on なので作業台の画面のクライアントは 0 で離れ、今回直したかった『開いた直後に閉じる/黙って閉じる』症状がこの経路に残る。

   Failure scenario: 案内のプログラムが6回落ちる → 6回目の pane-died で kill-pane → wbguide が消える → wbguide を映していた tmux attach は status 0 で終わる → workbench.ts は成功とみなして行を消し 0 を返す → Ghostty の分割が案内も『Press any key』も出さずに閉じ、@wn_guide_died を見に行くきっかけもない。

2. `lib/tmux/tmux.ts:44`: sh-* の最後のシェルが終わる処理は、wbguide が存在する前提で switch-client してから kill-session する。案内が消えている(使い切った、手で畳んだ)と切り替えが黙って失敗し、そのまま kill-session で作業台の画面ごと離れる。ensureGuide は `whatnext workbench` の起動時にしか走らないので、根本の経路が塞がっていない。

   Failure scenario: 作業台の画面が sh-abc を映している間に wbguide が消える → sh-abc の最後のシェルで exit → switch-client -t =wbguide は can't find session で失敗 → kill-session sh-abc → detach-on-destroy でクライアントが 0 で終わる → 分割が閉じる。0.20.2 の不具合と同じ見え方になる。

3. `lib/tmux/tmux.ts:55`: @wn_respawned はペインの一生分の累計で、時間で減らない。docs の言う『起動してすぐ終わるときに回り続けないため』の歯止めではなく、累計5回の上限になっている。

   Failure scenario: 数日動かす間に、案内が離れた時刻にたまたま5回落ちる(各回はすぐ起動し直せている) → 6回目は1回目から何日も経っていても kill-pane される → 案内のセッションが消え、上の2件の症状が出る。

4. `src/cli/guide.ts:19`: `whatnext workbench` から ensureGuide が作る案内は、一覧の node と cli.js ではなく、workbench を実行したプロセスの env.node/env.cli/process.env で動く。以後の respawn-pane も同じコマンドを使い続ける。

   Failure scenario: 一覧はグローバルに入れた v0.21 で動き、利用者は別の場所(古いグローバル版、または npx の一時キャッシュ)の `whatnext workbench` を手で実行する → 案内は別の版の cli.js で作られ、@wn_guide の JSON の形の違いを読み違える。キャッシュが消えると respawn-pane が5回続けて失敗し、案内が消える。

5. `src/cli/workbench.ts:33`: attach の判定が『0 以外で終わり、一覧が残っている』を一律につなげなかったとみなす。正常につないだあとに 0 以外で終わった場合(status が null になるシグナル終了、[lost tty] など)にも『could not open the workbench screen』と誤って出し、分割ではキーを待たせる。

   Failure scenario: 作業台の画面を数時間使ったあと、tmux のクライアントがシグナルで終わる(res.status === null) → null !== 0 が真で、一覧もある → 誤ったエラーを出し、Ghostty の分割は『Press any key to close.』のまま残る。

6. `src/cli/workbench.ts:43`: askListToRefreshGuide は、頼みごとを書いて一覧に SIGUSR2 を送る処理を、guide.ts のキー入力の処理(74-80行)と sh の @wn_req_sh に続く3つ目の写しとして書いている。

   Failure scenario: 頼みごとの名前の形(@wn_req_<秒>_<pid>)や通知の方法を変えると3か所を揃える必要があり、takeRequests の並べ替えとずれやすい。Tmux に request(line) のようなメソッドを1つ置き、guide.ts と workbench.ts の両方から呼ぶべき。

7. `src/ops/app.ts:1156`: 頼みごと `guide`(GUIDE_REFRESH)という知らせの仕組みは、案内の名前をセッションのオプション @wn_name にだけ置いていることへの対症の手当て。名前をサーバ全体のオプション(@wn_guide と同じ置き方)にすれば、作り直したセッションも自動で読める。

   Failure scenario: GUIDE_REFRESH は doFollow の中で、映す先が GUIDE で wbTty が分かっているときにしか名前を書かない。myTty() が取れない、一覧が忙しいなどの条件で名前が空のまま残りうる。知らせの種類、lastGuide のリセット、e2e の待ちという余分な部品も増える。

8. `src/cli/list.ts:67`: ensureGuide は作ったときに workbenchOptions(GUIDE, '') を呼び、その直後に list.ts も workbenchOptions(GUIDE, '') を呼ぶ。作ったときは同じ tmux の呼び出しが2回になり、どちらがオプションを入れる役かもあいまいになる。

   Failure scenario: 起動のたびに同じオプションを2回送る(効果は同じで無駄なだけ)。ensureGuide の『作ったときだけ入れる』という約束と、一覧の『常に入れ直す』という約束が重なっていて読み手が迷う。

9. `test/unit/cli.test.ts:26`: bash/zsh/sh を it.each で直接 execFileSync していて、zsh がない環境(Linux の CI、最小のコンテナ)では ENOENT で単体テストが落ちる。

   Failure scenario: zsh の入っていない Linux の CI で npm test → 'zsh でそのまま動く' が spawnSync zsh ENOENT で落ち、関係のない変更でもチェックが通らない。

10. `src/cli/workbench.ts:56`: CLAUDE.md の『`docs/PRODUCT.md` は要件(何を実現するか。観測できる振る舞い…)』に反して、新しく観測できる振る舞いを DESIGN.md にしか書いていない。対象は、つなげなかったときの標準エラーの文言、Ghostty の分割で『Press any key to close.』を出してキーを待つこと、案内が落ちたら起動し直すこと。PRODUCT.md 490行には同じ種類の『whatnext is not running…』が要件として載っている。

    Failure scenario: 規約は /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-inxy031r/w/9510775bc4/whatnext/CLAUDE.md の『要件と設計の2ファイル』。次の書き直しや cycle-audit は PRODUCT.md を正として突き合わせるので、この振る舞いが要件から漏れて消えるか、食い違いとして見つかる。

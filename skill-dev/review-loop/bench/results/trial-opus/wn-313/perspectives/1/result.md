ほぼ読み終えたので、指摘をまとめます。

## レビュー結果(`git diff main...HEAD`、コミット d212b82)

コミットの狙いは4つです。案内のペインが終わったら起動し直すこと、attach の前に `ensureGuide` で案内のセッションを作り直すこと、attach の失敗を標準エラーに出すこと、`exec` が二重に付くのを直すこと。どれも原因の説明に筋が通っており、`exec exec` の修正は bash・zsh・sh の実行テストで裏付けられています。`lib/tmux/tmux.test.ts` と `test/unit/cli.test.ts` は手元で通りました(11 件)。e2e は走らせていません。

### 正確性

- **`lib/tmux/tmux.ts:53`(`@wn_respawned` の回数)** 回数が数えるだけで戻らないので、「すぐ落ち続けるときに回り続けない」という目的より強く効きます。
  - 例:案内が数日に一度、別々の原因で落ちると、6 回目でペインが閉じ、案内のセッションも消えます。
  - そのとき作業台の画面が案内を映していれば、`detach-on-destroy on` で画面が離れます。tmux は 0 で終わる見込みなので(未確認)、`workbench.ts:33` は失敗と見なしません。結果、分割は何も出さずに閉じ、このコミットで直したはずの「開いた直後に閉じる」と同じ見え方に戻ります。
  - 直し方の案:起動から N 秒以内に終わったときだけ数える、または前回の起動からの時刻で回数を戻す。

- **`lib/tmux/tmux.ts:44` と `src/ops/app.ts:1494` 付近(作業台の画面がつながっている間に案内が消えたとき)** `ensureGuide` が走るのは `whatnext workbench` が起動したときだけです。そのため、つながったまま案内が消えると戻す手段がありません。
  - `pane-died` の `sh-*` の処理では、`switch-client -t "=wbguide"` が失敗したあと `kill-session` に進みます。作業台の最後のシェルを閉じると、作業台の画面ごと離れます。
  - 一覧の `doFollow` の `switchClient(wb, GUIDE)` も黙って失敗します。
  - DESIGN.md が退けているのは「一覧の側で作り直す」案のうち、attach の時点の話だけです。つながったあとの経路は抜けています。`sh-*` の処理で、切り替える前に案内があるかを確かめる(なければ作る)価値があります。

- **`src/cli/workbench.ts:33`** `res.status` は、tmux がシグナルで終わると `null` になります。この場合も `!== 0` が成り立つので、一覧が残っていれば「could not open」と出し、`fail()` でキーを待ちます。
  - 端末が閉じたときは親も SIGHUP で終わるので問題になりにくいです。ただ、`tmux kill-server` 以外の手段で client だけが殺されると、偽の失敗表示になります。
  - `res.signal` が付いているときは失敗と見なさないほうが意図に合います。

- **`src/cli/guide.ts:19`(`ensureGuide` を `whatnext workbench` から呼ぶとき)** `paneCommand(env, 'guide')` の `env.node`、`env.cli`、`PATH` は、`whatnext workbench` を起動したプロセスのものです。
  - 一覧が動いている間に利用者が `npm i -g` で版を上げ、手で `whatnext workbench` を打つと、作り直した案内のプログラムだけが新しい版になります。
  - `scripts()` の注記には「動いている一覧と同じ版のものを使わせる」とあり、この方針と食い違います。`@wn_guide` の JSON の形が版の間で変わると、表示が壊れます。
  - 一覧が自分のコマンドを tmux のオプション(例:`@wn_guide_cmd`)に置き、`ensureGuide` はそれを使う、という形が考えられます。

- **`src/cli/workbench.ts:27` と `src/ops/app.ts:1156`(頼みごと `guide`)** `doFollow` は `wbTty` がなければ何もしません(`app.ts:1469`)。また、`mainSession` が claude 以外のセッション(`trust-*` など)のときは途中で返ります。
  - 後者の場合、作り直した案内の `@wn_name` は空のまま残り、ステータス行は `workbench: ` だけになります。
  - 次に `doFollow` が案内の側を通れば `lastGuide` が空なので直りますが、それまでは名前が出ません。実害は小さいので、知っておけば十分です。

### 並行性

- **`src/cli/guide.ts:21`** 同時に作られたときに相手のものを使う処理は正しいです。ただ、`'exists'` を返すので、作った相手が `workbenchOptions` を入れ終える前に attach する可能性があります。その間は `prefix C-q` と `mouse` が効かず、ごく短い間だけ起こります。
- **`lib/tmux/tmux.ts:55`** `sleep 1` は `run-shell -b` の中なので、フックを塞ぎません。この 1 秒の間に `ensureGuide` が走ると、死んだペインを持つセッションを `'exists'` と見なして attach します。画面は 1 秒だけ空になりますが、起動し直したあとは追いつくので問題ありません。

### セキュリティ・プライバシー

- **`lib/tmux/tmux.ts:49`** `capture-pane` の末尾 5 行を、サーバ全体のオプション `@wn_guide_died` に置きます。中身はセッション名とパスです。tmux サーバのメモリの中だけでファイルには書かれないので、同じ利用者のソケットに届く範囲を超えては漏れません。
  - sh の上でも、コマンド置換の結果は評価し直されず、引数として渡るので、埋め込みの心配はありません。
  - 一点だけ:今後この値を `#{...}` の書式や `display-message` で出すなら、`escapeFormat` が要ります。
- **既存の問題(差分の外)** `signalGuide`(`lib/tmux/tmux.ts:400`)が読む `@wn_guide_pid` は、どこからも書かれていません(grep で書く側がありません)。今は 300ms の読み直しで動いているだけです。
  - 結果として、古い PID に SIGUSR2 を送る心配はありませんが、知らせとしては働いていません。起動し直すようになったので、PID を書くようにするなら、案内のプログラムが起動のたびに書き直す必要があります。

### 設計

- **`src/cli/list.ts:66-67`** 作ったときは `ensureGuide` の中で `workbenchOptions(GUIDE, '')` を呼び、そのあと一覧でも呼ぶので、二重になります。一覧の起動時には前の版のサーバを引き継いだ案内にも入れ直す意味があるので、一覧の呼び出しは残し、`ensureGuide` の説明にその分担を書くのがよいでしょう。
- **`lib/tmux/tmux.ts:48-59` と `docs/lib/tmux.md:19`** `lib/` は昇格済みのモジュールで、今回は契約の docs とテストを一緒に直しており、方針どおりです。ただし `tmux.test.ts` は、スクリプトに `respawn-pane` などの文字列が含まれるかを見ているだけです。振る舞いを確かめているのは e2e の側です。

### テスト

- **`test/e2e/workbench.test.ts:247-249`** `pid()` は、`display` が失敗すると `Number('')` で 0 を返します。`before` が 0 のまま `process.kill(0, 'SIGKILL')` が走ると、**テストの実行器を含むプロセスグループ全体を殺します**。`expect(before).toBeGreaterThan(0)` を挟んでください。
- **`test/e2e/workbench.test.ts:254`** `/signal=kill/` は、`#{pane_dead_signal}` を小文字の名前で出す環境(macOS の `sys_signame`)を前提にしているように見えます。Linux の CI で動かすなら、大文字の `KILL` か番号になる可能性があります(未確認)。

### 優先度

- 先に直したいもの:回数が戻らないこと(`tmux.ts:53`)、つながったまま案内が消える経路(`tmux.ts:44`)、e2e の `kill(0)`。
- 時間があれば:版の食い違い(`guide.ts:19`)、`res.signal` の扱い(`workbench.ts:33`)。
- 残りは軽微です。

残っている大きな不確実性は、DESIGN.md も認めているとおり、案内のプログラムが**なぜ終わったのか**がまだ分かっていないことです。今回の修正は症状を抑えるもので、原因は `@wn_guide_died` が手がかりを残すのを待つ形です。`@wn_guide_died` の中身を `WHATNEXT_DEBUG_LOG` にも書いておくと、tmux サーバが終わったあとも手がかりが残ります。

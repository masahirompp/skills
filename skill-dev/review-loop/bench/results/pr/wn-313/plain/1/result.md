PR #2 の差分(13ファイル、+177/−15)を読み、関係するコード(`App.doFollow`、`takeRequests`、`guide()`、`paneCommand`)も確かめました。直すべき不具合は見つかりませんでした。原因の切り分け(`kill-pane` で案内のセッションが消えること、`exec` が二重に付くこと)と直し方は筋が通っています。以下は優先度の高い順の指摘です。

### 要件・プロセス
- **`docs/PRODUCT.md`(更新なし)**: 利用者から見える挙動が3つ増えていますが、要件のファイルに書かれていません。
  - `whatnext: could not open the workbench screen ...` と `could not create the workbench guide ...` のメッセージ
  - Ghostty の分割で起動したとき、失敗すると `Press any key to close.` を出してキーを待つこと
  - 案内のプログラムが落ちても起動し直すこと
  
  理由は DESIGN.md「作業台の画面の仕組み」に書かれていますが、利用者がどう観測するかは PRODUCT.md の範囲です(CLAUDE.md の「要件と設計の2ファイル」)。PRODUCT.md:490 とシナリオ 59 の「終了コード 1 で終わる」に、キーを待つ場合を書き足すか、この挙動を層2として利用者に確かめるべきです。

### 挙動の弱点
- **`lib/tmux/tmux.ts:52-56`**: `@wn_respawned` はペインに付くオプションで、`respawn-pane` してもペインは同じなので、回数が戻りません。このため「起動してすぐ終わるときに回り続けないため」という理由とは違い、数日おきに1回落ちるだけでも、6回目にはセッションが畳まれます。
  - 畳まれた時点で作業台の画面が案内につながっていると、`detach-on-destroy on` で画面ごと離れ、#1 と同じ「急に閉じる」が起きます。終了コードは 0 になる見込みなので、エラーも出ません。
  - 直し方の案は2つです。最後に起動し直した時刻を残し、たとえば 60 秒以上動いていたら回数を戻すか、契約(`docs/lib/tmux.md`)に「生涯で5回まで」と明記するかです。
- **`src/cli/guide.ts:19`**: `whatnext workbench` から案内を作り直すと、`paneCommand(env, 'guide')` には、一覧のプロセスではなく Ghostty の分割のシェルの環境(`PATH`、`CLAUDE_CONFIG_DIR`、`WHATNEXT_DEBUG_LOG`、`LANG`)が入ります。
  - 手で別の版の `whatnext`(npx と global など)から `workbench` を打った場合、`env.cli` も一覧と違う版になりえます。そうすると案内だけが別の版で動きます。
  - 一覧が起動時に案内のコマンドを tmux のオプションに置き、`ensureGuide` はそれを使う形にすれば、こうしたずれが起きません。
- **`src/cli/workbench.ts:33`**: `res.status` が `null`(シグナルで終わった)の場合も `!== 0` になり、一覧が生きていれば「つなげなかった」と出します。今の経路ではたいてい node も同時に死ぬので実害は小さいですが、`res.signal` は分けて扱うほうが意図に合います。

### テストの移植性
- **`test/unit/cli.test.ts:26`**: `zsh` が入っていない環境(Linux の CI など)では `execFileSync('zsh', ...)` が ENOENT で落ちます。入っていなければ飛ばすべきです。
- **`test/e2e/workbench.test.ts:255`**: `/signal=kill/` が成り立つことは、手元の macOS と tmux 3.8 では確かめました(`pane_dead_signal` は `kill` を返しました)。ただ、この値はシグナル名を引く OS の関数に依存します。Linux では `KILL` や番号になる可能性があるので、`/signal=(kill|KILL|9)/i` くらいに緩めるのが安全です。
- **`lib/tmux/tmux.test.ts:75-80`**: 文字列を含むかだけを見ているので、たとえば `-lt 5` と `kill-pane` の分岐が逆になっても通ります。e2e で起動し直しは確かめていますが、5回を超えたら畳む側は、どのテストでも実際には動かしていません。

### 小さな整理
- **`src/cli/list.ts:66-67`**: `ensureGuide` が `'created'` を返したときは、その中(`guide.ts:22`)で `workbenchOptions(GUIDE, '')` がもう呼ばれていて、`list.ts:67` で2回目になります。既にあった場合に限って入れ直す意図なら、そう書くとよいです。
- **`src/cli/workbench.ts:43-52`**: `askListToRefreshGuide` の中身は、`guide.ts` の Enter の処理(`@wn_req_…` を書いて `@wn_pid` に SIGUSR2 を送る)とほぼ同じです。tmux.ts の `@wn_req_sh` とも役目が重なっています。`Tmux` に `request(line)` を1つ置けば、3か所が揃います。
- **`src/ops/app.ts:1475`**: `GUIDE_REFRESH` を受けても、whatnext の画面が `sh-` や `trust-` などを映していると、`doFollow` はこの行で先に抜けます。その間、作り直した案内のステータス行は `workbench: ` のまま空になります。実害は小さいですが、名前を入れ直す処理はこの分岐の前に置けます。
- 参考(この PR より前からある問題): `Tmux.signalGuide`(`lib/tmux/tmux.ts:400`)が読む `@wn_guide_pid` は、どこからも設定されていません。案内は 300ms ごとに読み直すので動いてはいますが、SIGUSR2 はずっと届いていません。

PR 本文にあるとおり、Ghostty + bash の実機(`test/real`)は流されていません。`exec` が二重に付く問題を直したことの最終確認になるので、マージの前に1回流すことを勧めます。テストは私も流していません(作業ツリーには触れていません)。

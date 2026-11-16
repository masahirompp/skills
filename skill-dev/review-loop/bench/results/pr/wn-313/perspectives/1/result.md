PR #2(`wbguide-recover`、d212b82、13ファイル +177/−15)を読みました。結論から言うと、直し方の大筋は妥当で、マージを止めるほどの欠陥は見つかりませんでした。指摘の中心は、`whatnext workbench` の側で案内のセッションを作り直すときに、どの版のプログラムを使うかです。

前提として、tmux 3.7c で attach の終了コードを実際に測りました。`kill-session` で離されたときと `detach-client` では 0、存在しないセッションと `kill-server` では 1 でした。`src/cli/workbench.ts:33` の「0 以外で、一覧がまだある」という見分け方は、この実測と合っています。

## 正確性

- **`src/cli/guide.ts:18`(`ensureGuide` を `src/cli/workbench.ts:22` から呼ぶ)**: 作り直した案内のコマンドが、一覧ではなく `whatnext workbench` を起動したプロセスの `env.node` / `env.cli` / `PATH` などから組み立てられます。たとえば一覧が global の whatnext で動いていて、利用者が別の checkout や `npx` で `whatnext workbench` を打つと、一覧とは別の版の案内のプログラムが、一覧が終わるまで動き続けます。`@wn_guide` の JSON や `key <GUIDE_CREATE> wbguide -` の頼みごとの形が版の間で変わると、案内が壊れます。
  - 直し方の案: 一覧が起動時に案内のコマンドをサーバのオプション(例: `@wn_guide_cmd`)に置き、`ensureGuide` はそれを使って作る。
  - 費用の小さい代わり: 少なくとも `@wn_version` と自分の版を比べ、食い違えば作らずにエラーにする。
- **`lib/tmux/tmux.ts:52-60`**: 起動し直した回数 `@wn_respawned` が減らないので、文書の「起動してすぐ終わるときに回り続けないため」という目的とずれています。何時間もの間に散発的に 6 回落ちただけでも、6 回目でセッションが畳まれます。
  - 畳まれた時点で作業台の画面が案内を映していると、`detach-on-destroy on` で離され、tmux は 0 で終わります。そのため Ghostty の分割は何も出さずに閉じ、#1 と同じ見え方になります(次の `w` では `ensureGuide` で直ります)。
  - 案: 前回落ちた時刻をペインのオプションに残し、たとえば 60 秒以上空いていれば数え直す。
- **`test/e2e/workbench.test.ts:255`**: `/signal=kill/` の小文字は macOS 向けの前提です。tmux の `#{pane_dead_signal}` は `sig2name` を通し、`sys_signame` を持たない glibc(Linux)では数字や別の表記になる見込みです(ソースは今回確かめていません)。実機が macOS + Ghostty 前提なら実害はありませんが、CI を Linux で回すなら落ちます。`/signal=(kill|9|KILL)/i` にしておくのが無難です。
- **`lib/tmux/tmux.ts:56-57`(`sleep 1` のあいだ)**: ペインは死んだままでもセッションは残っているので、この間の `ensureGuide` は `'exists'` を返し、attach すると「Pane is dead」が最大 1 秒見えます。害は小さく、直す必要はないと考えます。

## 並行性

- **`src/cli/guide.ts:19-20`**: 同時に作られたときに `'exists'` へ倒すのは正しいです。ただ、そのとき相手側の `workbenchOptions` がまだ入っていない可能性があります。ステータス行や `mouse` が一瞬既定のまま見える程度で、すぐ揃います。
- **`src/cli/workbench.ts:27` → `src/ops/app.ts:1156-1160`**: 頼みごと `guide` の流れは問題ありません。`onSignal` は、`takeRequests` と同じ周回で `WB_TTY` を読み、`this.wbTty` を書き換えてから `request` を処理します(`src/ops/app.ts:1142-1147`)。`whatnext workbench` は `WB_TTY` を `ensureGuide` より前に置くので、`doFollow` が `!wb` で早く戻ることもありません。

## セキュリティ・プライバシー

- `workbenchCommand` の引用は `shq` で、`'` を含むパスも bash・zsh・sh で動くことを単体テストで確かめています(`test/unit/cli.test.ts:27-30`)。打ち込む文字列の注入についての懸念はありません。
- `@wn_guide_died`(`lib/tmux/tmux.ts:51`)には、案内の画面の末尾(セッションの名前と `~` 起点のパス)が入ります。ただし利用者の専用 tmux サーバのメモリにあるだけで、外へは出ません。問題なしと判断しました。

## 設計

- **`src/cli/list.ts:66-67`**: `ensureGuide` が `'created'` のときは、`workbenchOptions(GUIDE, '')` を 2 回呼ぶことになります。害はありません。`'exists'` のとき(版を上げたあとにオプションを入れ直す)には 67 行目が要るので、残すなら「既存のセッションにも入れ直すため」とコメントを付けると意図が読めます。
- **`lib/tmux/tmux.test.ts:75-81`**: 案内の分岐のテストは、文字列が含まれているかを見るだけです。`-lt 5` が `-le 5` に変わっても通るので、回数の境目は E2E でも確かめていません。ここを守りたいなら、偽の `tmux` を PATH に置いて分岐を実際に動かすテストが要ります。
- **差分の外(以前からの問題)**: `Tmux.signalGuide`(`lib/tmux/tmux.ts:400`)が読む `@wn_guide_pid` を、書いている箇所がありません。案内は 300ms ごとの読み直し(`src/cli/guide.ts:62`)だけで更新されています。今回の頼みごと `guide` もこの読み直しに頼っているので、別の issue にする価値があります。

## 検討してほしい点

- 案内のプログラムが落ちた原因はまだ分かっていません。この PR は「落ちても戻す」対処なので、原因が「起動してすぐ落ちる」種類(版の食い違い、環境変数の不足)なら、5 回の上限を使い切ったあと、`ensureGuide` が同じコマンドで作り直して同じように落ちる、を繰り返します。`@wn_guide_died` が取れたら、落ちる原因を直すのか、作り直す仕組みを残すのかを決め直すのがよいと考えます。
- PR の本文にあるとおり、Ghostty + bash の実機(`test/real`)は流していません。今回直した `exec` の重複は bash でだけ起きていた不具合なので、マージの前に一度通すことを勧めます。

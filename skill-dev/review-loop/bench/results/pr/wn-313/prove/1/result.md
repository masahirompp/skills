**証明できた指摘なし**

PR #2 の変更が意図どおりに動かない場面を、実際に動かして探しました。再現できたものはありません。

## 確かめたこと

最初に `npm run build` をしてから実行しました。

| 確かめた場面 | 結果 |
|---|---|
| PR に含まれる作業台の E2E(`npx vitest run --dir test/e2e workbench ...`) | 15 件すべて通過 |
| 単体テスト(`npm test`) | 114 件すべて通過 |
| P1: 作業台の画面を開いたまま、案内のプロセスを 2.5 秒おきに 6 回 SIGKILL する | 5 回目までは起動し直し、6 回目でセッションを畳みました(残るセッションは `['list']`)。画面には `[exit 0]` だけが出て、誤った失敗の表示は出ません。5 回までという約束どおりです |
| P2: 2 つ目の作業台の画面を開く | 1 つ目は `[exit 0]` で閉じ、失敗の表示は出ません |
| P3: 作業台の画面で `ctrl+q d` を押す | `[exit 0]` で閉じ、失敗の表示は出ません |
| P4: 作業台の画面を開いたまま、一覧を `q` で終える | `[exit 0]` で閉じます。サーバが閉じた場合を、つなげなかった場合と取り違えていません |
| P5: 作業台で動いているものがある状態で、`q` のあと `y` を押して終える | 同じく `[exit 0]` で閉じます |
| P6: `TERM=dumb` と `WHATNEXT_WORKBENCH_SPLIT=1` を付けて attach をわざと失敗させる | tmux のメッセージと理由が残り、`Press any key to close.` が出ます。キーを押すと `[exit 1]` で終わります |
| P7: 一覧が動いていないときに、Ghostty の分割から起動した場合と同じ形で動かす | `whatnext is not running...` と `Press any key to close.` が出ます。キーを押すと `[exit 1]` で終わります |

P6 では、出るべき出力がそのまま出ました。

```
open terminal failed: terminal does not support clear
whatnext: could not open the workbench screen (tmux session "wbguide").
Press any key to close.[exit 1]
```

## 確かめていないこと

- Ghostty の実機での動き(AppleScript の分割、bash での ` exec ...` の打ち込み)は、この環境では動かせませんでした。PR の本文にあるとおり、`test/real` も流していません。打ち込む文字列が bash・zsh・sh で動くことは、PR の単体テストが通ることで確かめました。
- 起動し直しの回数は、時間がたっても戻りません。そのため、間をあけて 5 回落ちても 6 回目で畳みます。ただ、これは docs に書かれた「ペインごとに 5 回まで」のとおりで、意図に反するとは言えないので、指摘にしていません。

## 片付け

試しのコードは `scratch/probe*.test.ts` に置いたままです。このファイルは biome の lint に引っかかるので、置いたままだと `npm run check` が失敗します。消すかどうかはお任せします。

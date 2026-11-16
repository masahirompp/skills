## 結論:証明できた指摘なし

この変更(`lib/tmux/tmux.ts` の作業台の `status-format[0]` に、分割とウィンドウのキーを足したもの)を壊そうと試しましたが、壊れる入力は見つかりませんでした。試したことと結果は次のとおりです。

試し方:`scratch/` に小さなスクリプトを置きました。ビルド済みの `Tmux.createWorkbench` で、使い捨てのソケットに作業台 `sh-a0000000` を作ります。それを別の tmux の中から attach し、`capture-pane` で最下行を取りました。tmux はこの環境の 3.8 です。

| 試したこと | 結果 |
|---|---|
| ウィンドウ名に `%` を入れる(`a%Hb`、`100%done`) | `0:a%Hb* 1:100%done  · ^Q% split │ · ^Q" split ─ · ^Qc window`。strftime に食われるのは書式の固定部分だけで、名前は崩れない |
| `@wn_name` に `%` を入れる(`50%off %H`) | `workbench: 50%off %H  …` のまま出る |
| 幅を 60、40、34、25 にする | 右から欠けた。幅60では `… · ^Q% split │ · ^Q` で、`^Q%` は最後まで残る(意図どおり) |
| `docs/PRODUCT.md` の画面の例(幅33) | 取った画面 `workbench: fix-login  0:zsh*  · ^` が例と一字一句同じ |
| 「採らなかった形」の例(右寄せ、幅60) | 取った画面 `workbench: fix-login  0:zsh* 1:zsh  ^Q" split ─ · ^Qc window` が例と同じ |
| 案内に出したキーを実際に押す(whatnext の `serverConfig` も流し込んだ状態) | `C-q %` で左右に、`C-q "` で上下に分かれ、`C-q c` で窓が増えた。root 表の `C-q` とはぶつからない |
| `npm test`、`workbench.test.ts` の e2e、`npm run check` | unit は 106 件、e2e は 13 件すべて通った。check は `scratch/` を除けば通る(エラーは私が置いたスクリプトのものだけ) |

試していないことが2つあります。
- tmux 3.7c での実測。スキルに書かれている版で、この環境は 3.8 です。
- 古い版で作った作業台が残ったまま更新したときに、キーが出るか。作業台のオプションは `createWorkbench` のときにしか入りません。ただ、サーバが更新をまたいで残る場面を再現していないので、指摘にはしていません。

`scratch/` には試しに使ったスクリプト(`setup.mjs`、`cfg.mjs`、`att.sh`)が残っています。tmux のサーバはすべて止めました。

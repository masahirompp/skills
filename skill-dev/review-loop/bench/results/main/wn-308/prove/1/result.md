**証明できた指摘はありません。**

壊そうとして実行したものと、その結果を書きます。すべて、このディレクトリの中に作った `scratch/` のスクリプトを tmux 3.8 で動かした結果です。

| 試したこと | 結果 |
|---|---|
| `test/e2e/workbench.test.ts` | 13件すべて通過 |
| `npm test` と `biome check` | 106件通過、lint の指摘なし |
| `%%` が `%` として出るか(`scratch/probe.mjs`) | `workbench: fix-login  0:zsh*  · ^Q% split │ · ^Q" split ─ · ^Qc window` と出る |
| セッション名とウィンドウ名に `%H`、`%Y` を入れる | `fix%Hlogin`、`0:z%Ysh*` のまま出る。時刻には化けず、キーの表示も崩れない |
| 幅40 | `workbench: fix-login  0:zsh*  · ^Q% spli`。右から欠けて、`^Q%` は残る |
| 幅60でウィンドウ4つ | `… 3:zsh  · ^Q% split`。`^Q%` は最後まで残る |
| 全角の名前(`ログインの不具合を直す`)を幅60で | `… · ^Q% split │ ·`。全角でも幅の計算はずれない |
| docs の「採らなかった形」を、右寄せの書式で実際に描く(`scratch/probe2.mjs`) | `workbench: fix-login  0:zsh* 1:zsh  ^Q" split ─ · ^Qc window` と出る。`docs/PRODUCT.md` の例と一字一句同じ |
| docs の全体図の右の枠(中身は33桁) | 幅33の実際の描画 `workbench: fix-login  0:zsh*  · ^` と一致 |
| whatnext の `serverConfig` を流し込み、root の表に `C-q` を割り当てた状態で `^Q%`、`^Q"`、`^Qc` を押す(`scratch/probe3.mjs`) | ペインは 1 → 2(左右) → 3(上下) と増え、最後に新しいウィンドウ `1.0` ができる。案内した3つのキーは、どれも実際に効く。whatnext のキー(`l w v e x n f`)ともぶつからない |

見た範囲の限界も書いておきます。
- 確かめた tmux は 3.8 です。スキルに書いてある 3.7c では動かしていません。
- 案内の画面(`wbguide`)の書式は、この差分で変わっていないので試していません。

`scratch/` には、上の3つのスクリプトを残しています。

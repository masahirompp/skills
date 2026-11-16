**証明できた指摘はありません。**

差分は `lib/tmux/tmux.ts` の作業台の `status-format[0]` の1行と、docs・スキル・e2e テストの更新です。壊せそうな点を実機で順に試しましたが、意図から外れた挙動は再現できませんでした。

## 試したことと結果

**1. `%%` が `%` として出るか、狭い幅でどう欠けるか**(実際の tmux 3.8 で、`scratch/render.sh` を使って描画を取りました)
```
 80|workbench: fix-login  0:zsh*  · ^Q% split │ · ^Q" split ─ · ^Qc window
 60|workbench: fix-login  0:zsh*  · ^Q% split │ · ^Q" split ─ ·
 40|workbench: fix-login  0:zsh*  · ^Q% spli
 34|workbench: fix-login  0:zsh*  · ^Q
 30|workbench: fix-login  0:zsh*
 25|workbench: fix-login  0:z
```
`%` は出ており、右から欠けます。キーの中では `^Q%` が最後まで残るので、コミットの意図どおりです。

**2. PRODUCT.md の図と「採らなかった形」は実際の描画と合うか**
- 採らなかった形(右寄せ、幅60、窓2つ)を描画すると `workbench: fix-login  0:zsh* 1:zsh  ^Q" split ─ · ^Qc window` になり、docs の例と1文字も違いません。
- 図の右の枠は34桁で、先頭の1桁は空白です。中身の33桁を描画すると `workbench: fix-login  0:zsh*  · ^` で、図と同じでした。

**3. 出したキーが作業台で実際に効くか**
`bind -n C-q switch-client -T wnq` が root にあるため、prefix より先に横取りされる疑いがありました。e2e のハーネスで一時テストを動かして確かめました(テストは終わったあと消しています)。
```
GUIDE: "workbench: alpha"
STATUS0: "workbench: alpha  0:zsh*  · ^Q% split │ · ^Q\" split ─ · ^Qc window"
panes after ^Q": %2 top=0 / %3 top=10
windows after ^Qc: 0:zsh / 1:zsh
STATUS1: "workbench: alpha  0:zsh 1:zsh*  · ^Q% split │ · ^Q\" split ─ · ^Qc window"
```
`^Q"` で上下に分かれ、`^Qc` でウィンドウが増えます。案内のセッションには名前だけが出ており、これも意図どおりです。

**4. 名前に `%` を含むと崩れるか**
`NAME='50%off %d'` で描画すると `workbench: 50%off %d  0:zsh*  · ...` でした。strftime が効くのは書式の文字列だけで、値は壊れません。

**5. 既存のチェック**
- `test/e2e/workbench.test.ts`:13件すべて通過
- `npm test`:106件すべて通過
- `npm run check`:通過。一度失敗しましたが、原因は私が置いた一時テストのファイルで、消したあとに通りました。

## 確かめて、外したもの
`workbenchOptions` は作業台を作るときにしか呼ばれないので、旧版で作った作業台にはキーが出ないのではと考えました。しかし docs では、新しい版に移るには whatnext の終了が必要で、終了すると作業台は消えます。そのためこの場面は起きず、指摘から外しました。

試すのに使ったスクリプトは `scratch/` に残してあります。リポジトリのほかのファイルは変えていません。

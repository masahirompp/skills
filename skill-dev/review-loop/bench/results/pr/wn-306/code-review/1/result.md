9 findings, most severe first:

1. `src/screen/screen.ts:230`: 選んだ行のすぐ下の起動された行まで cursorBlock を伸ばしたため、b1 が選んだ行の入力欄の終わりではなく、続く (sub) 行の終わりを指すようになった。そのため「入力欄は最後の行まで窓に入れる」の補正で窓が下へずれ、入力欄と選んだ行が窓の外に押し出される。

   Failure scenario: P の下に (sub) 行が10行あり、高さ10の端末で P に `e` を押してメモを書く場合。avail=7、cursorBlock=[P の行, 最後の w9 の行] で、blockLen が avail 以上なので start=b0 になる。続く `s.inline && b1 > start+avail` で start=b1-avail に移り、w3〜w9 だけが映る。P の行も、入力中のメモ欄も見えなくなる。

2. `src/screen/screen.ts:213`: 最初の選べる行を選んだときに cursorBlock の始まりを 0 に固定するので、その上の (sub) 行が窓の高さを超えると、blockLen >= avail で start=b0=0 になり、選んだ行そのものが窓に入らない。

   Failure scenario: 一覧に出ていない対話セッションが `claude -p` を12個起動し、トップレベルの (sub) 行が12行、その下に最初の選べる行 s0 がある場合。高さ10では avail=7、cursorBlock=[0,14] で start=0 になり、画面には見出しと (sub) 行6行だけが出る。`> s0` は見えず、`1/N` だけが出る。

3. `src/ops/app.ts:263`: 選んでいた行が消えずに起動された行へ変わったときも goneName を作って guard を張るため、Ctrl+X を押すと、一覧に残っている行について「left the list」と事実と違う文言が出る。

   Failure scenario: (tty) の行 X を選んでいる。ある回で ps の表が読めず起動元が分からなかったが、次の回に起動元 P が分かり、X が P の下の (sub) に変わる。カーソルは隣の background 行 B に移り、guard={name:X} が張られる。直後に Ctrl+X を押すと `Ctrl+X ignored: X left the list and the selection moved.` と出るが、X は一覧に残っている。

4. `src/ops/app.ts:838`: openNote と openWait から起動された行を断る守りを消したが、attachKey の `this.cursor = sid` の経路(GUIDE のときの guideTarget)は、選べるかを確かめずに sid をそのまま使う。古い guideTarget が起動された行を指していると、その行にメモや待ち先を付けられる。

   Failure scenario: カーソルが X にあり、guideTarget も X。更新で X が起動された行に変わってから、follow の60msの遅延と doFollow が済むまでの間に、作業台の案内画面でメモのキーを押す。sidOfSession(GUIDE) は X を返し、cursor=X(選べない行)になり、openNote(X) がメモの入力欄を開く。待ち先は validWaits で黙って外れ、カーソルは選べない行に乗ったままなので ↑ も効かない。

5. `src/ops/app.ts:1197`: cursor を直接代入する経路(attachKey)が選べるかを確かめないので、「カーソルは起動された行に置かない」という不変条件が selectableOrder を通る経路でしか守られていない。

   Failure scenario: cursor が起動された行に入ると、listKey の `order.indexOf(cursor)` が -1 を返し、`↑` は何もしない。`↓` は order[0] に飛び、選んでいた位置から外れる。render は、その行を選んだ行として `>` を付けて描き、rowIndex.indexOf(cursor)+1=0 なので `0/N` を出す。

6. `src/screen/screen.ts:201`: 選べるかの判断を、画面側では表示用の `r.marker !== 'sub'` で、モデル側では Layout の `spawned` で、別々に行っている。選べる行の定義が2か所にある。

   Failure scenario: 将来 marker の付け方(例: 'sub' と 'tty' を両方持たせる、印の文言を変える)を変えると、selectableOrder と画面の rowIndex や cursorBlock の数え方が黙ってずれ、`<通し番号>/<総数>` や窓の位置が ↑↓ の並びと合わなくなる。ScreenRow に selectable を渡すか、selectableOrder の結果を Screen に渡すべき。

7. `src/screen/screen.ts:205`: trailing が区切りの境目で戻らないので、ある区切りの最後の選べる行を選ぶと、空行、次の区切りの見出し、その先頭のトップレベル (sub) 行まで cursorBlock に入る。「すぐ下に続く起動された行」の範囲を超えている。

   Failure scenario: 区切り A の最後の行 Y を選んでいて、区切り B の先頭に起動元が一覧に出ていない (sub) 行が並ぶ場合。cursorBlock は B の見出しと (sub) 行まで伸び、中央に寄せる計算が狂う。Y が窓の上端に寄るか、ブロックが avail を超えると start=b0 になり、Y の上の文脈が見えなくなる。

8. `src/model/cursor.ts:6`: selectableOrder は order の各要素について isSpawned(全区切り・全ノードの走査)を呼ぶので O(n²) になる。これをキーを押すたびと更新のたびに呼び、followCursor の ok() でも order.includes と isSpawned を重ねて呼んでいる。

   Failure scenario: 行が多い一覧で ↑↓ を押し続けると、キー1回ごとに全ノードを n 回走査する。起動された行の Set を Layout から1回作れば O(n) で済む(Layout に selectable/spawned の Set を持たせる)。

9. `test/e2e/deps.test.ts:441`: シナリオ70のテストは、other が orchestrator の上と下のどちらにあるかで押すキーを `below ? 'Down' : 'Up'` と切り替えるため、並びの前提が崩れても通ってしまう。(sub) 行を飛ばす向きも1方向しか確かめていない。

   Failure scenario: other が orchestrator の上に並ぶ場合、テストは Up から始まり、P の下の worker/worker-2 を ↓ で飛ばす肝心の挙動を確かめない。↓ の飛ばしが壊れても、テストは通りうる。

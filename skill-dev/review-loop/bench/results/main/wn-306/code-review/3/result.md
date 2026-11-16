9 findings, most severe first:

1. `src/screen/screen.ts:213`: 最初の選べる行を選んでいると、塊の始まりを 0(一覧の先頭)にする。その上にある見出しと (sub) の行で窓が埋まると、塊が窓以上の長さになって start = b0 = 0 に固定され、選んだ行(`>`)が窓の外に押し出される。

   Failure scenario: 高さ 10 の端末で、最初の区切りの先頭にトップレベルの (sub) の行が 7 行(注記付きなら 3 行ほどでも)並び、その下に最初の選べる行がある。カーソルはその行にあるのに、窓には見出しと (sub) の行しか映らず、`>` の行が見えない。

2. `src/ops/app.ts:265`: 選んでいた行が一覧に残ったまま起動された行に変わったときも、goneName を求め(prevLayout.order に含まれるため)守りを立てる。そのため、行が消えていないのに `Ctrl+X ignored: <名前> left the list and the selection moved.` と示される。

   Failure scenario: (tty) の行 worker を選んでいる。次の更新で ps の表から起動元 P が分かり、worker は P の下の (sub) に変わって、カーソルが P に移る。2 秒以内に Ctrl+X を押すと「worker left the list」と誤った知らせが出る。worker は一覧に残っている。PRODUCT.md「操作」の守りの条件(選んでいた行が一覧から消えたとき)とも食い違う。

3. `src/screen/screen.ts:230`: 起動された行はカーソルで選べないのに、窓は選んだ行の塊でしか動かない。そのため、塊が窓より長いときや、選べる行が 1 つもないときは、窓の外に出た (sub) の行をどうやっても見られない。

   Failure scenario: (1) 一覧に出ていない対話セッションが `claude -p` を多数起動し、トップレベルの (sub) の行だけが端末の高さを超えて並ぶ。cursor が undefined なので start=0 に固定され、下の行は見えないままになる。(2) P のすぐ下に、窓より多い (sub) の子が続く。blockLen >= avail で start=b0 になり、P の塊の末尾は切れる。次の選べる行の塊を中央に置いても途中の子は窓に入らず、PRODUCT.md の『選べない行が画面の外に残って見られなくなるのを防ぐ』を満たさない。

4. `src/screen/screen.ts:224`: カーソルがない(選べる行がない)まま一覧があふれると、idx は 0 になり、`0/0` や `0/N` のような意味のない通し番号が出る。

   Failure scenario: (sub) の行だけが端末の高さを超えて並ぶと、一覧の直後に `0/0` が出る。総数 0 なのに一覧には行があり、利用者を混乱させる。

5. `src/ops/app.ts:1197`: openNote と openWait から、起動された行を断る守りを外した。いまは、カーソルが起動された行に乗らないことだけが守りになっている。attachKey は sidOfSession から得た sid を、選べるかを確かめずに this.cursor に入れ、openNote と openWait を呼ぶ。

   Failure scenario: いまは起動された行が必ず interactive で id を持たないので、この経路には届かない(deriveSpawners は background を除く)。ただし起動された行に id が付く変更が入ると、attach 中の note のキーで起動された行のメモ欄が開き、保存したメモは描画で隠されて見えない。wait のキーでもメニューが開くが、canLink が false を返すので何も知らせずに終わる。

6. `src/screen/screen.ts:201`: 画面の組み立ては、選べるかどうかを `r.marker !== 'sub'` という表示の印から決めている。App と cursor.ts は Layout の node.spawned から決めるので、選べるかの出どころが 2 つある。

   Failure scenario: marker の付け方が変わると、<通し番号>/<総数> と窓の塊が、↑↓ で動く並び(selectableOrder)とずれる。たとえば (sub) と (tty) の表示をまとめるか、起動された行に別の印を足す変更である。ScreenRow に selectable を渡すか、Screen に selectableOrder を渡せば、出どころを 1 つにできる。

7. `src/model/cursor.ts:6`: selectableOrder は order の各 sid について isSpawned を呼び、そのたびに全区切りの全ノードをなめるので O(n²) になる。キーを押すたび(listKey)と更新のたびに計算し直している。

   Failure scenario: 行が数十あると、↑↓ を押すたびに数千回の比較が走る。layout は order を groups の nodes の順に作るので、`l.groups.flatMap(g => g.nodes.filter(n => !n.spawned).map(n => n.sid))` の 1 回の走査で同じ結果が得られる(Layout に持たせてもよい)。

8. `test/e2e/deps.test.ts:465`: シナリオ 71 は f と e を送った直後に、知らせやメニューが出ていないことを待たずに確かめている。描画が後から来る場合を捉えられず、『何もしない』を検証できていない。

   Failure scenario: f が誤ってメニューを開くようになっても、描画が keys() の戻りより遅ければ `not.toMatch(/waits for:|can't/)` は通ってしまう。少し待つか、更新を 1 回挟んでから確かめる必要がある。

9. `test/e2e/deps.test.ts:442`: シナリオ 70 は other が orchestrator より下か上かで押すキーを切り替えるので、並びが変わってもテストは通る。『↓ で起動された行を飛ばして次の行に移る』を確実には検証していない。

   Failure scenario: other が orchestrator より上に並ぶと、テストは Up/Down の向きを入れ替える。その結果、↓ が (sub) の子を飛ばす経路を一度も通らないまま通ることがある。並びを times で固定し、向きを決め打ちにすべきである。

確定した問題は上の 2 件で、どちらも描画を手で追ったか、コードの経路を読んで確かめました。

- **選んだ行が見えなくなる(screen.ts:213)**: 最初の選べる行を選ぶと、窓を一覧の先頭から始めます。その上の (sub) の行が多いと、カーソルのある行が画面の外に出ます。
- **誤った知らせ(app.ts:265)**: 選んでいた行が消えずに起動された行に変わっただけでも、守りが立ちます。すると Ctrl+X で `left the list` と、事実と違う知らせが出ます。

残りの扱いは次のとおりです。

- 3 件目(窓の外の (sub) の行を見られない)と 4 件目(`0/0` の表示)は、選べる行がない場合や塊が窓より長い場合の端の問題です。
- 5 件目(attachKey の経路)は、起動された行が必ず interactive で id を持たないので、いまは起きません。守りを外したことによる将来の危険として挙げています。
- 6 件目と 7 件目は整理の指摘、8 件目と 9 件目はテストが弱いという指摘です。

指示どおり検証の段は回していないので、確定した 2 件以外は確かめていない候補です。

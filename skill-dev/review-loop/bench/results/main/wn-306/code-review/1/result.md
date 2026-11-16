9件見つかりました。正しさに関わる問題は先頭の3件で、どれも画面の窓の計算（`src/screen/screen.ts`）にあります。描画の関数を一時的なテストで直接呼び、1と2は画面を取って確かめました（一時ファイルは消し、作業ツリーは clean のままです）。3は計算をたどっただけで、画面では確かめていません。4〜9はコードを読んでの判断で、実行しての確認はしていません。

9 findings, most severe first:

1. `src/screen/screen.ts:233`: 選んだ行のすぐ下に続く (sub) の行まで cursorBlock を伸ばしたので、b1 が入力欄の終わりではなく最後の (sub) の行の位置になった。そのため『入力欄は最後の行まで窓に入れる』の補正が窓を下へずらしすぎ、選んだ行もメモの入力欄も窓の外に出る。

   Failure scenario: 高さ10の端末で、(sub) の行を12個持つ起動元 p を選んで e を押す。blockLen >= avail なので start=b0 になるが、そのあと s.inline && b1 > start+avail の補正で start=b1-avail に動く。画面には w5〜w11 (sub) だけが並び、'> p' もメモの入力欄も出ない（render を直接呼んで確かめた）。利用者は何を打っているか見えないまま入力することになる。

2. `src/screen/screen.ts:213`: 最初の選べる行を選んでいるときは塊を一覧の先頭（0）から始めるが、その上に並ぶトップレベルの (sub) の行が窓より多いと、blockLen >= avail で start=b0=0 になり、選んだ行そのものが窓の外に出る。

   Failure scenario: 起動元が一覧に出ていない (sub) の行12個のあとに s0〜s4 が並び、高さ10で s0 を選ぶ。画面には見出しと w0〜w5 (sub) と '1/5' だけが出て、'> s0' は見えない（render で確かめた）。PRODUCT 24 の『選んだ行が見えるようにスクロール』を破る。

3. `src/screen/screen.ts:223`: 選べる行がなくカーソルが undefined のとき、cursorBlock は [0,0] のままなので窓は先頭に固定され、高さを超えた (sub) の行はどの操作でも見られない。通し番号も '0/0' になる。

   Failure scenario: 一覧に出ていない対話セッションが claude -p を端末の高さより多く起動する（オーケストレーションでは日常的）。カーソルがないので ↑↓ が効かず、下にある (sub) の行は画面の外に残る。PRODUCT が新しく書いた『選べない行が画面の外に残って見られなくなるのを防ぐ』と食い違う。'0/0' は総数があるのに0件に見える。

4. `src/ops/app.ts:263`: 選んでいた行が消えずに起動された行へ変わったときも、prevLayout.order に入っているので goneName が付き、Ctrl+X の保護が『left the list』の文言で出る。実際には行は一覧に残っている。

   Failure scenario: (tty) の worker を選んでいる間に、次の更新で起動元 P が一覧に出て worker が P の下に (sub) で入る。カーソルは隣の行に移り、2秒以内の Ctrl+X には『Ctrl+X ignored: worker left the list and the selection moved.』と出る。worker は画面に残っているので、示された内容が画面と食い違う。

5. `docs/DESIGN.md:132`: 『選んでいた行が更新で起動された行に変わったときも、消えたときと同じに隣の行へ移る』は観測できる振る舞いなのに、DESIGN.md にしか書かれていない。PRODUCT.md の『カーソル』の節とシナリオに入っておらず、層2のエスカレーションの記録もない。

   Failure scenario: CLAUDE.md（リポジトリ直下）の『`docs/PRODUCT.md` は要件(何を実現するか。観測できる振る舞い、受け入れシナリオ…)』と『2. 観測可能な挙動・仕様の変更: 人間へのエスカレーション必須』に反する。移る先を隣の行にするか起動元にするかは利用者に見える違い（起動元の下に入った行のそばに残るかどうか）だが、要件に書かれないまま実装されている。

6. `src/screen/screen.ts:201`: 画面側は『選べるか』を表示用の印 r.marker !== 'sub' で判定し、モデル側（selectableOrder）は layout の node.spawned で判定している。真実の出どころが2つある。

   Failure scenario: marker の導き方（app.ts 447 の n.spawned ? 'sub' : …）が将来変わる、たとえば印を別の文言に替えると、通し番号と窓の塊は ↑↓ の並びと黙って食い違う。ScreenRow に selectable フラグを渡すか、cursor.ts と同じ判定を共有すれば1か所で済む。

7. `src/model/cursor.ts:6`: selectableOrder は order の各 sid について isSpawned で全区切りの全 node を走査する（O(n²)）。それを ↑↓ のキー入力のたびと更新のたびに組み直している。

   Failure scenario: 行が多い一覧で ↑↓ を押し続けると、押すたびに n×n の走査が走る。layout を作る時点か関数の頭で、spawned の Set を1回作れば O(n) で済む。followCursor の ok() も、試すたびに next.order.includes と isSpawned を繰り返している。

8. `src/screen/screen.ts:215`: trailing は区切りをまたいでも戻らないので、区切り A の最後の行を選ぶと、空行、次の区切り B の見出し、B の先頭にあるトップレベルの (sub) の行まで、選んだ行の塊に入る。

   Failure scenario: 区切り A の最後の行を選び、区切り B の先頭に起動元が一覧にない (sub) の行が並ぶ。塊が B の見出しまで伸びるので、窓の中央寄せがずれ、選んだ行の前後の文脈が不自然に削られる。設計の『選んだ行のすぐ下に続く起動された行』を超えて、別の区切りの行まで同じ塊として扱っている。

9. `test/e2e/deps.test.ts:465`: シナリオ 71 の『f も e も何もしない』の確かめが、/waits for:|can't/ が出ないことしか見ていない。e でメモの入力欄が開いても検出できない。

   Failure scenario: 将来、カーソルが undefined の行や (sub) の行で openNote が開くようになっても、入力欄の文言は 'waits for:' も "can't" も含まないので、テストは通ってしまう。openNote と openWait から isSpawned の断りを外したので、このテストが唯一の歯止めになっている。

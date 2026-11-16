8 findings, most severe first:

1. `src/screen/screen.ts:213`: 最初の選べる行を選ぶと、窓の塊を一覧の先頭(0)から始める。上に並ぶ見出しと (sub) の行が窓の高さを超えると、blockLen >= avail で start = b0 = 0 になり、選んだ行が窓の外に出る。

   Failure scenario: 区切り a に起動元が一覧に出ていないトップレベルの (sub) の行が8つあり、区切り b の先頭が最初の選べる行 s0 で、端末の高さが 10 のとき。avail は 7 で、塊 [0, s0 の行の末尾] は 7 行を超えるので start=0 になる。見出しと (sub) の行6つだけが見え、カーソルの行 `> s0` はどこにも描かれない。'選んだ行が見えるようにスクロール'(シナリオ24)が破れる。

2. `src/screen/screen.ts:215`: 選んだ行に続く (sub) の行の分だけ cursorBlock[1] を伸ばすので、233行目の『入力欄は最後の行まで窓に入れる』が入力欄ではなく最後の (sub) の行を基準にする。

   Failure scenario: (sub) の行を10個持つ起動元 P で、低い端末で `e` を押してメモの入力欄を開く。b1 が最後の (sub) の行の末尾になるので、start = b1 - avail が窓を下へ送り、P の行と `Note for P: …█` の入力欄が窓の上に押し出される。利用者は打っている入力欄を見られない。

3. `src/ops/app.ts:265`: 選んでいた行が一覧に残ったまま起動された行に変わった場合にも、goneName が入り、Ctrl+X の受け付け止め(guard)と『left the list』の文言を出す。

   Failure scenario: 選んでいた tty の行 S の起動元が、更新で分かって S が (sub) になる。カーソルは隣の bg の行に移り、2秒以内の Ctrl+X は `Ctrl+X ignored: S left the list and the selection moved.` で断られる。S は一覧に残っているので文言は事実と違い、PRODUCT.md 591行目の『一覧から消えて』の条件の外で guard が働く。

4. `src/ops/app.ts:1197`: openNote から起動された行を断る守りを消し、選べないことだけを頼りにした。しかし attachKey は sidOfSession(GUIDE→guideTarget)の sid を、選べるかを確かめずに this.cursor に入れ、openNote を呼ぶ。

   Failure scenario: 更新で選んでいた tty の行 X が (sub) に変わった直後で、doFollow(60ms 後)が guideTarget を書き直す前に、作業台の案内の窓からメモのキーを押す。cursor が X(起動された行)に戻り、X のメモ入力が開く。persisted.notes に起動された行のメモが保存されるが、画面では隠れる。↑ は i=-1 で効かなくなる。

5. `src/screen/screen.ts:224`: 選べる行がなく、(sub) の行だけが端末の高さを超えて並ぶと、`0/0` と出し、窓は先頭に固まる。

   Failure scenario: 一覧に出ていない対話セッション Q が `claude -p` を20個起動し、トップレベルの (sub) の行だけが並ぶ。cursor が undefined なので cursorBlock は [0,0] のまま、start=0 になる。下の (sub) の行はどのキーでも見られず、位置の表示は行があるのに `0/0` になる(PRODUCT.md の『選べない行が画面の外に残って見られなくなるのを防ぐ』に反する)。

6. `src/screen/screen.ts:215`: trailing は区切りをまたいでも解けない。区切りの最後の行を選ぶと、空行、次の区切りの見出し、その区切りの先頭にある別の組のトップレベルの (sub) の行まで、選んだ行の塊に入れる。

   Failure scenario: 区切り a の最後の行 L を選び、区切り b の先頭に起動元が一覧に出ていない (sub) の行が並ぶ。塊が b の見出しと (sub) の行まで伸びて窓の中心がずれ、L と関係のない行が『選んだ行のすぐ下に続く起動された行』として扱われる。区切り a 内で L の下に続く兄弟のトップレベルの (sub) の行も同じ扱いになる。

7. `src/model/cursor.ts:6`: isSpawned は毎回すべての区切りのすべてのノードを走査する。それを order.filter の中で呼ぶ selectableOrder は O(N²) で、キーを押すたび(listKey)と更新のたび(apply)に作り直す。

   Failure scenario: followCursor の ok() は next.order.includes と isSpawned を、ループの中で行ごとに呼ぶので O(N²)〜O(N³) になる。行数が増えると ↑↓ の応答と更新が無駄に重くなる。layout() で spawned の Set(または Layout.selectable)を一度作って引けば O(1) で済む。

8. `src/screen/screen.ts:201`: 『選べる行』の定義が2か所にある。cursor.ts は Layout の node.spawned で、screen.ts は表示用の r.marker !== 'sub' で数える。

   Failure scenario: screen 側は g.nodes.filter(n => this.rows.has(n.sid)) を通したあとの行で数え、cursor 側は lay.order 全体で数える。印の付け方(marker)を変えたり、行のフィルタが食い違ったりすると、`<通し番号>/<総数>` と ↑↓ で動く並びがずれる。Screen に selectable の旗を持たせて1か所から導けば、二重の定義が消える。

レビューの対象はブランチ `sub-rows-unselectable` の `git diff main...HEAD` です。`gh pr view 2` もこのブランチの PR を返しました。今回は検証を挟まずに洗い出したので、確度は項目ごとに違います。

- **確度が高い(1〜3件目)**: 窓のスクロール2件と、guard の誤った文言です。コードの筋を追うだけで再現の筋道が立ちます。
- **確度が低い(4件目)**: 守りを外した openNote が、作業台の案内の窓からのキーで届く経路です。doFollow が guideTarget を書き直すまでの約60ms に限った競合です。
- **仕様の解釈しだい(6件目)**: 区切りをまたぐ trailing は、PRODUCT.md の『選べない行が画面の外に残って見られなくなるのを防ぐ』という狙いには合っています。意図した挙動かもしれません。

PR #2(`sub-rows-unselectable`)をレビューしました。指摘は 9 件で、正しさの問題を先に並べています。中でも重いのは 1 件目(メモの入力欄が窓の外に押し出される)と 3 件目(入力中の行が `(sub)` に変わったとき、入力の行き先がそのまま残る)です。8 件目の README の記述の古さは、CLAUDE.md の永続層の規約に反しています。

9 findings, most severe first:

1. `src/screen/screen.ts:211`: trailing で cursorBlock[1] を後続の (sub) 行の末尾まで延ばしたため、入力欄を窓に入れる補正 `if (s.inline && b1 > start + avail) start = b1 - avail` が、メモの入力欄ではなく最後の (sub) 行に合わせて窓を下げる。

   Failure scenario: 高さ 10 の端末で、(sub) の子を 8 行持つ P を選んで `e` を押す。block は P の行、入力欄 2 行、(sub) 8 行で avail を超える。start = b0 のあと、補正で start = b1 - avail に移り、窓には (sub) の行だけが並ぶ。P の行も `Note for P:` の入力欄も見えないまま、打った文字が入っていく。

2. `src/screen/screen.ts:213`: 最初の選べる行なら cursorBlock の始まりを 0 にする特例のせいで、前に並ぶトップレベルの (sub) 行と見出しが avail 以上あると、blockLen >= avail で start = 0 になり、選んだ行が窓の外に出る。

   Failure scenario: 起動元が一覧に出ていない (sub) 行が、トップレベルに 10 行並ぶ(1 番目の区切り全体がそうでもよい)。その下に最初の選べる行 A がある。高さ 10 の端末で A を選ぶと、block は [0, A の末尾] で avail を超え、start は 0 になる。窓には見出しと (sub) 行しか出ず、カーソルの行 `> A` が画面にない。

3. `src/ops/app.ts:262`: 選んでいた行が更新で起動された行に変わると、カーソルは隣へ移るが、mode(note か wait)は元の行の sid のまま残る。入力欄はカーソルのない (sub) 行の下に出続け、Enter で起動された行にメモが保存される。

   Failure scenario: (tty) の行 S で `e` を押してメモを入力している間に、更新で S の起動元が分かって S が (sub) になる。カーソルは隣の行 P に移り、armed だけが消える。mode.k は 'note' で sid は S のまま、入力欄は S の下に描かれる(窓は P に合わせるので見えないこともある)。Enter で commitNote(S) が走り、起動された行にメモが付く。画面では note を隠すので見えず、`Added a note to S.` だけが出る。

4. `src/ops/app.ts:843`: openNote から起動された行を断るガードを消したが、openNote はカーソル以外の経路からも呼ばれる。attachKey は sidOfSession(GUIDE なら guideTarget)の sid を this.cursor に入れてから openNote に渡すので、起動された行のメモ入力が開きうる。

   Failure scenario: 作業台の案内にカーソルの行 S が出ている。更新で S が (sub) に変わり、カーソルは移るが、follow は 60ms 遅れて動くので guideTarget はまだ S のまま。この間に作業台で ctrl+q ctrl+e を押すと、sid = S が cursor に入り、openNote(S) が断らずに note mode を開く。起動された行を選べないという不変条件が破れ、メモも付く。

5. `src/ops/app.ts:265`: 条件を `!selectableOrder(...).includes(cursor)` に広げたため、行が一覧に残ったまま (sub) に変わっただけでも goneName が入って guard が立つ。直後の Ctrl+X で『left the list』という事実と違う文言が出る。

   Failure scenario: (tty) の行 S を選んでいる。更新で S が P の下の (sub) に変わり、カーソルが P に移る。2 秒以内に Ctrl+X を押すと `Ctrl+X ignored: S left the list and the selection moved.` が出るが、S は一覧に残っている。PRODUCT.md「操作」の守りは、行が一覧から消えた場合しか定めていない。

6. `src/screen/screen.ts:214`: trailing は次の選べる行が出るまで続き、区切りや親子を見ない。そのため、選んだ行の子孫でない (sub) 行も『すぐ下に続く起動された行』として block に入る。次の区切りの空行、見出し、トップレベルの (sub) 行や、同じ区切りの後ろに並ぶ別の組のトップレベルの (sub) 行が該当する。

   Failure scenario: 区切り A の最後の行 X を選んでいる。区切り B の先頭に、起動元が一覧に出ていない (sub) 行が 5 行ある。cursorBlock は B の空行、見出し、(sub) 5 行まで延び、窓はこれを見せるためにスクロールする。X とは関係のない行が『一緒に見える塊』として扱われ、X の上の文脈が不必要に削られる。

7. `src/screen/screen.ts:201`: 選べるかどうかの判定を、画面側では表示用の `r.marker !== 'sub'` から推し量り、モデル側では selectableOrder(n.spawned)で決めている。同じ規則の出どころが 2 つある。

   Failure scenario: marker の付け方(app.ts:447)と selectableOrder の規則のどちらかだけが変わると、`<通し番号>/<総数>` と ↑↓ で数える行の集合がずれる。たとえば `11/11` と出ているのに、↓ で止まる行の数が違う。Screen に選べる行の印(ScreenRow.selectable など)を渡し、画面はそれを使うほうがよい。

8. `README.md:45`: README に『Both can be selected but not attached』と書かれたまま残っている。(sub) 行は選べなくなったので、利用者向けの説明が実装と食い違う。

   Failure scenario: /Users/masahirompp/.../whatnext/CLAUDE.md の規約『永続層: `docs/`(…)、`README.md`、… — 厳格に維持する』に反する。README を読んだ利用者は ↑↓ で (sub) 行を選べると思うが、実際には飛ばされる。

9. `src/model/cursor.ts:6`: selectableOrder は order の各 sid について、isSpawned で全区切りの全ノードを走査するので O(n²) になる。↑↓ のキー入力ごとと、更新ごとに呼ばれる。

   Failure scenario: 行が数十行でも、キー入力のたびに全ノードを n 回なめる。`l.groups.flatMap(g => g.nodes).filter(n => !n.spawned).map(n => n.sid)` と書けば、order と同じ順で O(n) になり、isSpawned の重複も消える。Layout に spawned の Set を持たせる手もある。

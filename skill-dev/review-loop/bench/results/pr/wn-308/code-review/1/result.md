I読んだのは `main...HEAD`(コミット 71d31d0、PR「作業台のステータス行に、分割とウィンドウのキーを出す」)です。ほかのセッションの作業台に入ったときの壊れ方、つまりはっきりした正しさのバグは見つかりませんでした。

- `%%` の扱いは、文字列が引数で渡り `sourceConfig` の引用を通らないので問題ありません。
- `^Q%`、`^Q"`、`^Qc` は、サーバを `-f /dev/null` で作るので tmux の既定のまま残ります。whatnext の bare キー(`v`、`e`)とも重なりません。
- 作業台では prefix の `C-q` が、root 表の `bind -n C-q` より先に効きます。
- e2e は 80 桁で、期待する行は収まります。

以下の指摘は、主に設計の深さ、テストの持ち越し、docs の食い違いです。検証は回していません。

8 findings, most severe first:

1. `lib/tmux/tmux.ts:340`: 利用者に見せるキーの説明の文言を、昇格済みモジュール lib/tmux の中に直に書いている。claude の画面のキーの説明(@wn_keys)は使う側(src/ops/keys.ts)から keysHelp として渡しているのに、作業台だけ形がそろっていない。

   Failure scenario: キーの文言や並び(例えば ^Q% を外す、別のキーを足す)を変えるたびに、厳格に維持する lib/ と docs/lib/tmux.md の契約を書き換えることになる。docs/lib/tmux.md の『この部品は「何をするか」の仕組みだけを持ち…使う側が持つ』『どのキーを置くかは使う側が決める』という方針に反し、DESIGN.md『キーの説明を1か所の表から作る』からも外れる。workbenchOptions(session, name, keysHelp) のように使う側から文言を渡せば、lib は仕組みだけを持つ形に戻る。

2. `lib/tmux/tmux.test.ts:20`: 昇格済みモジュールの見た目の変更(%% のエスケープを含む status-format)を、lib のテストではなく、使い捨て層の e2e(test/e2e/workbench.test.ts)だけで確かめている。

   Failure scenario: cycle-end で test/e2e が消えたあと、誰かが status-format の %% を % に直すと、作業台に『^Q split │』と出るようになる。それでも lib/tmux/tmux.test.ts は通ってしまい、壊れたことに気づけない。CLAUDE.md の『昇格…テストを持ち越し』の趣旨では、lib 側に workbenchOptions の書式(%% と GUIDE のときに出さないこと)を確かめるテストが要る。

3. `lib/tmux/tmux.ts:321`: workbenchOptions を呼ぶのは作業台を作るときと起動時の GUIDE だけなので、すでにある sh-<id> のステータス行は古い書式のまま残る。

   Failure scenario: abnormalExit は動いているものがある作業台を残す。そのあとこの版で whatnext を起動し直すと、新しく作った作業台にはキーが出るが、残った作業台には出ない。同じ画面の中で作業台ごとに表示が食い違う。起動時に sh-* のセッションすべてへ workbenchOptions を当て直せば揃う。

4. `docs/PRODUCT.md:442`: docs が典型として示す配置(作業台の画面が34桁)では、ステータス行は『0:zsh*  · ^』で切れ、足したキーは1つも見えない。キーを足した目的が、その配置では果たせない。

   Failure scenario: 画面を半分に分けた狭い作業台では、セッション名と窓の一覧で幅を使い切り、^Q% が出ない。名前が長い、またはウィンドウが2つ以上あると、80桁でも ^Q% が押し出される。この PR が解こうとした『作業台の中を分けられると分からなかった』という問題が、まさに典型の配置で残る。

5. `docs/PRODUCT.md:442`: 画面の例(34桁の枠の最下行)の書き換えが、実際の描画から取ったものかどうか分からない。手で書き換えた疑いがある。

   Failure scenario: /…/whatnext/CLAUDE.md の『画面の例は手で書かず、実際の描画(描画の関数か、画面の通しのテストで取った画面)から作る』に触れうる。tmux はステータス行の左端を空けないので、実際の描画なら行頭の空白の扱いで1桁ずれうる(枠の内側の ' workbench:…' の先頭の空白)。利用者がこの例を見て合意すると、字下げの水準で違う絵のまま合意しうる。

6. `docs/DESIGN.md:230`: 作業台の画面のステータス行に tmux の既定のキーを出すことにしたのに、DESIGN.md は更新していない。『tmux は利用者から隠す』(206行)とも食い違ったままになっている。

   Failure scenario: /…/whatnext/CLAUDE.md は、どう実現するか(ステータス行の書式、tmux の既定のキーに頼ること)を DESIGN.md に書くとしている。次のサイクルで DESIGN.md だけを読んで実装すると、『tmux を隠す』に従ってキーを出さない実装になりうる。また、どのキーの割り当てを前提にするか(既定の % " c が残っている前提)が docs に書かれていない。

7. `docs/lib/tmux.md:31`: 契約では、キーを続ける振る舞いを createWorkbench の説明に書いている。実際に status-format を置くのは workbenchOptions で、GUIDE にも呼ばれる(GUIDE には出さない)。

   Failure scenario: 使う側が契約だけを読んで、案内のセッションや既存のセッションに workbenchOptions を当てると、キーが出るかどうかが分からない。session === GUIDE で出し分けている事実は契約に書かれていない。

8. `test/e2e/workbench.test.ts:117`: e2e が確かめるのは、ウィンドウが1つのときにキーが続くことだけで、仕様の残り2点を確かめていない。

   Failure scenario: 確かめていないのは、ウィンドウが2つのときに窓の一覧のあとに続くこと(PRODUCT.md『ウィンドウを増やすほどキーは右へ押し出される』)と、案内のセッションにキーを出さないこと(25行では workbench: alpha の有無しか見ていない)の2点。GUIDE の分岐を消したり、W: のループの末尾の空白を変えたりしても、テストは通ってしまう。

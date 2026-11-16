8 findings, most severe first:

1. `src/cli/list.ts:68`: 新しいステータス行の書式は workbenchOptions を呼んだときにしか入らない。一覧の起動時に呼び直しているのは案内のセッション(GUIDE)だけで、すでにある作業台 sh-<id> には新しい書式が入らない。

   Failure scenario: 異常終了(abnormalExit)で、コマンドが動いている作業台だけが残る。その tmux サーバに新しい版の whatnext をつなぐと、sourceConfig と GUIDE の書式は入り直す。一方、生き残った sh-<id> の status-format[0] は古い版のままなので、その作業台の画面には `^Q% split │ ...` が出ない。シナリオ49と食い違う。

2. `lib/tmux/tmux.ts:340`: 長いステータス行を `#{=/N/…:}` で切っていない。作業台の画面が狭いと、キーの途中で生のまま切れる(図の `· ^` がそれ)。

   Failure scenario: 幅34の作業台の画面では `workbench: fix-login  0:zsh*  · ^` と出て、意味のない `· ^` が残る。claude の画面のステータス行は `#{=/#{e|-:#{client_width},1}/…:...}` で `…` を付けて切っている。こちらも同じ仕組みを使えば、欠けたことが分かる形で切れる(SKILL.md の記録どおり `client_width-1` にすれば、先頭の1文字も欠けない)。

3. `test/e2e/workbench.test.ts:117`: 昇格済みモジュール lib/tmux の振る舞い(status-format では `%` を `%%` と書く)を確かめているのが、使い捨て層の e2e テストだけになっている。lib/tmux/tmux.test.ts には workbenchOptions の書式のテストがない。

   Failure scenario: CLAUDE.md(リポジトリ直下)は「仕様が収束したモジュールは…`lib/` に昇格し、以後は永続層として厳格に維持する(テストを持ち越し…)」と定めている。cycle-end で test/e2e を消すと、`%` を `%%` に直す書き方の回帰を捕まえるテストがなくなる。誰かが `%%` を `%` に戻すと、`^Q split` になっても気づけない。

4. `docs/PRODUCT.md:442`: 作業台の図のステータス行(`workbench: fix-login  0:zsh*  · ^│`)を手で書き換えたように見える。実際の描画から取ったものとは確かめられない。

   Failure scenario: CLAUDE.md(リポジトリ直下)の「画面の例は手で書かず、実際の描画(描画の関数か、画面の通しのテストで取った画面)から作る」に反するおそれがある。手で書くと、先頭の空白や切れる位置(tmux は表示幅で切り、全角や曖昧幅の文字の扱いも絡む)が実機とずれうる。利用者がそれを見て合意すると、違う絵のまま決まる。

5. `docs/PRODUCT.md:557`: 同じものを「窓の一覧」と「ウィンドウの一覧」の2つの言葉で呼んでいる。直前の行(552)と、シナリオ49は「ウィンドウの一覧」である。

   Failure scenario: PRODUCT.md 557行目と docs/lib/tmux.md 31行目は「窓の一覧」、同じ節の552行目と761行目は「ウィンドウの一覧」になっている。永続層の docs で用語が揃わず、読み手が別のものを指すと受け取りうる。CONTEXT.md の用語管理とも合わない。

6. `lib/tmux/tmux.ts:340`: ステータス行に、東アジアの曖昧幅の文字(`│` U+2502、`─` U+2500、`·` U+00B7)を新しく足した。tmux は幅1として数えるが、曖昧幅を全角で描く端末では幅2になる。

   Failure scenario: 曖昧幅を2で描く設定の端末(日本語環境で多い)では、ステータス行が tmux の計算より3桁以上長くなる。右端がはみ出して折り返したり、描画が崩れたりしうる。`split │` や `split ─` は ASCII の `split |` や `split -` でも意味が通る。

7. `docs/lib/tmux.md:31`: 契約 docs に、workbenchOptions の振る舞いの分かれ目が書かれていない。案内のセッション(GUIDE)ではキーを出さず名前だけを出すことが抜けている。そのうえ、キーの記述を createWorkbench の注記に置いている。

   Failure scenario: 実装セッションは契約 docs 経由で lib を使い、中身を読まない決まりである。src/cli/list.ts は `workbenchOptions(GUIDE, '')` を直に呼んでいるが、GUIDE に渡したときにキーが出ないことは契約から読み取れない。次サイクルで、案内にもキーを出すつもりで呼び方を間違えうる。

8. `lib/tmux/tmux.ts:338`: 2つの書式で、先頭の `'#[align=left,fg=colour8]workbench: #{@wn_name}'` を重ねて書いている。

   Failure scenario: 色や見出しを変えるとき、片方だけを直しやすく、案内と作業台で見た目がずれる。共通の先頭を定数にして、作業台のときだけ窓の一覧とキーを足す形にすれば1か所で済む。

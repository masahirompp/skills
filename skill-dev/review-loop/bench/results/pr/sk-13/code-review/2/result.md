PR #1(`review-loop-perspective-options`、`main...HEAD`)をレビューしました。既存テストはすべて通ります(`python3 skill-dev/review-loop/test.py`)。指摘は9件です。最も重いのは1件目で、SKILL.md に載せたコマンド例そのものが終了コード2で止まります。

9 findings, most severe first:

1. `skills/review-loop/SKILL.md:50`: SKILL.md のコマンド例が `--instruct 'security-review=…'` と、security-review を含まない `--perspective` 2つを組み合わせており、review_config がこれを拒否するので、例のとおりに実行すると必ず終了コード2で止まる。

   Failure scenario: 親エージェントが例をそのまま写して `iterate <wt> --instruct 'security-review=…' --perspective 'code-review high {pr}' --perspective 'mattpocock-skills:code-review PR #{pr}'` を実行すると、review_config が「--instruct のスキル security-review が観点にない」で Precondition を出して止まる。test.py もこの組み合わせを「--perspective で外した観点への --instruct」として終了コード2になると確かめている。

2. `skills/review-loop/scripts/review_loop.py:397`: review_config は `s.strip()` を空かどうかの判定にしか使わず、値そのものは整えない。そのため、先頭に空白のある --perspective は事前確認を通ったうえで、レビュー役に `/ code-review …` という壊れたプロンプトを渡す。

   Failure scenario: `--perspective ' code-review high {pr}'` と渡すと、skill_name は split()[0] で `code-review` を返すので事前確認は通る。ところが run_reviews の prompt は `"/" + expand(spec)` なので `/ code-review high 7` になり、スラッシュコマンドとして解釈されない。レビュー役は無関係な応答を返し、反復を1回無駄にする(判定役は観点の欠落と扱う)。

3. `skills/review-loop/scripts/review_loop.py:963`: 既定と違うかどうかをスキル名の並びだけで比べているので、引数を変えた観点は記録されず、並べ替えただけの既定の観点は既定と違うものとして記録される。

   Failure scenario: `--perspective 'code-review low {pr}' --perspective security-review --perspective 'mattpocock-skills:code-review PR #{pr}'` で深さを下げて回すと、名前が既定と一致するので attempt に perspectives が残らず、状態コメントの表では既定の high で判定されたように見える。逆に既定の3つを順番だけ変えて渡すと、既定と同じ観点なのに観点の欄が表示される。比べるなら `specs` があるかどうか、または spec の文字列そのもので比べる。

4. `skills/review-loop/scripts/review_loop.py:962`: --instruct で範囲を絞った試行が、状態にも状態コメントにもまったく残らないため、completed になった反復が範囲を狭めたレビューだったかを後から確かめられない。

   Failure scenario: `--instruct 'code-review=テストは見ない'` を付けて completed になった反復は、表では既定の完全なレビューと区別がつかない。SKILL.md が求める「最後の判定でレビューされなかった範囲」の報告は親の記憶だけが頼りになり、コンテキストの圧縮などで失われると、範囲を絞ったことが報告から消える。

5. `skills/review-loop/SKILL.md:57`: オプションを反復ごとに付け直す仕組みは、親が毎回覚えていることに頼っている。付け忘れても何も警告されず既定に戻るので、仕組みの側(状態への保存か、直前の試行との違いの警告)で防ぐべきところを文書の注意書きで補っている。

   Failure scenario: 反復2で親が `--perspective` を付け忘れると、利用者が外した観点(たとえば読めない `.env` で止まる security-review)がそのまま戻り、同じ permission_denied がまた起きる。逆に `--instruct` を付け忘れると、絞ったはずの範囲が黙って戻る。スクリプトは直前の試行の観点を状態に持っているのに、それと比べた警告すら出さない。

6. `skills/review-loop/scripts/review_loop.py:846`: judge-input.md には追加の指示の区画を足したが、JUDGE_PROMPT にはその区画の扱いが書かれていない。既定の観点を外したときに「外した観点は欠落ではない」と判定役に伝える情報もない。

   Failure scenario: JUDGE_PROMPT は「観点の出力がレビューになっていない場合は観点の欠落」とだけ指示している。指示の区画をどう読むかが判定役の解釈任せなので、指示で外した範囲を見ていないレビューを、判定役が「観点の欠落」や漏れの指摘として載せうる。そうなると、親が直さなくてよい項目で反復を重ねる。

7. `skills/review-loop/scripts/review_loop.py:548`: valid_state は perspectives の要素が str かどうかしか見ないので、perspectives が文字列でも通ってしまい、render が1文字ずつ区切って表示する。

   Failure scenario: 状態コメントの JSON が手で `"perspectives": "code-review"` に書き換えられると、文字列の各文字は str なので検証を通る。render は `', '.join(...)` で「観点 c, o, d, e, -, …」と表示し、状態が読めない場合として止まるべきところで止まらない。`isinstance(a.get("perspectives", []), list)` も確かめる必要がある。

8. `skill-dev/review-loop/test.py:570`: 「--instruct はほかの観点には渡さない」のテストは、該当するレビューの呼び出しがなくても既定値 "x" で成功してしまい、何も確かめていない。

   Failure scenario: mattpocock-skills:code-review の呼び出しが起動されない、または name の記録が変わると、by_name.get が "x" を返し、`"削除したファイル" not in "x"` が真になってテストは成功する。この組み合わせで指示が漏れていても検出できない。既定値なしで、キーがあることを先に確かめるべき。

9. `skills/review-loop/scripts/review_loop.py:409`: 観点のスキル名の一覧を、--instruct のループの中で毎回作り直しているうえ、iterate でも同じ一覧をもう一度作っている。

   Failure scenario: `[skill_name(s) for s in perspectives]` を review_config のループの各回、エラーメッセージ、iterate の 962 行で別々に作っている。review_config で名前の一覧を一度だけ作って返せば、同じ式を3か所に書かずに済み、比べ方を変えるときの直し漏れ(3件目の指摘を参照)も防げる。

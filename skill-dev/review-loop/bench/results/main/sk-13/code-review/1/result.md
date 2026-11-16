9 findings, most severe first:

1. `skills/review-loop/scripts/review_loop.py:379`: --perspective の値の前後の空白を除いていない。skill_name は split()[0] で空白を飛ばして事前確認を通すが、expand はそのまま `/` を前に付けるので、プロンプトが `/ code-review high 7` になる。

   Failure scenario: `--perspective ' code-review high {pr}'`(引用の中に先頭の空白が入った)で起動する → review_config と preflight は skill_name='code-review' で通る → 子に渡るプロンプトは '/ code-review high 7' でスラッシュコマンドにならない → レビューでない出力が「観点の欠落」として扱われるか、1回分の試行と費用が無駄になる。review_config で spec を strip して返すべき。

2. `skills/review-loop/scripts/review_loop.py:743`: --instruct は親の claude の --append-system-prompt にだけ足すので、観点スキルがサブエージェントに作業を任せると、サブエージェントには届かない。そのため SKILL.md が勧める「権限の拒否への対処」として効かない。

   Failure scenario: mattpocock-skills:code-review(内部で sub-agent を並列に起動する)に `--instruct 'mattpocock-skills:code-review=削除した .env は読まない'` を渡す → sub-agent のシステムプロンプトに指示が入らず、.env を読みに行く → 同じ permission_denied で再び失敗し、連続失敗の数が進む。

3. `skills/review-loop/scripts/review_loop.py:798`: judge-input.md の先頭に「追加の指示」の区画を足したのに、JUDGE_PROMPT にはこの区画の意味も扱い方も書いていない。「観点ごとに区切ってある」とだけあるので、判定役が指示の区画をレビューの区画と取り違えたり、無視したりしうる。

   Failure scenario: `===== 観点 code-review に利用者が与えた追加の指示 =====` と `===== 観点: code-review =====` が似た見出しで並ぶ → 判定役は指示を観点の出力の一部と読むか、指示で外した範囲をほかの観点の指摘との競合として裁定に使う → SKILL.md の「指示で外した範囲を観点の欠落とは扱わない」がプロンプトで保証されていない。

4. `skills/review-loop/scripts/review_loop.py:962`: 状態に残すのが観点の名前の並びだけなので、--instruct で範囲を絞ったことも、引数を変えたこと(code-review の low など)も記録されない。逆に、同じ観点を順番だけ変えて渡すと「既定と違う」と記録される。

   Failure scenario: `--perspective 'code-review low {pr}' --perspective security-review --perspective 'mattpocock-skills:code-review PR #{pr}'` で深さを下げる、または --instruct でテストを見ないよう指示する → 表には何も載らず、既定どおり回したように見える。同じ3つを順番だけ変えて渡すと、内容は既定と同じなのに観点の名前が表に載る。

5. `skills/review-loop/scripts/review_loop.py:1073`: --perspective と --instruct は反復をまたいで覚えず、毎回付け直すことを親の記憶に頼っている。付け忘れると黙って既定に戻り、--instruct は状態にも残らないので後から気づけない(根本は、シリーズの設定を状態コメントに持たせていないこと)。

   Failure scenario: 反復1で --instruct を付けて permission_denied を避ける → 反復2で親が付け忘れる → 同じ拒否で再び失敗する。あるいは、外したはずの範囲の指摘が復活し、判定が行ったり来たりして見える。表からは原因を区別できない。run_id ごとに観点と指示を状態に保存し、次からはそれを既定にする設計にすれば防げる。

6. `skills/review-loop/scripts/review_loop.py:548`: valid_state は perspectives の要素が str かどうかしか確かめないので、手で編集されて文字列そのものになった perspectives を受け入れてしまい、render で1文字ずつ区切って描く。

   Failure scenario: 状態コメントの JSON で perspectives が "code-review"(リストでなく文字列)に書き換わる → `all(isinstance(n, str) for n in "code-review")` が True になる → 表に「観点 c, o, d, e, -, ...」と出る。isinstance(list) も確かめるべき。

7. `skills/review-loop/scripts/review_loop.py:412`: --perspective の引数の {pr} は置き換えるのに、--instruct の指示の中の {pr} は置き換えないので、レビュー役には `{pr}` がそのまま渡る。

   Failure scenario: `--instruct 'code-review=PR #{pr} で削除したファイルは見ない'` → システムプロンプトに文字どおりの 'PR #{pr}' が入る → レビュー役が PR を特定できないか、指示を取り違える。

8. `skill-dev/review-loop/test.py:558`: 551行目で --new-run を実行した直後に、新しい区画の先頭でもう一度 --new-run を実行している。重複していて、テストに1反復分の時間がよけいにかかる。

   Failure scenario: 551行目の `run(wt, "--new-run")` の直後に、558行目の `run(wt, "--new-run")` が続く → 結果を使わない偽の反復が1回増え、テストの実行時間が延びる。読む人には、ここだけ2回必要な理由があるように見える。

9. `skills/review-loop/scripts/review_loop.py:409`: 観点の名前のリスト `[skill_name(s) for s in perspectives]` を、--instruct 1件ごとの照合と、エラーメッセージと、iterate の 962〜963行目とで作り直している。

   Failure scenario: 同じ値を3か所で別々に作るので、名前の比較の規則(strip や safe_name)を変えるときに、1か所だけ直し漏れるおそれがある。review_config で names を1回だけ作り、既定と同じかどうかも合わせて返すほうが簡単になる。

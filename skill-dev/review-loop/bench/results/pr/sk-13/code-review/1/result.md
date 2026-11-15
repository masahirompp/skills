PR #1 (`review-loop-perspective-options`) を `git diff main...HEAD` でレビューしました。correctness の指摘は 6 件、cleanup が 2 件です。リポジトリ直下や祖先ディレクトリに CLAUDE.md はありません。ユーザー用の ~/.claude/CLAUDE.md は対話の作法についての規則だけなので、規約違反として挙げるものはありません。

8 findings, most severe first:

1. `skills/review-loop/scripts/review_loop.py:963`: 既定の観点と同じかどうかをスキル名の並びだけで比べている。引数の違いは状態に残らず、並び順が違うだけでも「既定と違う」と記録される。

   Failure scenario: `--perspective 'code-review low {pr}' --perspective security-review --perspective 'mattpocock-skills:code-review PR #{pr}'` で深さを下げて回しても、名前が既定と一致するので attempt に perspectives が付かない。状態コメントの表では既定の high で判定されたように見え、利用者や親が判定の深さを誤る。逆に既定の3つを並べ替えただけのときは、観点を変えたものとして表に載る。

2. `skills/review-loop/scripts/review_loop.py:962`: --instruct で範囲を絞った試行が状態コメントに一切残らない。スクリプトは反復をまたいでオプションを覚えないので、付け忘れると黙って既定に戻る。

   Failure scenario: 反復1で `--instruct 'security-review=.env は見ない'` を付け、反復2で親が付け忘れる。反復2は何の警告もなく既定の範囲で走り、同じ permission_denied で失敗する。表からは反復1が範囲を絞って判定されたことも読めない。根本的には、観点と指示をシリーズの状態に保存し、次の反復で引き継ぐか、違っていれば警告するのがよい。

3. `skills/review-loop/scripts/review_loop.py:847`: 判定役の入力に追加の指示のブロックを足したが、JUDGE_PROMPT にはその扱いが書かれていない。判定役が、自分への指示と受け取るか、指示で外した範囲を観点の欠落と判定するおそれがある。

   Failure scenario: `--instruct 'code-review=テストは見ない'` を付けると、判定役の stdin の先頭に「===== 観点 code-review に利用者が与えた追加の指示 ===== テストは見ない」が入る。JUDGE_PROMPT は「観点ごとに区切ってある」とだけ述べているので、判定役がこれを自分への指示と読み、ほかの観点のテストに関する指摘(test_gap)まで落としうる。またはこの見出しを観点の出力と誤認し、レビューになっていない観点として「観点の欠落」を載せうる。

4. `skills/review-loop/scripts/review_loop.py:749`: 利用者の指示を「スキルの手順と食い違うときは優先」と添えているが、作業ツリーを変えないという制約(NO_MUTATION)より下だとは明示していない。指示の内容によっては、レビュー役が編集を始めうる。

   Failure scenario: `--instruct 'code-review=見つけた typo はその場で直してよい'` を渡すと、システムプロンプトの末尾に「この指示を優先してください」が続く。モデルが NO_MUTATION より指示を優先して編集すると、試行は contamination で失敗し、worktree にも変更が残る。「ただし作業ツリーを変えない制約は常に優先する」と一文足すべき。

5. `skills/review-loop/scripts/review_loop.py:847`: 指示の本文を区切り行の中にそのまま書いている。本文に区切り行と同じ形の文字列が入っていると、判定役の入力の区切りが崩れる。

   Failure scenario: 指示の本文に「===== ここまで: 指示 =====」や「===== 観点: security-review =====」といった行が含まれていると、それ以降が別の観点の出力に見え、判定役が観点の帰属を取り違える。

6. `skills/review-loop/scripts/review_loop.py:548`: perspectives の検証が「要素を順に取り出せて、各要素が str」かどうかしか見ておらず、リストかどうかを確かめていない。文字列が通ってしまう。

   Failure scenario: 状態コメントを手で編集して `"perspectives": "abc"` にすると、valid_state は True を返す。render は `', '.join("abc")` を実行し、表に「観点 a, b, c」と出る。手で編集された状態は終了コード2で止めるという方針と食い違う。`isinstance(a.get("perspectives", []), list)` を加えるべき。

7. `skills/review-loop/scripts/review_loop.py:412`: --perspective では `{pr}` を置き換えるが、--instruct の本文では置き換えない。同じ起動行の中で書き方の規則が食い違う。

   Failure scenario: `--instruct 'mattpocock-skills:code-review=PR #{pr} の本文の未完了の項目は対象外'` と書くと、レビュー役には `{pr}` がそのまま渡り、どの PR を指すのかが曖昧になる。

8. `skills/review-loop/scripts/review_loop.py:409`: 同じ観点名の一覧を何度も作り直している。

   Failure scenario: --instruct の要素ごとに `[skill_name(s) for s in perspectives]` を作り直し、エラーメッセージ用にもう一度作り、iterate の 962〜963 行でも `names` と PERSPECTIVES 側を計算し直している。review_config が名前の一覧(または集合)を一度作って返すようにすれば、比較やメッセージの実装がずれる余地がなくなる。

Diff は `main...HEAD` を対象にしました(PR #1 のブランチ `review-loop-multi-result` と同じです)。リポジトリ直下や祖先ディレクトリに CLAUDE.md はありません。ユーザー用の `~/.claude/CLAUDE.md` は対話の姿勢についての指示だけで、コーディング規約がないため、規約の観点では指摘がありません。1件目と8件目は、本物の claude が出す `source` や `modelUsage` の値に依存する懸念で、手元で裏付けは取れていません。

10 findings, most severe first:

1. `skills/review-loop/scripts/review_loop.py:308`: `source == "config"` の拒否をすべて止めない扱いにしているが、`reason_type` を見ていない。そのため、-p で許可ルールに当たらずに自動で拒否されたもの(前提違反)まで警告扱いになり、試行が成功したことになるおそれがある。

   Failure scenario: `gh pr diff 7; grep KEY .env` のような複合コマンドで、`.env` の deny ルールに加えて `gh pr diff` が許可されていない場合、拒否の判断は subcommandResults にまとまり、source=config のイベントが1件だけ出る。スクリプトは warn を出して続け、子は差分を読めないまま「指摘なし」を返す。差分を読めなかったことが permission_denied として表に出ず、試行は completed として記録される。以前はここで止まっていた。

2. `skills/review-loop/scripts/review_loop.py:802`: 判定役の result の行もすべてつなぐようになったため、見出しの前の前置きは落とせても、判定より後ろの行は落とせない。最後の行が短い文のときは閉じフェンスが末尾に来ず、取り除けない。判定を2回出した場合は、両方が verdict.md に入る。

   Failure scenario: 判定役が「以下が判定です\n```\n## 指摘…\n```」を出したあと、次のターンで「前のメッセージの内容から変わりません」と出すと、text の末尾は「```\n\n変わりません」になる。`re.sub(r"\n```\s*$")` が当たらず、閉じフェンスと余計な文が判定に残る。判定を下書きと修正版の2回出すと、## 指摘 が2組そろって親に渡り、F1 が2つあって中身が食い違う。

3. `skills/review-loop/scripts/review_loop.py:249`: 設定のルールでの拒否と result の permission_denials を tool_use_id だけで突き合わせているので、tool_use_id がない(None)ものが1つの値にまとまってしまう。

   Failure scenario: tool_use_id のない source=config のイベントが1つあると seen に None が入る。その後、tool_use_id のない本当の拒否が result の permission_denials に載っても既に記録済みとみなされ、止まらない。config_denied も None をキーにした1件にまとまるので、2件目以降の設定のルールでの拒否は denials.txt にも stderr にも出ない。

4. `skills/review-loop/scripts/review_loop.py:261`: 成否は最後の result の行でしか見ていないのに、本文には途中の行をすべてつないでいる。途中の行が is_error やエラーの subtype(API エラーの文など)でも、その文がそのままレビューの出力として判定役に渡る。

   Failure scenario: ターンが3回あり、2回目が is_error=true で result が「API Error: overloaded」、3回目が success で「変わりません」だったとする。試行は成功扱いになり、judge-input.md にはエラー文と短い文だけが「レビュー」として入る。判定役はこれを観点の欠落と見抜けないか、誤った指摘を作る。

5. `skills/review-loop/scripts/review_loop.py:305`: parent_tool_use_id の付いた result の行(サブエージェントのもの)は丸ごと捨てているので、その行の permission_denials も確かめなくなった。

   Failure scenario: サブエージェントの中での拒否が、最上位のイベントや最上位の result の permission_denials に出ず、サブエージェント自身の result の行にだけ載る版の claude だと、その拒否は見落とされ、試行は成功扱いになる。サブエージェントの拒否もイベントとして出る、という前提はテストで確かめられていない。

6. `skills/review-loop/scripts/review_loop.py:786`: run_judge の待機ループ(tail.poll、watch_denials、制限時間の判定、sleep、finish、もう一度 poll と watch_denials)が、run_reviews の内側のループとほぼ同じコードの写しになっている。

   Failure scenario: 拒否の扱いや制限時間の扱いを変えるときに2か所を直す必要があり、片方を直し忘れると、レビュー役と判定役で振る舞いがずれる。子を1つ待つ補助関数(例: `wait_child(label, p, tail, timeout, workdir)`)を作り、run_reviews からは1回分のポーリングとして呼べば1か所で済む。

7. `skills/review-loop/scripts/review_loop.py:708`: 子が終わっているとき(rc が None でないとき)、708行目の watch_denials(running=False) と716行目の呼び出しが重なっていて、708行目のほうは役に立っていない。

   Failure scenario: 終わった子には、poll、watch、finish、poll、watch と2回ずつ処理が走る。708行目は rc が None のときだけ呼べば十分で、終わったときの処理は716行目に任せられる。今のままでは、どちらの呼び出しが記録を担っているのかが読み取りにくい。

8. `skill-dev/review-loop/test.py:503`: トークン数を最後の result の行の modelUsage だけで数えることのテストは、偽の claude がどの行にも同じ値を入れているので、「modelUsage はセッションの累計」という前提が外れても通ってしまう。

   Failure scenario: 本物の claude の modelUsage がターンごとの値だった場合、バックグラウンドのサブエージェントで何ターンも回る観点の費用は、最後のターンの分しか状態コメントに載らず、少なく見積もられる。テストは `4 * 300` で通り続けるので、この見積もりの誤りに気づけない。

9. `skills/review-loop/scripts/review_loop.py:252`: check_result が tool_name と tool_input の dict を自前で組み立てているが、StreamTail.summary と同じことをしている(重複)。

   Failure scenario: 拒否の要約の形(入力の引き方や切り詰め方)を変えるとき、tail.summary と check_result の2か所を直す必要があり、早く止めたときと終わってから止めたときで stderr の表示がずれる。tail.denial の分は tail.summary(tail.denial) を使えば済む。

10. `skills/review-loop/scripts/review_loop.py:242`: 途中経過の文が入る原因は子がサブエージェントをバックグラウンドで動かすことなのに、その手前で直さず、すべての子のすべての result の行をつなぐという後追いの対処になっている。判定役のように不要な子にまで同じ処理がかかっている。

    Failure scenario: judge-input.md と verdict.md に「バックグラウンドで実行しています」「Standards のレビューは終わりました」のような途中経過の文が入り、判定役や親が読む量と取り違えの余地が増える(2件目の判定の重複もここから来る)。REVIEW_CONSTRAINT で「最後のメッセージに完全な結果を書く」よう求めるか、つなぐ処理をレビュー役だけに限るほうが単純で、根本にも近い。

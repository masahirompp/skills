PR #1(review-loop-multi-result)のレビュー結果です。指摘は9件です。テストスイートはすべて通りましたが、指摘1と2の状況はテストで再現されていません。リポジトリに CLAUDE.md はなく、~/.claude/CLAUDE.md にもコードの規約はないため、規約違反の指摘はありません。

9 findings, most severe first:

1. `skills/review-loop/scripts/review_loop.py:803`: 判定役の result の行をすべてつないだあと、最初の見出しから末尾までを判定として切り出すため、判定より後の turn の result が判定に混ざる。

   Failure scenario: 判定役がバックグラウンドのサブエージェントを使い、途中の行に判定、最後の行に「前のメッセージの内容から変わりません」や判定の再掲を出す → verdict.md の「## 競合」節の後ろにその文が付く。再掲なら F1/C1 などの id が二重になり、親が直す範囲を誤る。前置きでフェンスを開いていた場合も、閉じフェンスが末尾でなくなり `\n```\s*$` が当たらず、フェンスが残る。テストの FAKE_JUDGE=multi は最後の行が空なので、この状況を確かめていない。

2. `skills/review-loop/scripts/review_loop.py:308`: `source == "config"` の拒否をすべて「止めない」側に分類するが、-p で許可ルールに当たらずに拒否された場合(SKILL.md の前提では失敗にすべきもの)も同じ source になるかどうかを確かめていない。

   Failure scenario: 許可ルールにない `gh pr diff` が -p で自動拒否され、そのイベントに source=config と reason_type=subcommandResults が付く → watch_denials は warn を出すだけで止めず、check_result も seen に入れて permission_denials を無視する → 差分を読めなかったレビューが成功として判定役に渡り、permission_denied の安全装置が効かない。fake では denylive に source がなく、この区別は検証されていない。

3. `skills/review-loop/scripts/review_loop.py:263`: child_error の詳細が、最後の result の行のエラー文ではなく、つないだテキストの先頭500文字になった。

   Failure scenario: 途中の turn で「バックグラウンドで実行しています」と長い本文が出たあと、最後の result が is_error=true(残高不足や max turns など)で終わる → stderr と failure.txt には途中の本文の先頭しか出ず、肝心のエラー文が切り捨てられて原因が分からない。従来は最後の行の result を出していた。判定役の no_output の詳細(799行目の `text[:500]`)も同じ。

4. `skills/review-loop/scripts/review_loop.py:309`: 設定のルールでの拒否を tool_use_id をキーにした dict に入れるので、tool_use_id のないイベントは1つのキーにまとまり、2件目以降が denials.txt にも stderr にも出ない。

   Failure scenario: サブエージェントの中の拒否などで tool_use_id のない config 拒否が2回起きる → 2件目は既存キー None の値を上書きするだけで、new_config_denials のスライスに入らない → 記録が漏れる。さらに seen に None が入るので、result の permission_denials のうち tool_use_id のない config 以外の拒否もすべて無視され、止めるべき試行が成功になる。

5. `skills/review-loop/scripts/review_loop.py:245`: check_result は result の permission_denials のうち、tool_use_id が config 拒否と一致するものを無条件に飛ばす。同じ id で config 以外の拒否もあった場合や、result 側の id の表記が違う場合を考えていない。

   Failure scenario: 1つの tool_use に対し、stream には config の拒否イベントだけが出て、result の permission_denials 側には別の理由の拒否が同じ id で入る → seen で飛ばされ、試行が成功扱いになる。拒否を見逃す側に倒れている。

6. `skills/review-loop/scripts/review_loop.py:708`: レビュー役の1つが拒否や timeout で raise すると、まだ poll していない他の子の config 拒否は denials.txt と stderr に残らない。

   Failure scenario: security-review に config 拒否が出たあと、同じループで先に code-review が permission_denied で raise する → security-review の tail は読まれず、拒否が記録されない。SKILL.md は「観点の欠落が出たら denials.txt を確かめる」としているが、失敗した試行の診断材料が欠ける。

7. `skills/review-loop/scripts/review_loop.py:786`: run_judge の監視ループ(poll → watch_denials → timeout → sleep → finish → 再 poll → watch_denials → check_result)が、run_reviews のループとほぼ同じ写しになっている。

   Failure scenario: 子1つを stream-json で見張る共通の関数(例: `wait_child(label, p, tail, timeout, workdir)`)に括れば、拒否の扱いや timeout の扱いを変えるときに直す場所が1か所で済む。今は片方だけ直して挙動がずれやすい。

8. `skills/review-loop/scripts/review_loop.py:716`: 子が終わった周回では watch_denials を2回呼んでいる(708行目の running=False と、716行目の再 poll 後)。1回目は冗長。

   Failure scenario: 終了を検知した周回では、708行目の呼び出しが config 拒否の記録だけをして何も止めず、直後の再 poll で同じ処理をもう一度する。708行目を `if rc is None:` の中に移し、running=True で呼べば同じ動きで単純になる。

9. `skills/review-loop/scripts/review_loop.py:237`: docstring に「modelUsage はセッションの累計で、どの行も同じ値になる」とあるが、累計なら行ごとに値は増えるので自己矛盾している(fake もすべての行に同じ値を出している)。

   Failure scenario: 後から読む人が「同じ値なのでどの行でもよい」と解釈し、最初の行で数えるように変えると、トークン数が過少に記録される。fake も同じ値を出すのでテストでは気づけない。「累計なので最後の行だけを使う(足すと重複する)」と書くべき。

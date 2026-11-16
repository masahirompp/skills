Review target `1` は、このブランチの PR(review-loop-multi-result、OPEN)です。`git diff main...HEAD` を対象にしました。変更は4ファイルで、`review_loop.py`、`SKILL.md`、`fakes/claude`、`test.py` です。

- **テスト**: `skill-dev/review-loop/test.py` を実行し、全て成功しました。
- **CLAUDE.md**: リポジトリ内にはありません。`~/.claude/CLAUDE.md` は応答の姿勢についての指示だけで、コードの規約はないため、Conventions の観点では指摘なしです。
- **未確認の前提**: 3件目(`source == "config"` が何を表すか)と6件目(`modelUsage` が累計か)は、本物の claude CLI の挙動で決まります。偽の claude による今回のテストでは確かめられません。

9 findings, most severe first:

1. `skills/review-loop/scripts/review_loop.py:242`: 空でない result の行を全てつなぐため、子が後のターンで出し直したり取り下げたりした古い本文も、判定役への入力と判定に残る。

   Failure scenario: 観点スキルが、ターン1で暫定の指摘 F1〜F3 を出す。バックグラウンドのサブエージェントの完了後、ターン2で『F2 は誤検出だったので取り下げる。最終結果: F1, F3』と出し直す。この場合、judge-input.md には両方が入り、判定役は取り下げられた F2 を生きた指摘として扱う。判定役自身が複数ターンで判定を出し直したときは、verdict に『## 指摘』が2組入る。F1 などの id が重複し、親が直す範囲を誤る。

2. `skills/review-loop/scripts/review_loop.py:803`: 判定役の最後の行の後に短い result の行が続くと、その文が verdict の末尾に混ざり、閉じフェンスを落とす処理も効かなくなる。

   Failure scenario: 判定役の results が ['以下が判定です\n```markdown\n## 指摘\n...\n## 競合\nなし\n```', '前のメッセージから変わりません'] のとき、text の末尾は '```\n\n前のメッセージから変わりません' になる。re.sub(r"\n```\s*$") は一致しない。verdict.md と stdout には、閉じフェンスと無関係な文が『## 競合』の節の中に残る。docstring が想定する『最後の行が短い文』の場面が、判定役ではそのまま壊れる。

3. `skills/review-loop/scripts/review_loop.py:308`: source == 'config' だけで『止めない拒否』と見なしているが、許可ルールに当たらず -p で自動的に拒否された呼び出し(reason_type subcommandResults の複合コマンドなど)も source config で来るなら、前提の『許可されていない呼び出しは試行の失敗』が黙って崩れる。

   Failure scenario: `gh pr diff 7 && gh api ...` の後半が allow ルールにないとき、ルール評価の結果として source=config、reason_type=subcommandResults の拒否が出る。この場合、試行は completed になる。観点スキルは diff を読めないまま不完全なレビューを返し、記録は warn の行と denials.txt だけに残る。SKILL.md の前提(拒否なら試行は失敗)と食い違う。

4. `skills/review-loop/scripts/review_loop.py:336`: 設定のルールでの拒否は stderr と denials.txt に残るだけで、判定役には伝わらない。そのため SKILL.md が頼りにする『観点の欠落』が出ず、欠けたレビューが完全なものとして通る。

   Failure scenario: security-review が `cat .env; cat config/secrets.yml` を拒否され、残りだけでレビューして『指摘なし』と返す。判定役はこの拒否を知らないので『観点の欠落』を出さない。SKILL.md の手順は『観点の欠落が出たときに denials.txt を確かめる』なので、親は denials.txt を見ずに収束と判断する。

5. `skills/review-loop/scripts/review_loop.py:249`: config_denied を tool_use_id で引くため、tool_use_id のない拒否のイベントが1つあると seen に None が入る。その結果、tool_use_id のない result 側の拒否(設定以外のものも)が全て見逃される。

   Failure scenario: source=config で tool_use_id のないイベントが出ると、config_denied[None] になる。同じ子の result の permission_denials に、tool_use_id のない別の拒否(許可ルールがないなど)があっても、`d.get('tool_use_id') not in seen` が偽になって飛ばされ、permission_denied にならない。tool_use_id のないイベントが複数あると、dict で上書きされて denials.txt にも1件しか残らない。

6. `skills/review-loop/scripts/review_loop.py:237`: 『modelUsage はセッションの累計で、どの行も同じ値になる』は自己矛盾している(累計なら後の行ほど大きい)。偽の claude はどの行も同じ値を返すので、累計かターンごとかをテストで見分けられない。

   Failure scenario: 本物の claude が result の行ごとにそのターン分の modelUsage を返す場合、最後の行だけを足すと、本文を出したターンまでのトークンが状態コメントの集計から抜ける。test.py の 4*300 の確認は、偽の claude の値が同一なので通ってしまう。

7. `skills/review-loop/scripts/review_loop.py:708`: 子が終わった周回でも watch_denials が2回呼ばれる(708行目と716行目)。1回目は直後の tail.poll() で増える行を見ないので不要。

   Failure scenario: rc が None でない周回では、708行目の呼び出しは記録だけで、716行目がその直後に同じことをする。周回ごとの処理が読みにくくなり、どちらを直すべきかを誤りやすい。708行目は `if rc is None:` の中に移せば足りる。

8. `skills/review-loop/scripts/review_loop.py:252`: check_result で、拒否のイベントから {tool_name, tool_input} を組み立てている部分が、StreamTail.summary の中身(318〜319行目)と重複している。

   Failure scenario: 拒否の要約の形(入力の引き方など)を変えるとき、2か所を揃える必要があり、片方だけ直すと stderr と状態の詳細が食い違う。StreamTail に denial_entry(d) を持たせて両方から使えば1か所で済む。

9. `skills/review-loop/scripts/review_loop.py:786`: run_judge に、run_reviews と同じ『poll → tail.poll → watch_denials → 制限時間 → finish → 最後の poll → check_result』の待ち方を書き写している。

   Failure scenario: 最後の行の読み残しの防止や、拒否の扱いを片方だけ直すと、レビュー役と判定役で挙動が分かれる。1つの子を待つ共通の関数(例: wait_child(label, p, tail, timeout, ...))にまとめれば重複がなくなる。

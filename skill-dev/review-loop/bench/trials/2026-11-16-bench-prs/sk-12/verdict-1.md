## 指摘

### F1: 判定役の result の行をすべてつなぐため、後ろの短い文や下書きの判定が verdict.md と標準出力に混ざり、閉じフェンスも落とせない
- 観点: code-review, code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:802
- 分類: defect
- 影響: 中。verdict.md と標準出力(L973 の `print(verdict)`)に、判定と関係のない文が混ざる。判定役が下書きと修正版の両方を `result` の行に出すと F1 などが2組並び、親はどちらが正しい判定か分からず、直す範囲を誤る。
- 起きやすさ: 特定の操作の組み合わせ。判定役がコードを確かめるためにサブエージェントをバックグラウンドで使う → 1ターン目に判定(前置きとフェンス付きのこともある)を出す → 2ターン目に修正版か「変わりません」のような短い文を出す。
- 再指摘: なし
- 根拠: L795 の `check_result` は、空でない最上位の `result` の行をすべて `\n\n` でつないで返す(L263 付近)。L802〜805 は、最初の見出しより後ろをすべて判定として扱い、`re.sub(r"\n```\s*$", ...)` で末尾の閉じフェンスを落とす。後ろに別の行の文が付くとフェンスが末尾に来ないので、この正規表現は効かない。test.py の `FAKE_JUDGE=multi` は「前置き、判定、空」の形しか試していない(fakes/claude:92)ので、この問題は検出できない。判定役については、レビュー役と違って「途中経過が混ざっても、欠けるよりよい」という前提が成り立たない。出力の形を決めているのは判定役だからである。
- 範囲: 差分の内。PR の前の判定役は `--output-format json` の1つの `result` だけを使っていた。
- 再現: test.py と同じハーネス(一時ディレクトリにある偽の claude)で、fakes/claude に `FAKE_JUDGE=multitrail` を足す。この判定役は `result("以下が判定です\n```markdown\n## 指摘\nなし\n\n## 競合\nなし\n```")` と `result("前のメッセージの内容から変わりません")` を順に出す。`run(wt, FAKE_JUDGE="multitrail")` を実行したとき、期待するのは rc 0 で out が `## 指摘\nなし\n\n## 競合\nなし` で終わること。実際には、out の末尾に「```」と「前のメッセージの内容から変わりません」が残るはず。
- 横展開: 破っている規則は「標準出力は判定だけ」。ほかの経路として、L796 の見出しの確認がある。見出しが下書きにだけあっても通ってしまう。
- 競合: なし

### F2: child_error の詳細が、最後の行のエラー文ではなく、つないだテキストの先頭500文字になった
- 観点: code-review, code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:263
- 分類: defect
- 影響: 低。stderr と failure.txt に途中の行の本文や途中経過が出て、`is_error` の原因(API Error、max turns など)が切り捨てられる。stream の全体は `*.stdout.jsonl` に残るので、親が掘れば原因は分かる。
- 起きやすさ: 特定の操作の組み合わせ。複数ターンを使う観点スキル → 途中の行に500字を超える本文を出す → 最後の行が `is_error=true` で終わる。
- 再指摘: なし
- 根拠: 差分で `str(data.get('result', ''))[:500]` が `text[:500]` に変わっている。`data` は最後の行で、`text` はすべての行をつないだもの。
- 範囲: 差分の内
- 再現: fakes/claude にレビュー役の mode を足す。その mode は、`result("本文" * 400)` を出したあと `result("API Error: overloaded", subtype="error_during_execution", is_error=True)` を出して、exit 0 で終わる。`run(wt, FAKE_REVIEW_code_review=<mode>)` を実行したとき、期待するのは rc 1 で err に「API Error: overloaded」が含まれること。実際には含まれないはず。
- 横展開: 破っている規則は「失敗の詳細は失敗した行から取る」。判定役も同じ `check_result` を通るので、同じように起きる。ほかの経路はなし。
- 競合: なし

### F3: 設定のルールでの拒否を判定役に渡していないため、読めなかった観点の欠落を判定役が検出できない。許可ルールの漏れや、禁止した操作の拒否も素通りしうる
- 観点: code-review, code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:337
- 分類: defect
- 影響: 中。拒否のせいで diff を読めないまま「指摘なし」で終わった観点が、成功として判定される。PR 本文が軽減策に挙げている「判定役が観点の欠落として拾う」は、判定役が拒否を知らないので働かない。欠落が出ないので、SKILL.md の「観点の欠落が出たときは denials.txt を確かめる」も発動しない。子が禁じられた `git push` や Edit を試みて deny ルールで拒否された事実も、warn の行と denials.txt にしか残らない。
- 起きやすさ: 特定の操作の組み合わせ。観点スキルが `gh pr diff 7; grep -n KEY .env` を実行する → deny ルールでコマンドごと拒否される → 子が diff を取り直さずに終わる。もう1つの道は、許可ルールのないサブコマンドが拒否され、そのイベントにも `source: config` が付く場合である。これは本物の claude で確かめていない。
- 再指摘: なし。PR 本文の Merge Danger に既知のリスクとして書かれている(「許可ルールが無いための拒否も source: config になるなら止まらずに続く。判定役が観点の欠落として拾う流れと、親が denials.txt を確かめる手順に頼る」)。ただ、今回の指摘はその軽減策が成り立たないことを示しており、前提を覆す事情にあたる。
- 根拠: `run_judge`(L773〜777)が judge-input.md に書くのは `reviews` の本文だけで、denials.txt の中身は入れていない。`watch_denials` は、`source == "config"` の拒否であれば、ツール名や入力に関係なく warn を出すだけで続ける(L333〜337)。偽の claude の `deny("config")` は、`reason_type="subcommandResults"` の形しか再現していない(fakes/claude:48)。止めないという方針は PR の意図どおりである。それでも、judge-input.md に観点ごとの拒否を足すことは意図とぶつからないので、直す価値がある。
- 範囲: 差分の内。止めずに続ける挙動は、この PR で入った。
- 再現: `run(wt, FAKE_REVIEW_security_review="denyconfig")` を実行してから、`[c for c in calls() if c["kind"]=="judge"][-1]["stdin"]` に `grep -n KEY .env` か拒否の記載があるかを見る。期待するのは含まれること。実際には含まれないはず。
- 横展開: 破っている規則は「止めない拒否は、判定の材料に残す」。ほかの経路の候補として、判定役自身の config での拒否がある(L789)。これも記録だけで、判定の妥当性には反映されない。
- 競合: なし

### F4: tool_use_id のない拒否のイベントが None に集まり、上書きで報告から漏れる。さらに、止めるべき拒否を素通りさせる
- 観点: code-review, code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:309
- 分類: defect
- 影響: 中。`seen` に None が入ると、tool_use_id のない `permission_denials` がすべて「記録済み」として扱われる。出どころの分からない拒否(止める側に倒すはずのもの)があっても、試行が成功になる。また、tool_use_id のない config の拒否が2件以上あると、2件目以降は `config_denied[None]` を上書きして件数が増えない。このため、`new_config_denials` にも denials.txt にも残らない。
- 起きやすさ: まれな条件。本物の claude が tool_use_id のない `permission_denied` のイベントを出す場合に限る。出すかどうかは確かめられない。
- 再指摘: なし
- 根拠: L309 は `self.config_denied[msg.get("tool_use_id")] = msg`。L249 は `seen = set(tail.config_denied)`。L253 以降の判定は `d.get("tool_use_id") not in seen` で、None どうしは一致する。L323 の `list(self.config_denied.values())[self.reported:]` は辞書の長さに頼っているので、上書きされたものは報告されない。
- 範囲: 差分の内
- 再現: 一時ディレクトリに jsonl を書く。中身は `{"type":"system","subtype":"permission_denied","source":"config","tool_name":"Bash"}` を2行と、`{"type":"result","subtype":"success","result":"x","permission_denials":[{"tool_name":"Write","tool_input":{}}]}` を1行。`StreamTail(path).poll()` のあと、`new_config_denials()` を呼ぶ。期待は2件、実際は1件になるはず。続けて `check_result("t", 0, <一時ディレクトリ>/b, {"tokens": new_tokens()}, tail)` を呼ぶ。期待は `permission_denied` の例外で、実際は "x" が返るはず。
- 横展開: 破っている規則は「出どころが分からない拒否は止める側に倒す」。ほかの経路として、`tail.denial` の tool_use_id が None のときも、L251 で `seen.add(None)` が同じ効果を持つ。
- 競合: なし

### F5: 1つのレビュー役が失敗して例外が出ると、ほかの子の最後の poll 以降に出た config の拒否が denials.txt に残らない
- 観点: code-review
- 場所: skills/review-loop/scripts/review_loop.py:711
- 分類: defect
- 影響: 低。失敗を調べる材料が一部欠ける。stream の全体は `review-*.stdout.jsonl` に残っている。
- 起きやすさ: まれな条件(タイミング)。巡回の途中で、ある子の stream に config の拒否が書かれる → 同じ巡回で、先に回った子が timeout、permission_denied、child_error のどれかで raise する → 残りの子の tail は poll されないまま止められる。
- 再指摘: なし
- 根拠: L706〜718 のループでは、どこかで raise すると、それより後ろの子の `tail.poll()` と `watch_denials` が走らない。例外を処理する側で、ほかの tail を読み切る処理もない。
- 範囲: 差分の内。denials.txt はこの PR で入った。
- 再現: 実行では示せない。偽の claude で、「config の拒否を書いた直後に、別の子が終わる」状態を POLL_SECONDS の間隔の中に収める必要があり、狙って起こせない。fakes/claude で sleep を細かく合わせれば近づけることはできる。
- 横展開: 破っている規則は「止める前に、動いている子の拒否を読み切る」。ほかの経路として、`run_judge` のタイムアウト(L789〜790)がある。ここは raise の前に `tail.poll()` 済みなので、ほぼ問題ない。
- 競合: なし

### F6: 止める拒否のあと result を出さずに終わった子が、permission_denied ではなく child_error になる
- 観点: code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:714
- 分類: defect
- 影響: 低。失敗の種類が child_error になり、拒否されたコマンドが stderr に出ない。SKILL.md の「同じ権限の拒否で2回続けたら報告」の判断材料が欠ける。
- 起きやすさ: まれな条件。子の stream に source のない拒否が出る → ポーリングの間隔の中で、子が result を書かずに異常終了する。
- 再指摘: なし
- 根拠: `running=False` の `watch_denials` は raise しない。`check_result` は `if not tail.results` を先に見るので、child_error になる。
- 範囲: 差分の外。PR の前のコードでも、rc が確定した巡回では denial を見ず、`tail.result is None` が child_error になっていた。同じ操作の順で同じ結果になる。
- 再現: fakes/claude にレビュー役の mode を足す。その mode は `deny()` のあと `sys.exit(1)` で終わる。`run(wt, FAKE_REVIEW_code_review=<mode>)` を実行したとき、期待するのは err に `permission_denied` と `gh pr diff 7` が出ること。実際には `child_error` と「result の行がない」が出るはず。
- 横展開: 破っている規則は「拒否の分類を、ほかの失敗より先に見る」。判定役(L793〜795)も同じ順なので、同じように起きる。
- 競合: なし

### F7: modelUsage の docstring が自己矛盾していて、累計という前提をテストで確かめていない
- 観点: code-review, code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:237
- 分類: naming_or_comment
- 影響: なし(コメント)。仮に前提が誤っていた場合は、状態コメントのトークン数が少なく記録される。これは費用の記録だけの話で、挙動には響かない。
- 起きやすさ: 普通の使い方。docstring を読んだ人が「累計なのに、どの行も同じ値になる」で混乱する。
- 再指摘: なし
- 根拠: docstring は「累計で、どの行も同じ値になる」と書いている。累計なら、ふつうは行ごとに増える。偽の claude はすべての行に同じ値を入れている(fakes/claude:58)ので、test.py の `4 * 300` の確認は偽の仕様をなぞっているだけである。一方で PR 本文の Evidence は、whatnext #308 の実物の stream で二重に数えなかったことを確かめたと書いている。前提そのものは実物で裏づけがある可能性が高く、直すべきは主に書き方である(「同じ値」なのか「増えていく累計」なのかを、実物に合わせて書く)。
- 範囲: 差分の内
- 再現: 対象外
- 横展開: 同じ前提は `add_tokens` の docstring(L220)にもある。
- 競合: なし

### F8: config の拒否と止める拒否が混ざる場合や、最後でない行の permission_denials を照合する分岐にテストがない
- 観点: code-review
- 場所: skill-dev/review-loop/test.py:511
- 分類: test_gap
- 影響: 低。`seen` の組み立てや、全行の `permission_denials` の照合が壊れても検出できない。
- 起きやすさ: 普通の使い方(今後の変更で回帰したとき)。
- 再指摘: なし
- 根拠: 指摘のうち「result にしか載っていない拒否で止める」は、既存の `deny` mode でテスト済み(fakes/claude:113、test.py:203)なので、この部分は当たらない。テストが欠けているのは次の3つ。同じ子に config の拒否と source のない拒否(result にだけ載る)が混ざる場合。最後でない result の行にだけ `permission_denials` がある場合。tool_use_id がない場合(F4)。
- 範囲: 差分の内
- 再現: 対象外
- 横展開: なし
- 競合: なし

### F9: check_result が拒否の要約を StreamTail.summary と同じように自前で組み立てていて、止める拒否の判定も2か所に分かれている
- 観点: code-review, code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:253
- 分類: style
- 影響: なし。今は挙動が一致しているが、変えるときに2か所を直す必要がある。
- 起きやすさ: 普通の使い方(保守するとき)。
- 再指摘: なし
- 根拠: L253〜254 の辞書の組み立ては、L319 の `summary` と同じ処理である。source の扱いは `poll` に、`seen` の除外は `check_result` に分かれている。
- 範囲: 差分の内
- 再現: 対象外
- 横展開: F10 の重複と同じ根から来ている。
- 競合: なし

### F10: new_config_denials が、poll のたびに辞書全体をリストに複製し、挿入順と件数に頼っている
- 観点: code-review
- 場所: skills/review-loop/scripts/review_loop.py:323
- 分類: style
- 影響: なし。上書きによる取りこぼしは F4 にまとめた。ここで残るのは書き方と、わずかな無駄だけである。
- 起きやすさ: 普通の使い方
- 再指摘: なし
- 根拠: `list(self.config_denied.values())[self.reported:]`。拒否を list に append し、id は set で別に持てば、F4 の上書きもあわせて解消する。
- 範囲: 差分の内
- 再現: 対象外
- 横展開: なし
- 競合: なし

### F11: run_judge が、run_reviews の子1つ分の処理(ポーリング、watch_denials、タイムアウト、finish、check_result)を複製している
- 観点: code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:778
- 分類: style
- 影響: なし。拒否や読み残しの扱いを変えるたびに2か所を直す必要があり、F6 のように同じ癖が両方に入る。
- 起きやすさ: 普通の使い方(保守するとき)
- 再指摘: なし
- 根拠: L784〜795 と L706〜718 は、同じ順で同じ処理をしている。この PR で判定役を stream-json に替えたときに生まれた重複である。
- 範囲: 差分の内
- 再現: 対象外
- 横展開: なし
- 競合: なし

### F12: 最後のターンで本文を繰り返すスキルでは、判定役への入力に本文が2回入る
- 観点: code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:259
- 分類: other
- 影響: 低。判定役の入力のトークンが増え、同じ指摘を2件として数える誤りを誘いうる。判定役は「同じ問題は1件にまとめる」よう指示されているので、実害は小さい。
- 起きやすさ: 特定の操作の組み合わせ。観点スキルが途中のターンで本文を出す → 最後のターンで「最終結果:」として同じ本文を出し直す。
- 再指摘: なし。docstring は「途中経過の文も混ざるが、欠けるよりよい」と書いているが、これは途中経過の文について割り切った理由で、本文が丸ごと重なる場合は扱っていない。
- 根拠: L259 は、空でない行をすべて重複を除かずにつないでいる。
- 範囲: 差分の内
- 再現: 対象外
- 横展開: なし
- 競合: なし

## 競合

なし

(補足: security-review は「`source: config` は CLI 自身が出すもので偽装できず、何かが許可されるわけでもない」として、脆弱性を0件と結論している。F3 はセキュリティの穴ではなく、レビューが欠けたまま成功扱いになるという信頼性の問題なので、この結論とは両立する。security-review の出力は対象を正しく見たレビューになっており、観点の欠落はない。)

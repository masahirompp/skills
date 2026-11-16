## 指摘

### F1: 止めるかどうかを `source == "config"` だけで決めているため、差分を読めなかった拒否や、許可ルールが無いことによる拒否でも試行が成功扱いになりうる
- 観点: code-review, code-review-2, security-review
- 場所: skills/review-loop/scripts/review_loop.py:319
- 分類: defect
- 影響: 中。拒否のせいで差分を読めなかった観点が rc=0 で通ります。気づけるかどうかは判定役の LLM が「観点の欠落」を出すかにかかっており、出さなければ、親は差分を見ていないレビューの「指摘なし」を受けて収束しうる。許可ルールが無いための自動拒否にも `source: config` が付くなら、SKILL.md の前提「許可されていないコマンドは試行が失敗する」も黙って崩れる。
- 起きやすさ: 特定の操作の組み合わせ。観点スキルが `gh pr diff 7; grep -n KEY .env` のような複合コマンドを実行する → 利用者の deny ルールに当たってコマンド全体が拒否される(source=config, reason_type=subcommandResults)→ `StreamTail.poll` がこれを `config_denied` に入れ、`watch_denials` は止めない → 子が差分を読まないまま終わる → `check_result` は `config_ids` にある id を除くので成功になる。もう一つの順: 許可ルールに無いコマンドの拒否に source=config が付く場合(本物の claude で確かめられていない)。
- 再指摘: なし。過去のレビューで採らなかった指摘ではない。ただし PR 本文の Merge Danger に「許可ルールが無いための拒否も `source: config` になるなら、止まらずに続く。その場合は判定役の観点の欠落と親の `denials.txt` の確認に頼る」とあり、作者は既知のリスクとして受け入れている。今回の指摘は、その頼り先が LLM の判断だけであること(判定役に渡るのは 200 文字で切った要約だけ)を具体的に示しているが、新しい事実は持ち込んでいない。
- 根拠: 319〜322 行は `msg.get("source") == "config"` だけで止めない側に振り分けており、`reason_type` も、拒否された操作が差分の取得を含むかも見ていない。main では拒否のイベントが出た時点で止めていた(main の review_loop.py 670 行付近: `if tail.denial: raise AttemptFailed("permission_denied", ...)`)。拒否されたことが判定役に伝わる経路は、JUDGE_PROMPT の「観点の区切りの中に…があれば…観点の欠落として載せる」と、`run_judge` が書き足す要約だけ。security-review は「source は CLI が付けるので偽造できない」と述べ、補足で「CLI の仕様が変わると判定がずれる」と書いている。偽造はできないという点は正しいが、source=config に入る拒否の範囲が想定より広いという問題には答えていない。
- 範囲: 差分の内。止めない扱いはこの PR(0f6501d)で入った。
- 再現: 前半(差分の取得を含む config の拒否が成功扱いになること)は既存のテストで示せる。`python3 skill-dev/review-loop/test.py` の `FAKE_REVIEW_security_review="denyconfig"` のケースでは、拒否されたコマンドが `gh pr diff 7; grep -n KEY .env` なのに rc=0 になる(テストもそれを期待している)。後半の、許可ルールが無いための拒否に source=config が付くかは本物の claude の挙動なので、実行では示せない(外部のサービスの挙動のため)。確かめるなら、空の一時ディレクトリで `git init` し、許可ルールを置かずに `claude -p --output-format stream-json --verbose "git log -1 を実行して"` を流し、出力の `"subtype":"permission_denied"` の行に `source` が付くか、その値は何かを見る。利用者の設定の影響を除くため、`--settings` で空の設定を渡すなど、隔離した設定で実行する。
- 横展開: 規則は「レビューの対象を読めなかった試行は成功にしない」。同じ判定を通る経路に `run_judge` の `watch_denials("judge", ...)`(834 行)がある。判定役が config の拒否で判定に必要なファイルを読めなくても止まらない。
- 競合: なし

### F2: tool_use_id の無い config の拒否のイベントは、result の permission_denials に同じ拒否が載ると突き合わせられず、止める側に数えられる
- 観点: code-review, code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:262
- 分類: defect
- 影響: 中(本物の claude が id の無い拒否のイベントを出す場合に限る)。PR の目的である「`.env` 系の拒否では止めない」が効かず、その種の拒否のたびに permission_denied で失敗し、連続失敗の上限にも数えられる。
- 起きやすさ: 特定の操作の組み合わせ。子が config の拒否を受ける → イベントに tool_use_id が無い → result の permission_denials に同じ拒否が載る(id 無しでも、`toolu_1` のような id 付きでも)→ `seen` に照合できる id が無いので `denials` に入り、permission_denied になる。
- 再指摘: あり。PR 本文の「実行で確かめていないこと」に「本物の claude が tool_use_id の無い拒否のイベントを出すかどうか。出すなら、止めない拒否でも試行が止まる(安全側)」とあり、作者は承知のうえで止める側を採っている。今回の指摘に、その理由を覆す新しい事実は無い。ただし F3 のとおり、テストはこの理由と逆の挙動(rc=0)を固定している。
- 根拠: `check_result` の `seen = set(tail.config_ids)` に入るのは id 付きのイベントだけ(`poll` の 320〜322 行)。result 側の拒否は `if not i or i not in seen` で、id が無ければ必ず、id 付きでも seen に無ければ止める側に足す。commit 1b46ee9 の本文に「id のない拒否は突き合わせず、止める側に数える」とあり、意図したとおりの動作である。
- 範囲: 差分の内。突き合わせの処理はこの PR で入った。
- 再現: 一時ディレクトリで test.py と同じ準備をする。偽の claude(`skill-dev/review-loop/fakes/claude` を一時ディレクトリに写したもの)の `denyconfignoid` の分岐で、`result(f"{name}: 指摘1件", permission_denials=[{"tool_name": "Bash", "tool_input": {"command": "gh pr diff 7; grep -n KEY .env"}}])` のように result にも同じ拒否を載せて流す。PR の意図(止めない)なら rc=0 になるはずだが、実際には rc=1 で `permission_denied: review security-review` になる。
- 横展開: 規則は「止めない拒否は、イベントと result で同じものと突き合わせて除く」。同じ突き合わせは判定役の `check_result("judge", ...)` も通る(844 行)。
- 競合: なし(C1 で直さないと裁定)

### F3: テストの denyconfignoid は result に permission_denials を載せずに rc==0 を確かめており、本物では起きにくい形を固定している
- 観点: code-review, code-review-2
- 場所: skill-dev/review-loop/fakes/claude:146
- 分類: test_gap
- 影響: 低。テストは「id の無い config の拒否でも試行は成功する」を保証しているように読める。しかし PR 本文と commit 1b46ee9 が述べている挙動は「止める(安全側)」で、テストは F2 の経路を一度も通らない。後で誰かが F2 を「直した」ときに、テストが挙動の変化を捕まえられない。
- 起きやすさ: 普通の使い方(テストを流すたびにこの形で通る)。
- 再指摘: なし
- 根拠: fakes/claude の 146〜149 行は `deny("config", tool_use_id=None)` を2回出したあと `result(f"{name}: 指摘1件")` を出すだけで、`result()` の既定値 `permission_denials: []` のままになっている。一方、同じファイルの `denyconfig`(142 行)は result にも拒否を載せており、偽の claude の中でも扱いがそろっていない。test.py:538〜541 は rc == 0 を条件に含めている。
- 範囲: 差分の内。このテストと偽の出力はこの PR(1b46ee9)で足された。
- 再現: 対象外
- 横展開: 規則は「偽の claude の出力は本物の出力の形に合わせる」。同じ形の候補として、`FAKE_JUDGE="denyconfig"` は result に拒否を載せている(id "x" で突き合わせられるので通る)。id 無しの判定役のケースは無い。
- 競合: なし

### F4: run_reviews は AttemptFailed のときだけほかの子の止めない拒否を記録するので、中断やほかの例外の経路では denials.txt から漏れる
- 観点: code-review, code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:733
- 分類: defect
- 影響: 低。中断や internal_error で終わった試行の `denials.txt` と stderr から、最後の巡回より後に子が出した config の拒否が抜ける。その試行は失敗扱いで判定には使われないので、困るのは後から調べるときの手がかりが欠けることだけである。ただし commit 1b46ee9 が掲げた「漏れなく記録する」はこの経路では守られない。
- 起きやすさ: まれな条件。security-review の子が config の拒否を書く → 次の巡回より前に利用者が SIGINT を送る(`on_signal` が Interrupted を投げる)→ `except AttemptFailed` を素通りし、拒否が記録されない。
- 再指摘: なし
- 根拠: 733 行は `except AttemptFailed:` だけ。`Interrupted` は `Exception` の派生で(92 行)、ここでは捕まらない。`poll_reviews` の中では git や gh を呼ばないので、Precondition は実際には出ない(code-review-2 が挙げた Precondition の例は当たらない)。直すときは、code-review の案のとおり捕まえる範囲を広げると、F5(記録の中の OSError が元の例外を置き換える)に当たる機会も増える。広げるなら、記録の部分を `try/except OSError` で囲むことと一緒に直す必要がある。
- 範囲: 差分の内。ほかの子の拒否を止める前に記録するのは、この PR の目的(1b46ee9)の直し残し。
- 再現: test.py の最後のケース(`failafter` と `denyconfighang`、`POLL_SECONDS: 3`)にならう。`failafter` の代わりに、`marker` ができるのを待ってから本体のプロセスグループに SIGINT を送る手順を一時ディレクトリで組む。たとえば、テストから `run` を Popen で起動し、`marker` ができたら `os.kill(pid, SIGINT)` を送る。期待は、`denials.txt` に `review security-review: Bash` があること。実際には無いはず(stderr は `failed: interrupted: SIGINT`)。
- 横展開: 規則は「試行を止める前に、全ての子の止めない拒否を記録する」。`run_judge` は巡回のたびに記録しているので、同じ漏れは最後の巡回より後の分だけ。`Children.kill_all` で子を止める経路(iterate の後始末)では、どの例外でも読み直さない。
- 競合: なし

### F5: except の中の record_config_denials が OSError を出すと、元の AttemptFailed が internal_error に置き換わる
- 観点: code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:736
- 分類: defect
- 影響: 低。状態コメントに残る失敗の種類が、本来の timeout などではなく internal_error になる。stderr の traceback には `During handling of the above exception` として元の例外も出る(`traceback.format_exception` は既定で連鎖をたどる)ので、詳細までは消えない。
- 起きやすさ: まれな条件。子が timeout になる → except の中で `denials.txt` を追記しようとして、ディスクが一杯などで OSError が出る。
- 再指摘: なし
- 根拠: 733〜737 行の except の中で `record_config_denials` が `open(..., "a")` を呼んでいる。`classify` は AttemptFailed 以外を internal_error にする(994 行〜)。
- 範囲: 差分の内。この except はこの PR で入った。
- 再現: 一時ディレクトリでテストを組む。`review_loop.record_config_denials` を、`OSError` を投げる関数に差し替える(テストで import して monkeypatch)。そのうえで `FAKE_REVIEW_code_review="failafter"`、`FAKE_REVIEW_security_review="denyconfighang"` を流す。期待は `failed: child_error`、実際には `failed: internal_error` になるはず。
- 横展開: 規則は「後始末の失敗で元の失敗の理由を置き換えない」。同じ形の候補として、`watch_denials` の中の `record_config_denials` も、巡回の途中で OSError を出すと internal_error になる(こちらは元の例外が無いので置き換えではない)。
- 競合: なし

### F6: 試行を止める拒否のイベントに id が無いと、result の同じ拒否と重複を除けず、stderr と failure.txt に2回出る
- 観点: code-review
- 場所: skills/review-loop/scripts/review_loop.py:257
- 分類: defect
- 影響: 低。拒否の一覧が `Bash {...}; Bash {...}` のように重複し、親が別々の拒否が2件あったと読み違えうる。種類と止まることは変わらない。
- 起きやすさ: まれな条件。source の無い拒否のイベントが id 無しで出る → 子が巡回より先に終わり、`watch_denials` の running=True の経路で止まらずに `check_result` に入る → result にも同じ拒否が id 無しで載る。
- 再指摘: なし
- 根拠: 256〜259 行は、id があるときだけ `seen` に足したうえで、`tail.denial` を必ず `denials` に入れる。264〜266 行の result の拒否は `not i` なら必ず足す。そのため id 無しの同じ拒否が2回入る。main の `check_result` は result の `permission_denials` だけを使っていたので、重複しなかった。
- 範囲: 差分の内
- 再現: 一時ディレクトリで、偽の claude に `deny(tool_use_id=None)` を出してから `result("x", permission_denials=[{"tool_name": "Bash", "tool_input": {"command": "gh pr diff 7; grep -n KEY .env"}}])` を出してすぐ終わる分岐を足し、流す。期待は、`failure.txt` の拒否が1件であること。実際には同じ `Bash {...}` が `; ` でつながって2件出るはず。
- 横展開: 規則は「同じ拒否は1回だけ数える」。同じ形の候補は F2 の突き合わせ(id が無いと照合できない)。
- 競合: なし

### F7: tool_use_id の無い拒否は tool_inputs.get(None) を引くので、id の無いほかの tool_use の入力が付きうる
- 観点: code-review
- 場所: skills/review-loop/scripts/review_loop.py:332
- 分類: defect
- 影響: 低。`denials.txt` や判定役への入力に、拒否された操作として別の呼び出しの入力が載りうる。ただし、本物の claude の tool_use には必ず id が付くので、`tool_inputs` に None のキーが入るのは偽の claude だけと見られる。code-review が根拠に挙げた「Read の拒否に Bash のコマンドが付いている」出力は、偽の claude の `deny()` が name に関係なく `{"command": ...}` を入力にしているためで、取り違えの証拠にはならない(fakes/claude:50〜52 行)。
- 起きやすさ: まれな条件。id 無しの tool_use と id 無しの拒否のイベントが両方出たときだけ起きる。
- 再指摘: なし
- 根拠: `poll` は `self.tool_inputs[block.get("id")]` で入力を覚える(id が無ければキーは None)。`summary` は `self.tool_inputs.get(d.get("tool_use_id"), {})` で引く。main の `denial_summary` も同じ引き方だった。
- 範囲: 差分の内。止める拒否の stderr への表示は main から同じだったが、取り違えが `denials.txt` と判定役への入力に載るのは、この PR が足した config の拒否の記録の経路から。
- 再現: 一時ディレクトリでテストを組む。`StreamTail` に次の3行を書いたファイルを読ませる: assistant の tool_use(id 無し、name Bash、input `{"command": "A"}`)、assistant の tool_use(id `t2`、name Read、input `{"file_path": "B"}`)、`{"type": "system", "subtype": "permission_denied", "source": "config", "tool_name": "Read"}`(id 無し)。`tail.config_summary(tail.config_denied[0])` を呼ぶと、期待は入力が `{}`、実際には `Read {"command": "A"}...` になるはず。
- 横展開: 規則は「id が無いものを id で引かない」。同じ引き方は `check_result` の 258 行にもある。
- 競合: なし

### F8: レビュー役の出力は result の行を全てつなぐので、途中の下書きや取り下げた指摘も判定役に渡る
- 観点: code-review
- 場所: skills/review-loop/scripts/review_loop.py:245
- 分類: defect
- 影響: 低。取り下げた指摘を判定役が有効なものとして F 番号を付けると、親が不要な修正をして反復が増えうる。ただし取り下げの文も同じ区切りに続けて入り、判定役は根拠をコードで確かめる指示を受けているので、拾われる可能性は低い。
- 起きやすさ: 特定の操作の組み合わせ。サブエージェントをバックグラウンドで動かす観点スキルが、途中の行で指摘を出し、後の行で取り下げる。
- 再指摘: あり。PR 本文の「直さなかったもの」に「レビュー役の出力で、同じ本文が2回つながりうる: 判定役が重複をまとめるので、実害が小さい」とある。今回の指摘は「重複」ではなく「取り下げ」で、判定役が重複をまとめても消えない点で事情は少し違う。とはいえ、取り下げの文が本文のすぐ後に続くので、実害が小さいという理由はおおむね当てはまる。判定役と扱いがそろっていないという点は、意図した違いである。レビュー役の本文は途中の行に入り(PR の Evidence にある whatnext #308 の実物)、判定役の判定は1行で完結する必要があるため。不整合ではない。
- 根拠: 245 行は空でない result を全て `"\n\n".join` している。docstring(238〜239 行)と SKILL.md に「途中経過の文も混ざるが、欠けるよりよい」と明記されている。
- 範囲: 差分の内
- 再現: 一時ディレクトリのテストで、偽の claude の観点に `multi("Standards: X はバグ", "Spec と照らすと X は意図どおり、取り下げ")` を出させる。`judge-input.md` に両方の文が入ることを確かめる(期待どおりに入る。判定役がそれをどう扱うかは LLM の挙動なので、実行では示せない)。
- 横展開: なし
- 競合: なし

### F9: 途中の result の行が is_error でも、最後の行が成功なら成功になり、そのエラー文が本文として判定役に渡る
- 観点: code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:250
- 分類: defect
- 影響: 低。`judge-input.md` に `API Error: 529` のような文が観点の出力として混ざる。本文が欠けていても、判定役が観点の欠落として扱わないことがある。
- 起きやすさ: まれな条件。途中のターンが API エラーで is_error=true の result を出す → 子が続けて最後のターンを success で終える。
- 再指摘: なし
- 根拠: 成否は `data = tail.results[-1]` だけで見ており(248〜249 行と 268 行)、途中の行の `is_error` を見ていない。テキストは全ての行をつなぐ(245 行)。main は最後の行だけを使っていたので、途中の行は成否にも本文にも入らなかった。
- 範囲: 差分の内。途中の行の文が本文に入るのはこの PR から。
- 再現: 一時ディレクトリのテストで、偽の claude に `result("API Error: 529", subtype="error_during_execution", is_error=True)` のあと `result("本文")` を出させる。今のコードでは rc=0 になり、`judge-input.md` に `API Error: 529` が入るはず。期待する挙動(失敗にするか、本文から除くか)は親が決める。
- 横展開: 規則は「エラーの行を本文として扱わない」。判定役は見出しを含む行だけを採るので、同じ問題は起きない。
- 競合: なし

### F10: トークン数を最後の result の行の modelUsage だけで数えるのは、modelUsage がどの行にもセッション全体の値で入るという前提に頼っている
- 観点: code-review
- 場所: skills/review-loop/scripts/review_loop.py:248
- 分類: defect
- 影響: 低。前提が崩れると、状態コメントと stderr のトークン数が少なく出る。トークン数は表示にだけ使い(608〜648 行、1028 行)、上限などの判断には使わない。
- 起きやすさ: まれな条件。本物の claude が、行ごとの差分だけを modelUsage に入れるか、バックグラウンドのサブエージェントの分を最後の行に入れない場合だけ起きる。
- 再指摘: なし
- 根拠: 248〜249 行は最後の行だけを `add_tokens` に渡している。PR 本文の Evidence では、本物の stream(whatnext #308)に当てて「二重に数えなかった(出力 18004)」と確かめているが、サブエージェントの分が最後の行に含まれるかまでは書いていない。test.py の 4*300 の確認は、偽の claude がどの行にも同じ値を出すことしか確かめていない。
- 範囲: 差分の内。複数の result の行を扱うのはこの PR から。
- 再現: 実行では示せない。本物の claude の出力の形の問題のため。確かめるなら、whatnext #308 の試行1の `review-*.stdout.jsonl` を読み、最上位の各 result の行の `modelUsage` を並べる。値が単調に増え、最後の行がサブエージェントのモデルの分も含んでいるかを見る(読み取りだけで済む)。
- 横展開: なし
- 競合: なし

### F11: timeout や拒否で途中で止めた子のトークン数を足していない
- 観点: code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:750
- 分類: defect
- 影響: 低。失敗した試行のトークン数が実際より少なく出る。SKILL.md:98 に「失敗した試行の分は、途中で止めた子を含まない下限」と明記されているので、利用者が誤解する余地は小さい。
- 起きやすさ: 特定の操作の組み合わせ。観点が result の行をいくつか出したあと、40 分を超えて timeout になる。
- 再指摘: なし
- 根拠: timeout と拒否の経路は、`check_result` を通らずに raise する(749〜750 行、`watch_denials`)。main も同じで、timeout のときは `check_result` を呼んでいなかった。
- 範囲: 差分の外。main でも、子を途中で止めた経路は `check_result` を通らず、トークン数を足していなかった。SKILL.md にも下限だと書いてある。PR で `tail.results` が複数の行を持つようになり、足せる値が手元に残る場面は増えたが、足さない挙動自体は前からある。
- 再現: 一時ディレクトリのテストで、偽の claude に `multi("途中")` を出させてから `time.sleep(120)` させ、`REVIEW_TIMEOUT` を短く上書きして流す。今のコードでは、状態コメントのその試行のトークン数は 0 のはず。
- 横展開: なし
- 競合: なし

### F12: 判定役が ## 指摘 と ## 競合 を別々の result の行に出すと no_output になる
- 観点: code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:845
- 分類: other
- 影響: 低。その試行は no_output で失敗し、連続失敗に1回数えられる。再実行すれば済む。
- 起きやすさ: まれな条件。判定役が result の行を複数出すのは、バックグラウンドのタスクでターンを分けたときだけ。判定役のプロンプトはそれを求めていない。
- 再指摘: あり。commit 6a008f4 と PR 本文の「反復1」で、「つないだテキストを判定にすると、無関係な文や2組目の判定が混ざり、見出しが別々の行にしかなくても通っていた」ことを不具合として直している。test.py の `split` のケースも、no_output になることを意図した挙動として固定している。今回の指摘は「試行が無駄になる」という逆向きの懸念で、判定役が実際に見出しを分けて出すという観測は無い。以前の理由を覆す事情は無い。
- 根拠: 845〜853 行は `reversed(tail.results)` で、全ての見出しを含む最後の行だけを採っている。VERDICT_SECTIONS のコメント(763〜764 行)が「形の揺れで試行が無駄になる」のを避けると言っているのは項目の抜けについてで、行が分かれる場合のことではない。
- 範囲: 差分の内
- 再現: 対象外
- 横展開: なし
- 競合: なし

### F13: 終わった子について watch_denials を2回呼んでいる
- 観点: code-review, code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:747
- 分類: style
- 影響: なし。rc が None でないとき、747 行の呼び出しは記録するだけで raise せず、755 行が同じことをやり直す。読む人に2回呼ぶ理由が伝わらない。
- 起きやすさ: 普通の使い方。子が終わるたびに通る。
- 再指摘: なし
- 根拠: 747 行は `running=rc is None`。rc が None でなければ `record_config_denials` だけを実行する。その直後の `tail.poll()` と 755 行で、同じ処理を読み残しまで含めてやり直している。
- 範囲: 差分の内
- 再現: 対象外
- 横展開: なし
- 競合: なし

### F14: 判定役の待ち方が p.wait から POLL_SECONDS ごとの sleep に変わり、判定役が終わってから最大2秒余計に待つ
- 観点: code-review
- 場所: skills/review-loop/scripts/review_loop.py:837
- 分類: other
- 影響: なし。1試行あたり最大2秒遅れる。数分〜数十分かかる試行の中では無視できる。
- 起きやすさ: 普通の使い方。毎回の試行で通る。
- 再指摘: なし
- 根拠: main は `p.wait(JUDGE_TIMEOUT)` だった。今は 832〜837 行で `time.sleep(POLL_SECONDS)` の巡回になっている。拒否を監視するために巡回が必要になったという変更の理由は正当。`p.wait(timeout=POLL_SECONDS)` で `TimeoutExpired` を捕まえれば、監視したまま遅れを無くせる。
- 範囲: 差分の内
- 再現: 対象外
- 横展開: レビュー役の `poll_reviews` も同じ巡回だが、子が複数あるので、1つの子を wait する形にはできない。
- 競合: なし

### F15: new_config_denials と config_denials が、同じ拒否の要約を別々に作っている
- 観点: code-review
- 場所: skills/review-loop/scripts/review_loop.py:337
- 分類: style
- 影響: なし。今は両方とも `config_summary` を通るので、`denials.txt` と `judge-input.md` の表記は一致している。要約を一度作って持てば、`reported` での数え方と合わせて簡素になる。
- 起きやすさ: 普通の使い方
- 再指摘: あり。PR 本文の「直さなかったもの」に「拒否の要約の組み立ての重複: 挙動に関わらない。まとめると、レビューしていない共有の処理が増える」とある。今回の指摘も挙動には関わらないので、その理由を覆す事情は無い。
- 根拠: 337〜345 行は、どちらも `self.config_summary(d)` を呼んでいる。
- 範囲: 差分の内
- 再現: 対象外
- 横展開: F16 と同じ規則(要約の組み立てを1か所にまとめる)。
- 競合: なし

### F16: check_result と StreamTail.summary で、拒否の dict の組み立てが重複している
- 観点: code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:257
- 分類: style
- 影響: なし。片方だけ直すと、stderr(`summary`)と failure.txt(`check_result`)で拒否の表示が食い違う余地がある。
- 起きやすさ: 普通の使い方
- 再指摘: あり。F15 と同じ、PR 本文の「拒否の要約の組み立ての重複」を直さないという判断に当たる。今回の指摘も、表示が食い違う「余地」を挙げているだけで、その理由を覆す事情は無い。
- 根拠: 257〜258 行の `{"tool_name": ..., "tool_input": tail.tool_inputs.get(...)}` は、331〜332 行の `summary` と同じ組み立て。
- 範囲: 差分の内
- 再現: 対象外
- 横展開: F15
- 競合: なし

## 競合

### C1: tool_use_id の無い config の拒否で、誤って止まらないようにする(PR の目的を守る)か、止める側に倒す(安全側)か
- 場所: skills/review-loop/scripts/review_loop.py:262
- 指摘: code-review: id の無い config の拒否は result の側で必ず止める側に数えられ、止めない経路が実質的に通らない。code-review-2: id の無い config の拒否のイベントは result の id 付きの拒否と突き合わせられず、止まってしまう。security-review: id の無い拒否や source の無い拒否を止める側に数えるのは安全側に倒した扱いで、検知のすり抜けにならない。
- 裁定: security-review。直さない。commit 1b46ee9 は「id のない拒否は止める側に数える」と明記し、PR 本文も「出すなら、止めない拒否でも試行が止まる(安全側)」と受け入れている。本物の claude が id の無いイベントを出すかはまだ観測されていない。F1 のとおり、止めない側は差分を読めないレビューを通しうる。この状態で突き合わせを緩める(id の無いものを tool_name などで照合する)と、関係のない拒否まで止めない側に入る危険のほうが大きい。止まっても permission_denied として表に出るので、利用者が気づいて判断できる。ただし、テストがこの挙動と逆の rc=0 を固定している点(F3)は直すべき。

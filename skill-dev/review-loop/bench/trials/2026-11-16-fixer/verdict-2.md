## 指摘

### F1: レビュー役の名前(`code-review-2`)が表に出るのに、`--instruct` はスキル名しか受け付けず、エラー文も対応を示さない
- 観点: code-review, code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:465
- 分類: defect
- 影響: 低。親が提案した `--instruct 'code-review-2=…'` は、子を起動する前に終了コード2で止まる。エラー文は「観点: code-review, code-review, security-review」と同じ名前を並べるだけなので、スキル名を書くべきだと気づくまで遠回りする。重ねた片方だけに指示を渡す手段も無いが、これは SKILL.md:63 が「その全てに渡る」と書いた仕様である。
- 起きやすさ: 特定の操作の組み合わせ。既定で回す → `code-review-2` だけが `permission_denied` になる → stderr に `review code-review-2` と出る → 親が SKILL.md:161 の「その観点への `--instruct`」に従って役の名前を書く。
- 再指摘: なし
- 根拠: コードを読んで確かめた。`review_config` の `names` は `skill_name(s)` の一覧(456行)で、465行はそれとだけ照合する。失敗の対象は `f"review {name}"` で役の名前になる(853、855、861行)。main では役の名前とスキル名が常に同じで(重複は拒否していた)、このずれは無かった。観点の出力が言う「実行して確認」は、こちらでは実行していない。
- 範囲: 差分の内
- 再現: `skill-dev/review-loop/test.py` の `run` を使い、既定の観点のまま `run(wt, "--instruct", "code-review-2=x")` を実行する。期待は、受け付けるか、「役の名前ではなくスキル名 `code-review` を書く」と分かるエラーが出ること。実際は rc == 2 で、stderr は `--instruct のスキル code-review-2 が観点にない(観点: code-review, code-review, security-review)` になるはず。偽の `claude` と `gh` だけを使うので、GitHub には触れない。
- 横展開: 規則は「利用者に見せる名前と、利用者が入力する名前を揃える」。候補は、SKILL.md:161 の「その観点への `--instruct`」、SKILL.md:66 と状態コメントの「指示を渡した観点の名前」(`attempt["instructed"]` はスキル名、1066行)、F2 の判定役の出力欄。
- 競合: なし

### F2: JUDGE_PROMPT が重ねた観点に合わせて更新されておらず、「観点」欄にスキル名と役の名前のどちらを書くかが決まらない
- 観点: code-review, code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:908
- 分類: defect
- 影響: 低。判定役がスキル名を書くと、2回目だけが出した指摘も「観点: code-review」になり、親は `review-code-review.result.md` を開いて見つけられない。「code-review, code-review-2」と書くと、親は独立した2観点の一致と読みうる。どちらも、親が両方のファイルを読めば取り戻せる。
- 起きやすさ: 普通の使い方。既定の観点で回すたびに、判定役の入力は `===== 観点: code-review =====` と `===== 観点: code-review-2 =====` に分かれる(945行)。
- 再指摘: なし
- 根拠: JUDGE_PROMPT はこの PR の差分に含まれず、908行は「観点スキルの名前」のままである。`code-review-2` が同じスキルの2回目だという説明は、プロンプトにも `judge_system_prompt` にも無い。この判定自身も同じ入力を受けており、欄には区切りの名前を書いた。競合の「採る観点」が同じスキルどうしで意味を持たないという点は、今回は競合が無く確かめる材料が無い。
- 範囲: 差分の内(行は変えていないが、名前が分かれたのはこの PR の変更による)
- 再現: 実行では示せない。プロンプトの書き方の問題で、判定役(LLM)がどちらを書くかは回ごとに変わり、偽の `claude` は判定を固定の文で返すため。
- 横展開: 規則は F1 と同じ。候補は、JUDGE_PROMPT の「観点どうしの競合」「挙げた観点を全て書く」と、判定の「観点」欄からレビューの出力ファイルを引く SKILL.md の手順4。
- 競合: なし

### F3: 既定から `mattpocock-skills:code-review` を外すと、PR 本文を仕様として実装との食い違いを見る観点が既定に無くなるが、その損失を採用した集計では測れていない
- 観点: code-review, code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:49
- 分類: other
- 影響: 中。既定で回すと、仕様や文書と実装の食い違い、設計の誤りを見る役がいなくなり、利用者は見落としに気づけない。ただし裏づけは別の形の結果の1試行・1件だけで、損失の大きさは確かめられていない。
- 起きやすさ: 普通の使い方。`--perspective` を付けずに回すたびに当てはまる。実際に見落としが出るのは、PR 本文や README と実装が食い違う PR に限られる。
- 再指摘: あり(部分的)。PR 本文の「確かめていないこと」は、正解が行単位の不具合で設計の誤りを測っていないと既に書いている。ただし「だから外す」という判断に当てはめていない。今回は、`results/main` に単独の検出があることと、`security-review` を残した基準(外す影響を測れない)との不揃いが新しい事情になる。
- 根拠: `repeat.py results/main` を実行して確かめた。「code-review の全ての試行を合わせても見つからず…」の節に `mattpocock: W306-7` と `security-review: W306-6` が出る。W306-7 は `answers/wn-306.json` で `file` が `README.md` の不具合である(中身が「記述と実装の食い違い」かまでは読んでいない)。`results/pr` では同じ節が「なし」で、`repeat.md` と一致する。`score.py:114` は trivial に「重複、構造の好み、テストが無いという指摘」を含める。`results/pr/_clusters` で mattpocock だけが挙げたまとまりを数えると trivial 45、wrong 4、real 0 だった。観点の言う 55 とは合わないが、real が0で大半が trivial という向きは同じ。費用の差(題材あたり約 $1.1 と余計な指摘 +6件、対して security-review は $0.40・0件)も `repeat.md` と合うので、外す側にも根拠はある。
- 範囲: 差分の内
- 再現: 対象外
- 横展開: 規則は「測れていない軸は、同じ基準で残すか外すかを決める」。候補は、`security-review` を残した理由の書き方(README.md:51、PR 本文)と、SKILL.md:170 の「既定には無い」の案内。
- 競合: なし

### F4: bench の README が「この2つのスキルが見つけた不具合は無い」と書くが、各1試行の `results/pr` だけに基づくことと、余計な指摘の指標が設計の指摘を些末に数えることが「言えないこと」に無い
- 観点: code-review, code-review-2
- 場所: skill-dev/review-loop/bench/README.md:51
- 分類: naming_or_comment
- 影響: 低。読み手(既定を次に見直す人)が「外しても失うものは無い」と、実際より強く受け取る。README は開発用の文書で、スキルの挙動は変わらない。
- 起きやすさ: 普通の使い方。README を読んで既定を見直すとき。
- 再指摘: なし(F11 の README の書き直しは反復1で済んでいるが、この2点は扱っていない)
- 根拠: 51行の記述は `results/pr` については正しい(`repeat.md` と一致)。同じリポジトリの `results/main` では、security-review が W306-6、mattpocock が W306-7 を単独で検出する(実行して確かめた)。`results/main` では code-review 2回分が 21〜26件、前の既定が 20〜24件で、幅が重なる。ただし `results/main` は PR なしの形で、本番の引数とは違う(README.md:43)。54行の「言えないこと」は、perspectives と plain の試行2・3を使っていないことは書くが、security-review と mattpocock が `results/pr` で1試行だけ(README.md:44 の「ほかは1回」)であることを、結論の限定として書いていない。余計な指摘の分類の盲点は F3 の根拠のとおり。
- 範囲: 差分の内
- 再現: 対象外
- 横展開: 規則は「根拠の限定を、結論と同じ場所に書く」。候補は、`review_loop.py:42-45` のコメント(「多く見つかった」「少なかった」と書く)と、PR 本文の「根拠」。
- 競合: なし

### F5: `repeat.py` が、一部の題材で欠けた試行を警告なしに全題材分として集計し、試行1が無い構成を黙って比較から落とす
- 観点: code-review, code-review-2
- 場所: skill-dev/review-loop/bench/repeat.py:29
- 分類: defect
- 影響: 低。途中で失敗した実行の結果にかけると、検出・時間・費用が黙って下がり、既定を決める根拠の数字が誤る。コミット済みの `results/pr` は全題材が揃っている(code-review-2 が確認)ので、今の数字には影響しない。
- 起きやすさ: 特定の操作の組み合わせ。bench の一部の題材や試行が失敗する → そのまま `repeat.py` をかける。
- 再指摘: なし(反復1の F12 は 0 で割る件で、別の問題)
- 根拠: コードを読んで確かめた。29行は、どれかの題材にある試行番号を全て採る。欠けた題材は、`det` に何も足されず、`dur[k].get(c, 0)` が0、`cost` も足されないまま、分母は `len(cases)` と `len(bugs)` で変わらない(61〜63行)。75行の `(c, 1) in cost` は、試行1が1題材にでもあれば採り、無ければ警告なしに落とす。観点の言う具体的な数字(18件、$0.53)は実行していない。
- 範囲: 差分の内(この PR の新しいファイル)
- 再現: `cp -R skill-dev/review-loop/bench/results/pr "$(mktemp -d)/pr"` で写しを作り、写しの中の `sk-12/code-review/2` を消して、`python3 skill-dev/review-loop/bench/repeat.py <写し>` を実行する。期待は、欠けを警告するか止まること。実際は `code-review#2` の行が、警告なしに元(21件、$0.59)より小さい値で出るはず。
- 横展開: 規則は「欠けたデータを0として合算しない」。候補は、同じ読み込みを持つ `combos.py:22-52`(F11)と、`score.json` が無い試行を `continue` で飛ばす `repeat.py:51-52`(費用と時間は足し、検出は足さない)。
- 競合: なし

### F6: 名前の重なりを拒否で扱うので、番号付けが作った名前と実在のスキル名がぶつかる正当な組み合わせを起動できない
- 観点: code-review
- 場所: skills/review-loop/scripts/review_loop.py:443
- 分類: other
- 影響: 低。`--perspective code-review --perspective code-review --perspective code-review-2` や、スキル `focus-1` と `--focus` の併用が終了コード2で止まり、利用者は役の名前を変えられない。止まるのは子を起動する前で、出力の上書きは起きない。
- 起きやすさ: まれな条件。`<スキル名>-<数字>` や `focus-<数字>` という名前のスキルを、同じスキルの重ねや `--focus` と一緒に使うとき。
- 再指摘: あり(設計の選び直し)。反復1の F9(出力の上書き)を、拒否で直したと PR 本文が書いている。拒否を選んだ理由は書かれていない。今回は別の直し方(番号を飛ばす、名前空間を分ける)の提案で、拒否が誤りだと示す事情は無い。
- 根拠: コードを読んで確かめた。スキル名、番号付きの名前、`focus-N` は同じ名前空間にあり、重なりは `safe_name` 後の名前で比べて拒否する(436〜445行)。この挙動は test.py:385〜392 が期待として固定し、SKILL.md:64 にも書いてある。意図した挙動である。
- 範囲: 差分の内
- 再現: 対象外
- 横展開: 規則は「作った名前が入力の名前と重ならないようにする」。提案どおり名前の形を変えると、出力ファイル名(`review-code-review-2.result.md`)、SKILL.md:62 と 64、test.py:178 と 618 の期待が全て変わる。
- 競合: なし

### F7: 繰り返す構成の試行がちょうど2つのとき、「全ての試行を合わせた行」が直前の2つ組の行と同じ内容で2回出る
- 観点: code-review, code-review-2
- 場所: skill-dev/review-loop/bench/repeat.py:74
- 分類: defect
- 影響: 低。表に同じ行が2つ並ぶだけで、数字は誤らない。
- 起きやすさ: 特定の操作の組み合わせ。試行が2つだけの構成(または結果)に `repeat.py` をかける。コミット済みの `results/pr` は3試行なので起きない。
- 再指摘: なし
- 根拠: コードを読んで確かめた。試行が2つだと、72〜73行の `combinations(trials, 2)` が1行を出し、74行が同じ名前・同じキーでもう1行を出す。30行が2未満を断るので、2つの場合は通る。
- 範囲: 差分の内
- 再現: `results/pr` を一時ディレクトリに写し、全題材の `code-review/3` を消して `repeat.py <写し>` を実行する。期待は、`code-review#1 + code-review#2` の行が1つ。実際は2行続けて出るはず。
- 横展開: なし
- 競合: なし

### F8: SKILL.md が根拠として指す `skill-dev/review-loop/bench/README.md` は、プラグインに含まれず、スキルを使う側から辿れない
- 観点: code-review, code-review-2
- 場所: skills/review-loop/SKILL.md:25
- 分類: naming_or_comment
- 影響: 低。プラグインとして入れた環境で、親が根拠を読もうとしても、cwd にも `${CLAUDE_SKILL_DIR}` の下にも無い。レビューの実行そのものには影響しない。
- 起きやすさ: 特定の操作の組み合わせ。別のリポジトリで review-loop を回し、親が既定の根拠を確かめようとするとき。
- 再指摘: なし
- 根拠: 確かめた。`.claude-plugin/plugin.json` は `"skills": "./skills/"`、`README.md:19` は「`skill-dev/` は…プラグインには含まれず」と書く。`git show main:skills/review-loop/SKILL.md` に `skill-dev` は出ないので、この参照は PR が初めて入れた。SKILL.md のほかのパス(`scripts/review_loop.py`)はスキルのディレクトリからの相対である。
- 範囲: 差分の内
- 再現: 対象外
- 横展開: 規則は「SKILL.md から指すパスは、配布される範囲に置く」。候補は `review_loop.py:45` のコメント(`skill-dev/…/repeat.md` を指す。読むのは開発者なので害は小さい)。
- 競合: なし

### F9: SKILL.md が「既定を変えるときは `PERSPECTIVES` だけを書き換える」と述べた直後に、既定の中身を本文に書き写している
- 観点: code-review-2
- 場所: skills/review-loop/SKILL.md:25
- 分類: naming_or_comment
- 影響: 低。次に `PERSPECTIVES` だけを変えると、SKILL.md:25 の「既定は `code-review high` を2つと `security-review`」と SKILL.md:170 の「既定には無い」が黙って古くなり、親が古い既定を前提に報告する。
- 起きやすさ: 特定の操作の組み合わせ。次に既定を変える人が、SKILL.md の指示どおり `PERSPECTIVES` だけを直す。
- 再指摘: なし
- 根拠: 確かめた。25行に「そこだけを書き換える」と「既定は…」が並び、170行に「既定には無い」がある。どちらもこの PR の差分で入った。「security-review を外す」の例が古くなるという点は、該当の行を特定していない。
- 範囲: 差分の内
- 再現: 対象外
- 横展開: 規則は「既定の値を持つ場所を1つにする」。候補は、SKILL.md:26 の「この文書に書いた値は、その既定値」と断っている定数、test.py:310 の「既定の3つの役」というコメント、bench の README.md:51。
- 競合: なし

### F10: `role_names` を3か所で呼び直しており、役とスキルの対応が、同じ引数を同じ順で渡し続けることに頼っている
- 観点: code-review, code-review-2
- 場所: skills/review-loop/scripts/review_loop.py:1073
- 分類: style
- 影響: なし。今の3か所は同じ `(perspectives, focuses)` を渡しており、挙動は正しい。将来どこかで `focuses` を渡し忘れると(既定値は `()`)、検査を通った名前と出力ファイルの名前がずれうる。
- 起きやすさ: まれな条件。今のコードでは起きない。番号の付け方や呼び出しを変える将来の変更で起きる。
- 再指摘: なし
- 根拠: コードを読んで確かめた。`review_config` は検査のためだけに呼んで結果を捨て(457行)、別に `names` も作る(456行)。`run_reviews` は `roles[len(perspectives):]` の位置に(834〜837行)、`iterate` は `zip(roles, perspectives)` の位置に頼る(1073〜1075行)。
- 範囲: 差分の内
- 再現: 対象外
- 横展開: F1 と F2 を直すとき、役とスキルの対応を1か所で作って渡す形にすれば、同じ修正で済む。
- 競合: なし

### F11: `repeat.py` の読み込みと集計の前半が、`combos.py` とほぼ同じ写しになっている
- 観点: code-review, code-review-2
- 場所: skill-dev/review-loop/bench/repeat.py:21
- 分類: style
- 影響: なし。数え方を片方だけ直すと、docstring の「数え方は combos.py と同じ」が崩れ、`combos.md` と `repeat.md` の数字を比べられなくなる。今は同じ。
- 起きやすさ: まれな条件。集計の数え方を将来変えるとき。
- 再指摘: あり。PR 本文が「開発用の集計で、PR が膨らむ」として直さないと書いている。今回の2つの観点は、その理由を覆す事情を挙げていない(code-review は自分でそう書いている)。F5 を直すなら、同じ欠けの扱いが `combos.py` にも要るので、そのときは共通化する理由が増える。
- 根拠: `combos.py:37-48` に、同じ `_clusters` の読み込みと `score.json` の読み込みがあることを確かめた。
- 範囲: 差分の内
- 再現: 対象外
- 横展開: F5 の横展開と同じ。
- 競合: なし

### F12: 重ねた役の片方だけが失敗・タイムアウトする経路のテストが無い
- 観点: code-review-2
- 場所: skill-dev/review-loop/test.py:259
- 分類: test_gap
- 影響: なし(今の挙動は変わらない)。`code-review-2` だけが落ちたときの失敗の対象の表示、残りの役の停止、`results` の名前の対応が実行で確かめられておらず、壊れても気づけない。
- 起きやすさ: 普通の使い方。既定が重ねた構成になったので、片方だけの失敗は既定の実行で通る経路になった。
- 再指摘: あり。PR 本文(F13)が「偽の `claude` はスキル名で振る舞いを切り替えるので、作り替えが要る」として直さないと書いている。既定が重ねた構成だという事情は見送った時点で既にあり、理由を覆す新しい事情は無い。F1 を直すなら、その再現に同じ仕組みが要る。
- 根拠: 確かめた。`fakes/claude:128-130` は `args[-1].split()[0]` のスキル名から `FAKE_REVIEW_<名前>` を引くので、`FAKE_REVIEW_code_review=fail` は2つとも失敗させる。test.py:259 はその形のテストだけである。
- 範囲: 差分の内
- 再現: 対象外
- 横展開: 偽の `claude` を、同じスキルの何回目の起動かで振る舞いを変えられる形にすれば、F1 の失敗の対象の表示も同じ仕組みで確かめられる。
- 競合: なし

## 競合

なし

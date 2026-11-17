===== 観点: code-review =====
9 findings, most severe first:

1. `skills/review-loop/scripts/review_loop.py:58`: レビュー役のモデルの既定を `opus` に固定したため、これまで利用者の既定のモデルで動いていた環境で、毎回 `--model` を付けないと動かなくなる。

   Failure scenario: Opus を使えない利用者(プランや組織の制限、別名 opus の対応先が無い Bedrock・Vertex の設定)が、手順どおり `iterate <wt>` を起動する → 事前確認で 'There's an issue with the selected model' が返り、終了コード2になる。この PR より前は既定のモデルで回っていたので、後退になる。SKILL.md は `--model` を『利用者に指示されたときだけ付ける』としているため、親は自分では回避できず、毎反復止まる。使えたとしても、3役すべてが opus になる分だけ費用が上がる

2. `skills/review-loop/scripts/review_loop.py:549`: 事前確認は init で止めず、result までモデルを1ターン動かすようになった。それなのに、NO_MUTATION の制約(--append-system-prompt)も `--max-turns 1` もツールの制限も付けておらず、しかもロックを取る前、`start` のスナップショットを撮った後に、worktree の中で動かしている。

   Failure scenario: プロジェクトの CLAUDE.md や UserPromptSubmit フックが『まずテストやフォーマッタを流す』と指示している → プロンプト 'ok' の子がツールを使い、ファイルを書き換えたまま最大2分動いて kill される → 試行は後の find_contamination で contamination として失敗し、レビュー役のせいにされる。ロックの前に動くので、別の試行の実行中に2つ目を起動した場合も、その事前確認が実行中の試行の worktree を汚しうる

3. `skills/review-loop/scripts/review_loop.py:606`: モデルを使えないと判定する条件が、名前の誤りで観測した文字列(`unrecognized_model` のタグと 'There's an issue with the selected model')だけになっている。ドキュメントがうたう『使う権限が無い』場合に別の形のエラーが返ると、警告だけ出して試行に進む。

   Failure scenario: 名前は正しいが権限の無いモデル(例: 組織で禁止された完全な名前)で、API が 403/404 系の別の文言を返す → 『モデル以外の理由』として warn を出して試行に進む → レビュー役3つが全て child_error で失敗し、連続失敗に数えられる。終了コード2で止めるという SKILL.md の説明(『名前の誤りか、使う権限が無い』)と食い違う

4. `skills/review-loop/SKILL.md:170`: 終了の判断が、『再現なしで直したもの』(defect でない指摘や、影響が低の指摘への修正)をどう扱うかを定めていない。読み方によって、毎回もう1回回すことにも、確かめないまま終えることにもなる。

   Failure scenario: 最終反復で命名の指摘だけを再現なしで直した → 『実行で確かめていない修正が1つでもあれば、もう1回回す』に当たるとも読めるので、命名を直すたびに反復が1回増え、5回の目安を超える。逆に『対象への修正』の条件(再現と既存テスト)は当てはまらないので、差分のレビューだけで終えてよいとも読める。親によって判断が割れる

5. `skills/review-loop/scripts/review_loop.py:1157`: 成功時に、標準出力へ reviews.md の全文(全レビュー役の生の出力)を出している。親が使うのはパスだけで、内容は俯瞰の役に渡すので、親の文脈を毎反復で無駄に消費する。

   Failure scenario: code-review high を2つと security-review の出力が合わせて数十KBになる → バックグラウンドの Bash の出力として、反復ごとに親の文脈に入る。判定役のころは要約された判定だけが入っていた。5反復で文脈を圧迫するうえ、親が俯瞰の前に生の指摘を読むことになり、俯瞰の役をサブエージェントに分けて親を先入観から切り離すという設計の狙いも弱まる。代わりに、標準出力は作業ディレクトリのパスか件数の要約だけにすれば足りる

6. `skills/review-loop/scripts/review_loop.py:789`: model を記録していない旧版の試行(利用者の既定のモデルで動いた)を、表では既定(opus)と区別せずに出している。また、warn_option_change は旧版の試行との比較を飛ばすので、同じシリーズの途中でモデルが変わっても警告が出ない。

   Failure scenario: 旧版で sonnet を既定にして2反復回したシリーズを、新版で続ける → 表には3反復とも『モデル』の注記が無く、同じ opus で回したように見える。直前の試行とモデルが違うという警告も出ない。モデルを固定して反復どうしを比べられるようにする、というこの PR の目的に反して、指摘の数の変化をモデルの違いと見分けられない

7. `skills/review-loop/SKILL.md:162`: 過去の判断を俯瞰の役に伝える経路が、PR 本文と history/ の overview-N.md だけになっている。overview-N.md は俯瞰の役自身の出力なので、親が覆した判断(却下、段階の変更)は入らない。

   Failure scenario: 反復1で俯瞰の役が規則1にまとめた指摘を、親が PR の意図を理由に却下し、理由を自分の文脈にだけ残す(PR 本文に書く義務は『経緯』としか書かれていない) → 反復2の俯瞰の役は、history/overview-1.md で自分が採った形だけを見て、同じ指摘を『以前に採らなかった指摘』と認識せずに規則に載せる → 振動するか、親が毎回同じ却下を繰り返す

8. `skill-dev/review-loop/fakes/claude:88`: 偽の claude で、FAKE_BAD_MODELS が未設定だと `"".split(",")` が `[""]` になる。そのため `--model` を渡さない呼び出しは、model が空文字になって『使えないモデル』の経路に入る。

   Failure scenario: 今後、`--model` を付けない事前確認の経路をテストする(あるいはスクリプトが条件付きで `--model` を省く)と、FAKE_BAD_MODELS を設定していないのに偽の claude が is_error と unrecognized_model を返す → テストが本物とは違う理由で失敗するか、誤った前提のまま通る

9. `skills/review-loop/scripts/review_loop.py:77`: LEGACY_STALE_LOCK_AFTER を75分と仮定しているが、main の履歴には STALE_LOCK_AFTER が95分(VERIFY_TIMEOUT を含む。e250b13 から 25048e2 まで)の版がある。

   Failure scenario: e250b13 の版で起動した試行が60分ほど経過したところで、新版を起動する → stale_after の無いロックを75分で古いとみなすので、80分を過ぎた時点で、実行中の旧版のロックを奪って interrupted として記録する。旧版の試行は最後に、他人のロックの下で状態を書く(配布されていなければ起きない)
===== ここまで: code-review =====

===== 観点: code-review-2 =====
PR #26 をレビューしました(`git diff main...HEAD` の範囲)。`skill-dev/review-loop/test.py` は手元で全て通ります。repo 直下や変更のあるディレクトリには CLAUDE.md が無く、ユーザー全体の CLAUDE.md は会話の仕方の規則なので、規約違反の指摘はありません。

9 findings, most severe first:

1. `skills/review-loop/scripts/review_loop.py:551`: 事前確認が init の直後に止めるのをやめ、モデルに 1 ターン分の応答を最後まで返させるようになった。この子には REVIEW_CONSTRAINT(作業ツリーを変えない制約)も --append-system-prompt も、ツールを絞る指定も渡していないため、ロックを取る前に、制約のない agent が worktree の中で 1 ターン動く。

   Failure scenario: 利用者の CLAUDE.md や hook に反応して、子がプロンプト 'ok' に対してツールを呼び、worktree を書き換えたとする。start の snapshot は事前確認の前に取ってあるので、40 分のレビューが終わったあとの find_contamination で contamination と判定され、無実のレビュー役のせいにされる。試行 1 回分の費用が無駄になり、連続失敗の回数も 1 つ進む。修正案は、事前確認に --max-turns 1 と REVIEW_CONSTRAINT を渡すか、ツールを無効にして起動すること。

2. `skills/review-loop/scripts/review_loop.py:934`: reviews.md の区切りは固定文字列 `===== 観点: <名前> =====` だけで、レビュー役の本文に同じ形の行があっても見分けられない。それなのに、SKILL.md の「表と役の対応」は、この区切りの名前を機械的に完全一致で照らすよう親に求めている。

   Failure scenario: review-loop 自身の PR のように、差分に区切りの文字列を含むコードがあると、レビュー役は `===== 観点: code-review =====` のような行をそのまま引用する。親が区切りを数えると、実在しない役の名前が混ざるか、引用された名前が実在の役と重なる。その結果、照合は誤った警告を出すか、欠けた役を見逃す。修正案は、区切りに試行ごとの nonce を入れること。

3. `skills/review-loop/scripts/review_loop.py:616`: 既定のモデルを、利用者の既定から別名の opus に固定した。ところが事前確認が止めるのは、決まった文言(UNKNOWN_MODEL_STDERR と UNKNOWN_MODEL_RESULT)に一致したときだけで、それ以外の理由で opus を使えないときは警告を出すだけで試行に進む。

   Failure scenario: プランや Bedrock/Vertex の設定で opus を使えず、エラーの文言が "There's an issue with the selected model" と違う場合、事前確認は warn を出して試行に進む。レビュー役は全て child_error で失敗し、3 反復で連続失敗の上限に達して --new-run が要る状態になる。以前の版は利用者の既定のモデルで動いていたので、これはこの PR で生じた後退。

4. `skills/review-loop/scripts/review_loop.py:1013`: 比べられるようにモデルを固定した、と説明しているのに、状態コメントに記録して比べているのは別名の 'opus' だけで、実際に解決されたモデル ID ではない。

   Failure scenario: 反復の途中で claude CLI が更新され、opus の指す実体が新しいモデルに変わったとする。記録は 'opus' のまま変わらないので、warn_option_change は警告を出さず、状態コメントの表にも差が現れない。反復どうしや PR どうしの比較が黙って崩れる。修正案は、事前確認の init または result に載る実際のモデル ID を記録すること。

5. `skills/review-loop/scripts/review_loop.py:1157`: 標準出力が、判定役のまとまった判定から、全レビュー役の生の出力をつないだものに変わった。親のコンテキストに大量のテキストが入る。

   Failure scenario: 既定の 3 観点に --focus を足すと、標準出力は数万文字になる。手順 4 で突き合わせるのは、文脈を引き継がない俯瞰の役で、reviews.md をファイルとして受け取る。それでも親は毎反復、同じ全文をバックグラウンドの出力として読み、コンテキストを消費するうえ、俯瞰の役より先に生の指摘に引きずられる。修正案は、標準出力を reviews.md のパスと、役ごとの件数の要約だけにすること。

6. `skills/review-loop/scripts/review_loop.py:551`: 事前確認で、毎反復 opus に 'ok' の応答を最後まで返させるようになった。この分のトークンは、試行のトークン数にも状態コメントの表にも記録されない。

   Failure scenario: 1 反復ごとに、Claude Code のシステムプロンプトと CLAUDE.md を含む opus の呼び出しが 1 回増える。同じシリーズで同じモデルが前の反復で completed になっていても、毎回呼ぶ。終了時の報告にある合計トークン数は、この分だけ少なく出る。修正案は、直前の試行が同じモデルで completed なら、モデルの確かめを省くこと。

7. `skills/review-loop/scripts/review_loop.py:804`: ロックごとに stale_after を記録し、LEGACY_STALE_LOCK_AFTER、型の検証、上限と下限の丸めまで足した。得られるのは、異常終了したあとの待ち時間が 75 分から 55 分に縮むことだけで、増えた複雑さに見合わない。

   Failure scenario: 版ごとに長さを変える仕組みと、手で編集された値への対策(bool、NaN、文字列、上限と下限の丸め)と、それぞれのテストを保守し続ける必要がある。STALE_LOCK_AFTER を、旧版も含めた最大の 75 分の定数のままにすれば、同じ安全性をコードを増やさずに得られる。

8. `skills/review-loop/scripts/review_loop.py:75`: 判定役を外したので、必要な時間は PREFLIGHT_TIMEOUT 2 分、REVIEW_TIMEOUT 40 分、MARGIN 5 分の合計 47 分になった。それなのに BASH_TIMEOUT と SKILL.md の起動の指定は 90 分のまま。

   Failure scenario: 見張り役が後始末できずに止まった、といった異常時に、親の Bash ツールが必要以上に 40 分以上待ち続ける。定数の意味(合計に対する余裕)とも食い違う。

9. `skills/review-loop/scripts/review_loop.py:1082`: warn_option_change で、model だけ別扱いの分岐がある(記録の無い版の判定、str かどうかの確かめ、1 要素のリストへの包み直し)。比べる値を正規化する小さな関数に寄せれば、観点や指示と同じ 1 本の比較で書ける。

   Failure scenario: 比べる項目を増やすたびに、分岐がさらに増える。今の形では perspectives と model だけが「記録の無い版の試行は飛ばす」扱いになっていて、項目ごとの扱いの違いを読み取りにくい。
===== ここまで: code-review-2 =====

===== 観点: security-review =====
# セキュリティレビュー結果: `review-loop-no-judge`

このブランチの変更で新たに入った、確信度 8 以上のセキュリティ上の問題は見つかりませんでした。報告すべき脆弱性はありません。

候補が出なかったため、偽陽性を除く手順(手順2)は行っていません。

## 調べて退けた候補

| 箇所 | 結論 | 理由 |
| --- | --- | --- |
| `--model` の値を `claude` の子プロセスに渡す処理(事前確認、`run_reviews`) | 該当なし | 引数をリストで渡しており、`shell=True` を使っていません。値は CLI フラグから来るので信頼できる入力です。状態コメントに記録した `model` は表示とログにしか使われず、コマンドの引数には戻りません。 |
| 状態コメントの `stale_after`(`lock_stale_after`) | 該当なし | `StateComment.read` が読むのは、自分のログインで書かれ、マーカーで始まるコメントだけです。第三者は値を差し込めません。値は `STALE_LOCK_AFTER` 以上 `BASH_TIMEOUT_MAX` 以下に収められます。数でない値、真偽値、NaN は旧版の値(75分)として扱われます。他人のロックを奪う経路はありません。 |
| 状態コメントの `attempts[].model` | 該当なし | `valid_state` で文字列であることを確かめています。読むのは自分のコメントだけで、表示とログにしか使われず、パスにもコマンドにも渡りません。 |
| `reviews.md` への書き込み(`write_reviews`) | 該当なし | パスは `workdir` の下の固定名です。`workdir` は既存の `make_workdir` が作り、所有者が自分であること、権限が 0700 であること、シンボリックリンクでないことを確かめています。役の名前は区切りの文字列に入るだけで、パストラバーサルは起きません。 |
| 判定役を外し、標準出力をレビュー役の生の出力に変えた点 | 該当なし | 秘密が新たに漏れる経路はありません。stderr の末尾をログに出す処理は以前からあり、今回は事前確認の警告に同じ扱いを足しただけです。レビュー役の出力が親のプロンプトに入る点は、除外の対象(AI のプロンプトへの入力の混入)に当たります。 |
| 事前確認で子プロセスの終了を待つ処理と `kill_group` | 該当なし | 自分が起動したプロセスグループを止めるだけです。 |

新たに入った pickle、yaml、`eval`、`shell=True` の使用はありませんでした。`json.loads` は以前からあり、自分のコメントだけに使われます。
===== ここまで: security-review =====

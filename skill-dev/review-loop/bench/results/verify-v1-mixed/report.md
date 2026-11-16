# 検証役の試し

渡した指摘 116 件のうち、結論が出たもの 78 件。費用 $8.23(API 換算)。

## 正解と一致した指摘(本物と分かっているもの)。題材の種類ごと

| | 再現した | 起きなかった | 実行では示せない | 挙動に関わらない | 計 |
|---|---|---|---|---|---|
| doc | 0 | 0 | 7 | 0 | 7 |
| python | 17 | 0 | 5 | 0 | 22 |
| shell | 4 | 0 | 0 | 0 | 4 |
| ts | 6 | 0 | 0 | 0 | 6 |
| **計** | 27 | 0 | 12 | 0 | 39 |

「実行では示せない」12 件を、検証役がコードや文面で追った結果: 成り立つ 9、成り立たない 1、分からない 2。

## 正解に無い指摘。分類役の分類ごと

| | 再現した | 起きなかった | 実行では示せない | 挙動に関わらない | 計 |
|---|---|---|---|---|---|
| 本物 | 2 | 0 | 0 | 0 | 2 |
| 些末 | 17 | 0 | 7 | 8 | 32 |
| 誤り | 2 | 0 | 2 | 0 | 4 |
| 未確定 | 1 | 0 | 0 | 0 | 1 |
| **計** | 22 | 0 | 9 | 8 | 39 |

## 本物なのに落ちた、または落ちかけたもの

- `sk-12/v5` S12-6(perspectives)→ **実行では示せない**・追った結果 does_not_hold
  - 根拠: 本物の CLI の出力を採るには外部の API を呼ぶ必要があり、ここでは実行していない。代わりに、インストール済みの CLI 2.1.325 のバイナリを読んだ。permission_denied イベントを作る2か所はどちらも tool_name, tool_use_id, agent_id, decision_reason_type, decision_reason_code, decision_reason, message だけを持ち、source も reason_type もない。そのため review_loop.py:325 の msg.get('source') == 'config' は成り立たず、どの拒否も self.denial に入って止まる。「許可リストにない拒否にも config が付いて停止が働かなくなる」は、このバージョンでは成り立たない。逆に、PR の「config の拒否では止めない」処理が働かない可能性が高い(本物の stream で確かめる必要あり)。child_error の切り捨てと config_denied の None キーは v2 と v3 で再現した
- `sk-12/v8` S12-1(perspectives)→ **実行では示せない**・追った結果 unclear
  - 根拠: 主の指摘は、本物の claude CLI が -p で「許可リストにないため拒否」したときに source="config" を付けるかどうかに懸かっている。これは外部の CLI の挙動で、本物の出力を採らないと確かめられない。コードの側を追った。review_loop.py:316-319 は source=="config" なら、reason_type を見ずに config_denied に入れ、止めない。watch_denials(:328-341)と check_result(:254-262)も config の拒否を止める対象から外す。したがって、許可リストにないための拒否にも config が付くなら、停止は働かなくなる。この条件付きの部分は成り立つ。前提が成り立つかは不明。fakes/claude の deny() は source=config, reason_type=subcommandResults を決め打ちで出している。副の指摘で child_error の詳細の切り捨ては再現した。stderr は `child_error: ... is_error True: 途中経過あああ…` で 500 字に切られ、最後の行の 'XYZ_REAL_ERROR' は出なかった(:263-264 で text[:500] を出しているため)。modelUsage
- `sk-12/v14` S12-1(code-review)→ **実行では示せない**・追った結果 unclear
  - 根拠: 本物の claude -p が、許可ルールのない呼び出しを拒否したときにイベントの source を何にするかは、外部の挙動で、この環境では確かめられない。コードを追うと、review_loop.py:308-309 は reason_type を見ずに source == "config" の拒否をすべて止めない側(config_denied)に入れ、watch_denials は warn の行と denials.txt に書くだけ。したがって『本物がこの場合に config を付けるなら、試行が止まらない』という条件付きの部分は成り立つ。テストの偽の claude(skill-dev/review-loop/fakes/claude:41-49)は source=config・reason_type=subcommandResults を自分で付けているだけで、本物の形と照らし合わせてはいない。前提の部分が本当かどうかが不明なので unclear とする

## 全件

- `sk-12/v1` [S12-2] code-review → **再現した**
  - 指摘: 10 findings, most severe first: 1. `skills/review-loop/scripts/review_loop.py:249`: A config denial event with no tool_use_id puts None into `seen`, so every permission_denials entry in result that also lacks tool_use_id is silently treated
  - 根拠: tool_use_id なしの組み合わせでは 'case1 (no id both) -> success: body' となり、拒否が素通りした。config 側に id があると 'AttemptFailed permission_denied | Bash {"command": "sandbox-nested"}' になる。seen に None が入り、id のない拒否をすべて見逃すことを確認した(review_loop.py:249-256, :309)。ただし手元の CLI 2.1.325 のバイナリでは、permission_denied イベントに常に tool_use_id を入れており、実際に起きる見込みは低い
- `sk-12/v2` [正解に無い・未確定] perspectives → **再現した**
  - 指摘: 本文が 500 字を超えると、最後の行にあるエラー文が切り捨てられ、失敗の原因が分からなくなります。 - 対処: `data.get("result")` を使うか、末尾を出すようにします。 - **`review_loop.py:237` — docstring の「modelUsage はセッションの累計で、どの行も同じ値になる」が矛盾している** - 累計なら、行ごとの値は増えていくはずで、同じ値にはなりません。 - テストの fake は、どの行にも同じ `model
  - 根拠: child_error の detail は554字で、'REAL' を含まない(False)。text[:500] がエラー文を切り捨てると分かった。判定役の経路では、つないだテキストの '### F1' が2回出て、末尾が '...なし\n\n変わりません' になる(verdict.md に混ざる)。拒否のあとに result の行がない場合は child_error になる(既存の挙動)。modelUsage が累計かどうかは本物の出力がないので確かめていない
- `sk-12/v3` [正解に無い・些末] mattpocock → **再現した**
  - 指摘: トを分けたほうが、レビューと切り戻しがしやすくなります。 ## Spec 仕様の各項目は実装されています。次の点はコードとテストで確認しました。 - 「最上位」かどうかは `parent_tool_use_id` で判定しています。 - 空の行を除き、出た順につないでいます。 - トークン数と成否は `tail.results[-1]`(最後の result の行)から取っています。 - 判定役も、観点と同じく `StreamTail`、`watch_denials`、`ch
  - 根拠: denials.txt は ['rev: Grep {}(reason_type rule)'] の1行だけで、Read が上書きで消えた。id のない result にしかない拒否の素通りも v1 で再現した。(c)2 の child_error 分類も 'AttemptFailed child_error | result の行がない(終了コード 1)' で確認した。(a) のテストの穴は挙動に関わらない。hook など source が config 以外のときに止めることは 'case6 hook -> permission_denied' で確認した
- `sk-12/v4` [S12-5] perspectives → **再現した**
  - 指摘: 順3に書く - **同じ箇所 — 書き込み系の操作も止めなくなった** - 子が `git push` や `Edit` を試み、deny ルールで拒否された場合も、以前は試行が失敗していましたが、今は続きます。 - 実際の変更は混入の確認と `head_changed` で捕まるので、安全上の穴ではありません。 - ただ「子が禁じた操作を試みた」という信号が `warn:` にしか残りません。拒否されたツールが読み取り系でなければ止める、という区別もありえます。 ## 並行
  - 根拠: 今のブランチは 'warn: ... 設定のルールで拒否された(試行は続ける): Bash {"command": "git push"}' を出し、check_result は success を返した。main では、permission_denials が1件でもあれば permission_denied を出していた(main の review_loop.py:250-252)。書き込み系の操作が deny ルールで拒否されても試行が止まらなくなったことを確認した
- `sk-12/v5` [S12-6] perspectives → **実行では示せない**(does_not_hold)
  - 指摘: ブランチの変更で `permission_denied` による停止はほぼ働かなくなります。 - 「source がなければ止める」という逃げ道は、source が付かない場合しか守りません。 - テストは fake が出す形の確認にとどまっています。次の2つを本物の CLI で採って比べ、fixture にすることを勧めます。 1. deny ルールに当たったときのイベント 2. 許可リストにないために拒否されたときのイベント - **`review_loop.py:263
  - 根拠: 本物の CLI の出力を採るには外部の API を呼ぶ必要があり、ここでは実行していない。代わりに、インストール済みの CLI 2.1.325 のバイナリを読んだ。permission_denied イベントを作る2か所はどちらも tool_name, tool_use_id, agent_id, decision_reason_type, decision_reason_code, decision_reason, message だけを持ち、source も reason_type もない。そのため review_loop.py:325 の msg.get('source') == 'config' は成り立たず、どの拒否も self.denial に入って止まる。「許可リストにない拒否にも config が付いて停止が働かなくなる」は、このバージョンでは成り立たない。逆に、PR の「
- `sk-12/v6` [正解に無い・些末] mattpocock → **挙動に関わらない**
  - 指摘: _judge` の新しい見張りのループ(poll → watch_denials → 時間切れの判定 → finish → check_result)は、`run_reviews` で子1つを見張る処理とほぼ同じです。1つの子を見張る関数にまとめられます。 - **Mysterious Name の可能性**: - `denial_summary` を `summary` に改名したことで、何の要約かが名前から消えました。 - `self.reported` は報告済みの設定
  - 根拠: run_judge と run_reviews の見張りのループの重複、denial_summary から summary への改名、self.reported の名前、文字列 'config' の散らばり、コミットの分け方はいずれも構造と命名の指摘で、挙動は変わらない。末尾の Spec の (a) はテストの穴の指摘
- `sk-12/v7` [正解に無い・些末] perspectives → **再現した**
  - 指摘: 。 - それ以外の並行性の問題は見当たりません。`denials.txt` への追記は単一プロセスの逐次処理で、`reported` による差分の管理にも二重書きはありません。判定役の待ち方を `wait` からポーリングに変えた点も、タイムアウトと後始末の流れは以前と同じです。 ## プライバシー - **`review_loop.py:327` 付近、`denials.txt` と stderr** - ツールの入力が最大 200 字、ローカルの一時ディレクトリと std
  - 根拠: rc=0 で、試行は続いた。stderr に `warn: review security-review: 設定のルールで拒否された(試行は続ける): Bash {"command": "curl -H 'Authorization: Bearer ghp_SECRETTOKEN123' x"}(reason_type rule)` が出た。作業ディレクトリ(TMPDIR の下)の denials.txt にも同じ行が平文で残った。コマンドに直書きしたトークンが、拒否されるとローカルのファイルと stderr に残る、という指摘どおり。状態コメントへ外に出る経路はこの実行では見ていない(指摘も外には出ないと言っている)。前半の「ほかの並行性の問題はない」は、問題がないという主張なので、検証の対象にしていない。
- `sk-12/v8` [S12-1] perspectives → **実行では示せない**(unclear)
  - 指摘: `SKILL.md:103` — `source == "config"` かどうかで止めるかを決める前提が確かめられていない(最も重要)** - `-p` では、許可リストにないコマンドは確認なしで拒否されます。この拒否に `source: "config"` が付くかどうかは、本物の出力で確かめられていません。 - fake の `reason_type="subcommandResults"` は「複合コマンドのサブコマンドごとの判定」を表すものです。このサブコマンド判
  - 根拠: 主の指摘は、本物の claude CLI が -p で「許可リストにないため拒否」したときに source="config" を付けるかどうかに懸かっている。これは外部の CLI の挙動で、本物の出力を採らないと確かめられない。コードの側を追った。review_loop.py:316-319 は source=="config" なら、reason_type を見ずに config_denied に入れ、止めない。watch_denials(:328-341)と check_result(:254-262)も config の拒否を止める対象から外す。したがって、許可リストにないための拒否にも config が付くなら、停止は働かなくなる。この条件付きの部分は成り立つ。前提が成り立つかは不明。fakes/claude の deny() は source=config, reason_typ
- `sk-12/v9` [正解に無い・些末] perspectives → **再現した**
  - 指摘: - 根拠の弱さ: フェイク(`fakes/claude` の `deny()`)は `source="config", reason_type="subcommandResults"` を決め打ちで出しています。本物の CLI がどちらの拒否にどの値を付けるかは、テストでは確かめられていません。 - 対策: 本物の claude で「許可ルールがないだけのコマンド」と「deny ルールに当たるコマンド」をそれぞれ `-p` で流し、`source` と `reason_typ
  - 根拠: (1) rc=0 で試行は完了し、stderr の warn 1行と denials.txt に `Bash {"command": "git push origin HEAD"}` が残るだけだった。main では StreamTail がどの permission_denied でも止めていた(main の :292)ので、合図が警告に弱まったのは指摘どおり。(2) verdict.md は `…## 競合\n\nなし\n```\n\n判定は前のメッセージのとおりです。\n` になった。閉じフェンスと余計な文が判定に残った。(3) denials.txt と stderr には `cat secrets.txt` の1件だけが残り、`cat .env` は消えた。config_denied[None] が上書きされている(review_loop.py:317)。fragment の冒頭
- `sk-12/v10` [S12-5] code-review → **再現した**
  - 指摘: iews could also use per child, would remove the duplication. The first watch_denials call in run_reviews (running=False) is redundant with the one after finish. 7. `skills/review-loop/scripts/review_loop.py:707`: Config denials are only wri
  - 根拠: rc=1 で、`failed: child_error: review code-review` になった。security-review の config の拒否(cat .env)は stderr の warn にも denials.txt にも出ず、denials.txt は作られなかった。run_reviews(review_loop.py:704-717)は子の順に poll と watch_denials を回すので、先の子の check_result が例外を出すと、後の子の tail は読まれないまま kill_all になる。項目8の docstring の矛盾はコメントの指摘で、挙動には関わらない。
- `sk-12/v11` [S12-3] prove → **再現した**
  - 指摘: レビューで確かめたのは2点で、どちらも判定役(judge)が `result` の行を複数出したときに起きます。今回の変更で、判定役の `result` の行もすべてつなぐようになったことが原因です。 この2点のほかに、次のものは指摘として証明できませんでした。 - 既存のテスト(`TMPDIR=$PWD/scratch/tmp python3 skill-dev/review-loop/test.py`)は「全て成功」でした。 - 判定役が設定のルール以外で拒否されて実行を
  - 根拠: rc=0 になり、stdout と verdict.md は `## 指摘 … ## 競合\n\nなし\n```\n\n判定は前のメッセージのとおりです。\n` だった。check_result(:249)が result の行を \n\n でつなぐため、末尾がフェンスで終わらなくなる。そのため run_judge(:806-808)の `\n```\s*$` が当たらず、閉じフェンスと余計な文が判定に残る。main は判定役の出力に --output-format json を使い、最後の result だけを見ていた。この入力なら見出しがなく、no_output で失敗する。今回の変更で、壊れた判定が成功として通るようになった。
- `sk-12/v12` [S12-3] code-review → **再現した**
  - 指摘: ict\n```markdown\n## 指摘 ...\n```' and result 2 = 'その内容から変わりません'. In the joined text, `\n```\s*$` does not match, so verdict ends with '```\n\nその内容から変わりません'. That broken fence and extra sentence go to stdout and verdict.md, which the parent 
  - 根拠: 項目4の fence: verdict.md の末尾に ```\n\n判定は前のメッセージのとおりです。 が残った。項目5の draft: rc=0 で、verdict.md は `## 指摘\n\n### F1: 下書きの指摘\n\n## 競合\n\n### C1: 下書きの競合\n\n## 指摘\n\n### F1: 確定の指摘…` になり、見出しの組が2つできた。min(start)(:806)が下書きの見出しを指すため。項目6の nonewline: rc=1、`failed: child_error: judge / result の行がない(終了コード 0)`。StreamTail.poll(:302-303)は最後の改行までしか読まないので、改行のない最後の行は捨てられる。main の判定役は --output-format json だったので、この経路はなかった。ただし、
- `sk-12/v13` [正解に無い・誤り] code-review → **再現した**
  - 指摘: f sections with different content, and the parent cannot tell which F1 or C1 is the real one. Before this change only the last result was used, so this did not happen. The review side can also end up passing duplicated report bodies to the 
  - 根拠: (6) 末尾に改行のない result の行は読まれず、FAIL kind=child_error detail='result の行がない(終了コード 0)' になった。改行の手前までしか読まない処理(review_loop.py:293)が原因で、プロセスが終わった後の tail.poll() でも読まれない。判定役は今回の変更で json.load から StreamTail に移ったので、判定役にとっては新しく入った退行。(7) 途中の行が is_error=true でも OK text='途中で切れた\n\n変わりません' になり、成功として扱われた。(5) 2つの result の行が両方つながって返り、判定役の場合は '## 指摘' が2回入った本文になった(A_judge)
- `sk-12/v14` [S12-1] code-review → **実行では示せない**(unclear)
  - 指摘: 8 findings, most severe first: 1. `skills/review-loop/scripts/review_loop.py:307`: Any denial with source == "config" is now non-fatal. If real claude in -p mode also tags the ordinary case (a call with no allow rule is turned into a deny, 
  - 根拠: 本物の claude -p が、許可ルールのない呼び出しを拒否したときにイベントの source を何にするかは、外部の挙動で、この環境では確かめられない。コードを追うと、review_loop.py:308-309 は reason_type を見ずに source == "config" の拒否をすべて止めない側(config_denied)に入れ、watch_denials は warn の行と denials.txt に書くだけ。したがって『本物がこの場合に config を付けるなら、試行が止まらない』という条件付きの部分は成り立つ。テストの偽の claude(skill-dev/review-loop/fakes/claude:41-49)は source=config・reason_type=subcommandResults を自分で付けているだけで、本物の形と照らし合わせ
- `sk-12/v15` [正解に無い・本物] code-review → **再現した**
  - 指摘: → the attempt does not stop, the reviewer returns 'no findings' without having read the diff, the judge treats it as a valid review, and only a warn line and denials.txt are left. This contradicts the SKILL.md precondition that 'calls to to
  - 根拠: 返った値は 'Standards: 指摘 A, B\n\n最終: 指摘 A, C' で、取り下げた B も重複した A も残った(result.md にも同じものが書かれる)。判定役の場合は '## 指摘\n1. B\n## 裁定\nx\n\n## 指摘\n1. C\n## 裁定\ny' になった。run_judge は最初の見出しから後ろを全部 verdict にするので、'## 指摘' が2つある判定がそのまま渡る。判定役がどちらを採るかはモデル次第なので実行では示していないが、中身が重複したり食い違ったりすることは示せた
- `sk-12/v16` [S12-2] mattpocock → **再現した**
  - 指摘: judge.*` に変わりました。`verdict.md` との衝突を避けるための変更と読め、`SKILL.md` にも反映されているので問題ありません。 **(c) 実装の誤りが疑われるもの(境界条件)** 1. `tool_use_id` のない拒否を取りこぼすことがあります。私もコードで裏を取りました(`review_loop.py:308-309` と `:249-256`)。 - `tool_use_id` のない config の拒否は、`config_denie
  - 根拠: E_none_seen は OK text='指摘なし' になり、result にだけ載った拒否で止まらなかった。seen に None が入ったため。tool_use_id がある E_control では FAIL kind=permission_denied で止まる。E_overwrite では warn の行も denials.txt も1件だけで、2件目は config_denied[None] の上書きで消えた。どちらも指摘どおり。本物の stream で tool_use_id が欠けることがあるかは確かめていない。テストの不安定さは、5回とも rc=0・FAIL=0(各回 約115秒)で再現しなかった
- `sk-12/v17` [S12-6] code-review → **再現した**
  - 指摘: d adds C → result.md and judge-input.md contain both the retracted B and the duplicate A, and the judge adopts the retracted finding. For the judge itself, a draft verdict plus a final verdict both go into verdict.md, giving two '## 指摘' sec
  - 根拠: (3) child_error の detail は先頭の途中経過の文だけで500字が埋まり、REAL_ERROR_CAUSE は出なかった(review_loop.py:263 の text[:500])。(4) tool_use_id のない config の拒否があると、result にしか載っていない tool_use_id のない拒否が既に見たものとして扱われ、試行は OK で通った。指摘の失敗シナリオのとおり
- `sk-12/v18` [正解に無い・些末] mattpocock → **実行では示せない**(holds)
  - 指摘: **中身が読めない名前**: - `StreamTail.summary(self, d)` は、旧名の `denial_summary` にあった「拒否の」という意味が落ちています。 - `self.reported` の中身は「報告済みの config の拒否の件数」です。 - **1つの関数が多くを抱えている**: `check_result` は、テキストの連結、`result.md` への書き込み、トークン数の加算、拒否の統合と成否の判定の4つを受け持っています。た
  - 根拠: 挙動は stopped kind=permission_denied で、config 以外の source では止まることを確かめた。指摘の中心は、この挙動が文書に書かれていないこと。SKILL.md:103 には『source が config では止めない』と『source がなければ止める側に倒す』しか書かれておらず、hook のように config でも空でもない source が止まることは明記されていない(:24 も同じ)。これは文書の書き方の問題で、実行では示せないので not_runnable とする。文面を追った結果は holds。名前(summary、reported)や check_result が抱える責務の多さについての指摘は、挙動に関わらない。同じ指摘の2番(tool_use_id のない拒否を取りこぼす)は、sk-12/v16 で再現している
- `sk-12/v19` [正解に無い・些末] mattpocock → **挙動に関わらない**
  - 指摘: - 終わったあとの `poll` → `watch_denials(running=False)` → `check_result` - **Feature Envy の可能性: `check_result` の拒否の統合部分。** `tail.config_denied`、`tail.denial`、`tail.tool_inputs`、`tail.results` を直接たどっています。`StreamTail.blocking_denials()` のように Stream
  - 根拠: 事実関係はコードと一致する。check_result(review_loop.py:249-253)は tail.config_denied・tail.denial・tail.tool_inputs・tail.results を直接たどっており、{tool_name, tool_input: tail.tool_inputs.get(...)} の組み立ては StreamTail.summary(317-319行)にもある。test.py:513 は denials.txt を with なしの open(...).read() で読み、ほかの open は with を使っている(58,60,86,145 行など)。wd = err.rstrip().splitlines()[-1] は 206 行と 512 行に出てくる(494 行にも同じ形がある)。どれも Feature Envy、
- `sk-12/v20` [正解に無い・些末] mattpocock → **挙動に関わらない**
  - 指摘: コードの慣習で照合しました。 ## Standards ハード違反はありません。以下はすべて判断事項です。 - **標準との照合** - 新しい振る舞いには、偽の `claude` のモードとテストが付いています。README の「スクリプトの振る舞いをテストで検証する」方針に合っています。 - `SKILL.md` は frontmatter を変えておらず、追記した文の文体と用語は既存に揃っています。 - `judge.*` と `review-*.result.md` 
  - 根拠: 事実関係はコードと一致する。差分で denial_summary() が summary(self, d) に改名されている。self.reported(284,323-324行)は報告済みの設定拒否の件数。watch_denials(328行)は記録と、running かつ tail.denial のときの AttemptFailed の送出(340-341行)を兼ねている。"config" は 308 行などにリテラルとして書かれている。check_result の拒否を集める処理は StreamTail のデータだけを使っている。挙げられているのは、命名(Mysterious Name)、Feature Envy、重複、Primitive Obsession、コミットの分け方といった構造や好みの話で、どれも実行時の挙動を変えない。Spec の部分は文が途中で切れていて、評価できる主張
- `sk-13/v1` [S13-3] prove → **再現した**
  - 指摘: 06:02:49Z', 'result': 'completed', 'tokens': {'input': 14000, 'cache_read': 8000, 'output': 1200}, 'iter': 1} table row = | 5268b3f | 2026-11-15T06:02:49Z | completed(反復 1) | 1.4万(うちキャッシュ読み込み 8000) | 1200 | ``` **出るべきだった出力** - 既定と違う観点で回したこと
  - 根拠: (A) rc=0。子には '/code-review low 7' が渡ったが、attempt は {sha, at, result:'completed', tokens, iter:1} で perspectives が無い。表の行は '| 39e1bd9 | … | completed(反復 1) | 1.4万(うちキャッシュ読み込み 8000) | 1200 |' で、既定の試行と見分けがつかない。比べているのがスキル名の並びだけ(review_loop.py:962-964)だからである。(H) valid_state=True。描画は 'completed(反復 1)、観点 s, e, c, u, r, i, t, y, -, r, e, v, i, e, w'。valid_state の検査(review_loop.py:548、`all(isinstance(n,str) 
- `sk-13/v2` [正解に無い・些末] mattpocock → **再現した**
  - 指摘: for s in perspectives]` を、`review_config` の中で2回、`iterate` でもう1回作っています(`review_loop.py:962`)。`review_config` で1回作れば済みます。 - **いつも一緒に渡る引数:** `perspectives` と `instructions` は揃って `run_reviews` に渡り、`instructions` は `run_judge` にも渡ります。まとめる余地はあります
  - 根拠: Spec 1:(A) 引数だけ変えても attempt に perspectives が残らず、表の行は既定と同じだった。Spec 3:(C) rc=0 で事前確認と重複検査を通り、子に渡ったプロンプトは '/ code-review high 7' だった。'/' の後に空白が入ったスラッシュコマンドになる(review_loop.py:375 は split()[0]、757 は '/' + expand(spec))。Spec 2(JUDGE_PROMPT が変わっていない)は事実だが、判定役の LLM がどう読むかは実行では示せない(v4 を参照)。リスト内包を2回作ること、iterate の既定値 None が使われないことも事実だが、挙動には関わらない。
- `sk-13/v3` [正解に無い・些末] perspectives → **再現した**
  - 指摘: ューされなかった観点と範囲も報告する」としていますが、その根拠は親エージェントの記憶にしかありません。また `SKILL.md:57` のとおり、スクリプトは反復をまたいでオプションを覚えません。付け忘れて既定に戻った反復と、絞った反復が同じシリーズに混ざっても、収束の判断のときに区別できません。対策として、`attempt` に `instructed: [観点の名前]` を記録し、表にも載せることを勧めます。前の試行と観点や指示が変わったときに `warn:` を出すとな
  - 根拠: rc=0。attempt は {sha, at, result:'completed', tokens, iter:4} で、指示についての記録は何も無い。表の行も 'completed(反復 4) | …' で、範囲を絞った反復を後から見分けられない。これは指摘どおり。なお、REVIEW_CONSTRAINT はシステムプロンプトの先頭に残っていた(True)ので、そこは実害がない。テストが抜けているという指摘は、それ自体は挙動に関わらない。
- `sk-13/v4` [正解に無い・些末] mattpocock → **実行では示せない**(holds)
  - 指摘: rate`、`run_reviews`、`run_judge` へ常に組で渡っています。`run_reviews` の引数は8個になりました。小さな型にまとめる候補です。ただ、既存コードは `start` や `ctx` を辞書で回しているので、辞書に揃えるのも筋は通ります。 3. **Mysterious Name(軽微)**: - 関数 `review_constraint(instruction)` は、定数 `REVIEW_CONSTRAINT` と同じ名前なのに、指
  - 根拠: 中心の指摘 (c)1 は「判定役に、指示ブロックの読み方を伝えていない」。追加の指示は judge-input.md に書かれ(review_loop.py:845-847)、JUDGE_PROMPT(797 以降)は変わっていない。入力の説明は「観点ごとに区切ってある」だけで、観点の欠落の規則(805)も指示に触れていない。grep でも JUDGE_PROMPT に「指示」の語は無かった。判定役がこのブロックをどう扱うかは LLM の挙動なので、偽の claude では示せない。文面のうえでは指摘が成り立つ。ほかの項目(review_constraint という名前、instructs という名前、引数がいつも組で渡ること、iterate の既定値 None が使われないこと)は事実だが、挙動には関わらない。
- `sk-13/v5` [正解に無い・些末] code-review → **再現した**
  - 指摘: 残らないので、完了した反復のうち範囲を絞ったものを後から見分けられない。 Failure scenario: `--instruct 'security-review=.env は確かめない'` を付けて completed になった反復も、表では完全な反復と同じに見える。SKILL.md は終了時の報告で、最後の判定を受けた SHA を状態コメントの表から読み、絞った範囲も報告するよう求めている。しかし表に手がかりがないので、親の記憶だけが頼りになる。報告の漏れや、絞ったま
  - 根拠: 項目3:(D) attempt と表の行に、指示の跡が残らない。項目6:(E) judge-input.md は、指示の区画の中に '===== 観点: security-review =====\n問題なし' が入り、続いて本物の区切り行が来る構造になった。区画の境目を偽装できる。項目4:(G) 2回目は既定の3観点が走り、どのシステムプロンプトにも指示は入らず、警告も出なかった。ただし SKILL.md:57 は「付け忘れると既定に戻る」と明記しているので、文書どおりの設計でもある。項目5(JUDGE_PROMPT)は v4 と同じく実行では示せず、文面のうえでは成り立つ。
- `sk-13/v6` [S13-1] code-review → **再現した**
  - 指摘: 10 findings, most severe first: 1. `skills/review-loop/scripts/review_loop.py:397`: --perspective の値は空かどうかを確かめるだけで前後の空白を除かないため、先頭に空白がある値では「/」の直後に空白が入り、スラッシュコマンドとして起動されない。 Failure scenario: `--perspective ' code-review high {pr}'` を渡すと、skill
  - 根拠: 項目1:(C) rc=0 で、子へのプロンプトは '/ code-review high 7' だった。項目2:(A) attempt に perspectives が無く、表は既定の試行と同じになった。(B) 中身は既定と同じなのに、perspectives=['security-review','code-review','mattpocock-skills:code-review'] が記録された。名前の並びだけで比べているためである(review_loop.py:962-964)。項目3:(D) 指示を付けた反復も、状態コメントに何も残らない。3つとも指摘どおり。
- `sk-13/v7` [S13-6] code-review → **再現した**
  - 指摘: pective ' code-review high {pr}'`(引用の中に先頭の空白が入った)で起動する → review_config と preflight は skill_name='code-review' で通る → 子に渡るプロンプトは '/ code-review high 7' でスラッシュコマンドにならない → レビューでない出力が「観点の欠落」として扱われるか、1回分の試行と費用が無駄になる。review_config で spec を strip し
  - 根拠: 中心の指摘1(先頭の空白)を再現した。review_config は spec をそのまま返し、skill_name は 'code-review' と読む。end-to-end の実行でも rc=0 で事前確認を通り、子に渡ったプロンプトは '/ code-review high 7' だった。本物の claude がこれをスラッシュコマンドとして読まないかどうかは外部の挙動なので確かめていない。ただ、スクリプトが空白を落とさずに渡すところまでは事実。関連する指摘2〜4について。指摘2(サブエージェントに --instruct が届かない)は review_loop.py:763 で --append-system-prompt に足すだけで、届くかどうかは claude の挙動に依るため実行では確かめていない。指摘3は '指示' も '追加' も JUDGE_PROMPT に出てこない
- `sk-13/v8` [S13-5] mattpocock → **再現した**
  - 指摘: 観点で回した試行は、状態コメントの表に観点の名前を載せる」 - `names != [skill_name(s) for s in PERSPECTIVES]` は順序も含めて比べています。そのため、既定を並べ替えて渡しただけで表に名前が載ります。 - 逆に、`code-review max {pr}` のように引数だけを変えた場合は、中身が違っても載りません。規約の担当も同じ点に気づいています。 - 順序を問わない比較にすれば前者は直ります。後者は「名前を載せる」という仕様
  - 根拠: 逆順にすると ['mattpocock-skills:code-review','security-review','code-review'] が記録され、表に名前が出る。引数だけを変えると記録されない(None)。valid_state は文字列の perspectives に True を返した。render の行は '| aaaaaaa | ... | ok、観点 c, o, d, e, -, r, e, v, i, e, w | ...' になった。3点とも指摘どおりの挙動
- `sk-13/v9` [正解に無い・些末] mattpocock → **再現した**
  - 指摘: :** ありません。 - SKILL.md の frontmatter は変わっていません。 - 新しい振る舞いは、既存と同じく `test.py` に偽の `claude`/`gh` を使って追加されています。 - 誤りは既存と同じく `Precondition` で終了コード2にしています。 **既存の書き方とのずれ(判断事項):** 1. **エラー系の新しいテストが終了コードしか見ていない。** 既存のテストは `rc == 2 and "重複" in err` のよ
  - 根拠: 仕様とのずれ1(引数だけを変えた試行が表に載らない)を再現した。引数だけを変えた spec では names が既定と一致し、attempt に perspectives が付かない。同じ名前を並べ替えたものは載る。残りは挙動に関わらない。エラー系のテストは rc==2 しか見ておらず、メッセージを確かめていない(テストの書き方の問題)。system_prompt がファイルの途中にある、内包表記を繰り返している(409, 411, 962, 963行)、iterate の既定値を使っていない(呼ぶのは 1076 行の main だけで、常に両方を渡している)、の3つは事実だが、構造の好みにとどまる
- `sk-13/v10` [S13-1] mattpocock → **再現した**
  - 指摘: OMPT` は変わっていません。そのため「観点の欠落」や「指摘を捨てない」という規則と、利用者の指示との関係が判定役任せです。 - 例えば、レビュー役が指示を守らず外された範囲を指摘したとき、判定役がそれを捨てるのか残すのかが決まっていません。 3. **先頭に空白がある `--perspective` が、事前の確認を通ったあとで壊れる。** - `' code-review high {pr}'` は、`skill_name` が `split()[0]` を使う(`re
  - 根拠: 指摘3(先頭の空白)を再現した。rc=0 で通り、子のプロンプトは '/ code-review high 7' だった。空白だけの spec は止まるが、先頭に空白がある spec は止まらない。指摘2(JUDGE_PROMPT が指示の扱いを定めていない)も文面として成り立つ。JUDGE_PROMPT に '指示' も '追加' も出てこない。判定役が実際に取り違えるかは LLM の挙動なので、実行では示せない。欠けているテストの指摘(空の指示、観点の重複を確かめるテストが無い)は挙動に関わらない
- `sk-13/v11` [正解に無い・些末] mattpocock → **挙動に関わらない**
  - 指摘: st.py に、正常系、指示の渡し先、状態への記録、終了コード2の各ケースが足されています。 - 引数の誤りは、ロックを取る前に `Precondition` で終了コード2にしています。既存の書き方と同じです。 **スメル(どれも判断の問題):** 1. **Duplicated Code**: `[skill_name(s) for s in ...]` が4か所にあります。`review_config` の中だけで2回あり、しかもループの中で毎回作り直しています。`re
  - 根拠: 重複は 409, 411, 962, 963 行の4か所で、指摘どおり。409 行はループの中で毎回作り直している。iterate の既定値 specs=None, instructs=None は、唯一の呼び出し元(1076行の main)では使われない。命名(review_constraint / instructs)、引数をまとめる候補、『指示を優先』の一文がスコープクリープかどうか、はいずれも構造や仕様の判断で、挙動の誤りではない
- `sk-13/v12` [S13-5] code-review → **再現した**
  - 指摘: ruct は状態にも残らないので後から気づけない(根本は、シリーズの設定を状態コメントに持たせていないこと)。 Failure scenario: 反復1で --instruct を付けて permission_denied を避ける → 反復2で親が付け忘れる → 同じ拒否で再び失敗する。あるいは、外したはずの範囲の指摘が復活し、判定が行ったり来たりして見える。表からは原因を区別できない。run_id ごとに観点と指示を状態に保存し、次からはそれを既定にする設計にすれば防げ
  - 根拠: 指摘6を再現した。valid_state は True を返し、表には '観点 c, o, d, e, -, ...' と出た。指摘7も再現した。システムプロンプトの末尾は文字どおりの 'PR #{pr} で削除したファイルは見ない' で、{pr} は置き換わらない(expand を呼ぶのは spec だけ)。指摘5(--instruct が状態に残らず、反復2で付け忘れると再び拒否される)は、attempt に instructions を保存するコードが無いことをコードで確認した。付け忘れるかどうかは親の LLM の振る舞いに依る。指摘8(551行と558行の run(wt,'--new-run') の重複)は事実だが、テストの冗長さにとどまり、挙動には関わらない
- `sk-13/v13` [正解に無い・些末] mattpocock → **再現した**
  - 指摘: 利用者の指示があるときだけ付ける、以後の反復でも同じものを付ける、権限の拒否で止まったときの提案として使う)がすべて書かれています。 **(b) 仕様にない振る舞い(小さく、方向は妥当)** - レビュー役のシステムプロンプトに「スキルの手順と食い違うときは、この指示を優先」とあります(`review_loop.py:749`)。仕様は指示を「足す」とだけ言っています。 - 終了時の報告に、レビューされなかった観点と範囲が加わっています。 **(a) テストで確かめていない箇
  - 根拠: rc=0。最後の試行は {sha, at, result: completed, tokens, iter: 1} だけで、perspectives も、指示があったことを示す項目もない。コメントの表も『completed(反復 1)』だけで、『指示』の語は本文にない。--instruct だけで範囲を絞った試行は、後から状態コメントを見ても区別できない。指摘どおり(指示の本文 .env が載らないことも確かめた)。断片にある (a) のテスト不足と (b) の文言は、挙動の指摘ではない
- `sk-13/v14` [S13-8] perspectives → **再現した**
  - 指摘: e-review` と読まれ、`:397` の空チェックも事前確認も通ります。 - ところが子に渡すプロンプトは `"/" + expand(spec, pr)` で、`/ code-review high 7` になります。これはスラッシュコマンドとして解釈されません。 - 結果として子はスキルを起動しないまま普通の文章として応答します。判定役がそれを「観点の欠落」と拾えれば分かりますが、費用をかけた試行がまるごと無駄になります。 - 直し方: `review_config
  - 根拠: 先頭が空白の観点: rc=0。skill_name が split で空白を落とすので、事前確認を通る。子に渡ったプロンプトは '/ code-review high 7'(スラッシュの後に空白)。本物の claude がこれをスラッシュコマンドとして扱わないかどうかは、偽の claude では確かめられない(偽の claude は lstrip('/') で名前を読む)。それでも、壊れた形のまま子に渡ることは確かめた。C: 引数だけを medium に変えても rc=0 で、attempt に perspectives がない(表に載らない)。C2: 並べ替えただけでも perspectives=['security-review','code-review','mattpocock-skills:code-review'] が記録される。比較が名前の並びだけ、という指摘も成り立つ
- `sk-13/v15` [正解に無い・些末] perspectives → **再現した**
  - 指摘: 既存の PR 単位のロックで直列化されます。 - **設計上の注意**: 観点の構成を途中で変えても、反復回数・連続失敗の数(958行)は同じシリーズで数え続けます。観点を外して失敗を回避した試行も、連続失敗のリセットに数えます。これで良いかは判断が分かれるので、少なくとも SKILL.md に書いておく価値があります。 ## プライバシー - 指示の本文を状態コメント(PR 上で公開される)に載せず、観点の名前だけを載せる設計は妥当です。指示には `.env` のような機微
  - 根拠: 失敗の直後は consecutive_failures=1、iter=1。security-review を外して回すと rc=0 で、consecutive_failures=0 に戻り、iter=2。run_id は同じシリーズのまま。観点を外して失敗を避けた試行でも、連続失敗が消え、同じシリーズの反復に数える。指摘どおり。断片にあるほかの点(プライバシーのテストが無い、ps で argv が見える、オプションの再指定を親の記憶に頼る、SKILL.md:116 の提案の書き方)は、設計とテストの指摘で、ここでは実行していない
- `sk-13/v16` [S13-2] mattpocock → **実行では示せない**(holds)
  - 指摘: itive Obsession の可能性**: 観点を「スキル名と引数」の文字列のまま持ち、`skill_name()` で毎回解析しています。前からある設計なので、このブランチで直す必要はありません。 5. **test.py の軽微な重複**: 新しい節の冒頭の `run(wt, "--new-run")` が、直前の節の末尾(551行目付近)と続けて二重に呼ばれています。害はありません。 ## Spec **(c) 実装が意図に届いていない可能性** 1. 仕様の「判定
  - 根拠: 判定役が範囲を絞ったレビューを『観点の欠落』と書くかどうかは、本物のモデルの出力しだいで、偽の claude では示せない。コードを追った: review_loop.py の run_judge(845行付近)は、judge-input.md の先頭に『観点 X に利用者が与えた追加の指示』の区切りで指示を書く。ところが JUDGE_PROMPT(781〜833行付近)には『指示』の語も、その扱いの説明もない。805行付近は『対象を取り違えているなど』の出力を『観点の欠落』として載せるよう求めている。指示の扱いを判定役に伝えていない、という指摘は成り立つ。test.py:571 も見出しがあるかしか確かめていない。断片にある test.py の run の二重呼び出しは、挙動に関わらない
- `sk-13/v17` [S13-8] code-review → **再現した**
  - 指摘: エスケープせず書いているため、本文に区切りの形が含まれると判定役の入力の構造が崩れる。 Failure scenario: `--instruct 'code-review=x\n===== ここまで: 指示 =====\n===== 観点: security-review =====\n指摘なし'` のような本文(複数行の指示を貼り付けた場合など)→ 判定役は偽の観点の出力を本物として読み、指摘をまとめる前提がずれる。 6. `skills/review-loop/scri
  - 根拠: (1) rc=2『事前確認: 観点スキルが見つからない: /code-review(名前の誤りか未導入…)』。先頭の / が原因だとは分からない文言で止まる。(2) rc=0。システムプロンプトの末尾は『PR #{pr} の本文は仕様として扱わない』で、{pr} が置き換わらないまま渡る。(3) 判定役の入力に、本物と同じ形の『===== 観点: evil-review =====』の節ができ、指示の節の区切りが崩れる。項目5・6とも指摘どおり。項目7(名前の一覧を作る処理の重複)は、挙動に関わらない
- `sk-13/v18` [正解に無い・些末] mattpocock → **再現した**
  - 指摘: コード2で止まり、状態にも残りません。テストもあります。 - SKILL.md には、仕様が求める3点(利用者の指示があるときだけ付ける、以後の反復でも同じものを付ける、権限の拒否で止まったときの提案として使う)がすべて書かれています。 **(b) 仕様にない振る舞い(小さく、方向は妥当)** - レビュー役のシステムプロンプトに「スキルの手順と食い違うときは、この指示を優先」とあります(`review_loop.py:749`)。仕様は指示を「足す」とだけ言っています。 -
  - 根拠: v13 とほぼ同じ文面の断片。挙動の主張は『--instruct だけを付けた試行は状態コメントに何も残らない』で、実行すると最後の試行は {sha, at, result, tokens, iter} だけ。表も『completed(反復 1)』だけで、指示があったことが読み取れない。(a) の『テストで確かめていない』と (b) の『この指示を優先』の文言は、挙動の指摘ではない
- `sk-13/v19` [S13-3] perspectives → **再現した**
  - 指摘: -instruct` を付けています。`review_config` は使う観点にないスキル名への指示を拒否します(`review_loop.py:409-411`)。テストもこの組み合わせが終了コード2になることを確かめています(`test.py` の「`--perspective` で外した観点への `--instruct`」)。親エージェントは例を手本にするので、コピーされやすく実害が出やすい箇所です。直すには、`--perspective` に `security-r
  - 根拠: この断片の先頭の主張(SKILL.md の例)は再現した。review_config(['code-review high {pr}','mattpocock-skills:code-review PR #{pr}'], ['security-review=...']) は Precondition『--instruct のスキル security-review が観点にない』を投げる。iterate ではこれが終了コード2になる。続く主張も実行で確かめた。(1) 962-964: 引数だけ変えた『code-review low {pr}』の組は記録されない(False)。既定と同じ観点を並べ替えただけの組は記録される(True)。(2) 548: perspectives が "abc" でも valid_state は True を返し、表には『completed、観点 a, b, c
- `sk-13/v20` [正解に無い・些末] perspectives → **挙動に関わらない**
  - 指摘: 出しが記録されていない(キーがない)ときも成り立ちます。 - 「ほかの観点には渡さない」を確かめたいなら、キーがあることも検査に入れます(`"mattpocock-skills:code-review" in by_name and ...`)。 - `:569` の `by_name.get("code-review", "")` は空文字のときに失敗する側なので、問題ありません。 - **テストが欠けているもの** - 前後に空白がある `--perspective`(正
  - 根拠: test.py:570 の `by_name.get("mattpocock-skills:code-review", "x")` は、キーがなければ『x』を返し、検査が通る。これはコードを読めば分かる事実だが、指摘はテストの強さと、無いテストについてのものなので、スクリプトの挙動には関わらない。それに、直前の検査(:564-565)で、両方の観点の review 呼び出しが記録されていることを確かめている。補足の節(並行性、プライバシー、入力の誤り)は『問題なし』という判断で、欠陥の主張ではない。
- `sk-13/v21` [S13-4] perspectives → **再現した**
  - 指摘: 差分は `skills/review-loop/scripts/review_loop.py`、`skills/review-loop/SKILL.md`、`skill-dev/review-loop/test.py` の3ファイルです。テスト(`python3 skill-dev/review-loop/test.py`)は全件通り、作業ツリーは変わっていません。指摘は重い順に並べます。 ## 正確性 - **`skills/review-loop/SKILL.md:49-
  - 根拠: 出力は『example Precondition: --instruct のスキル security-review が観点にない(観点: code-review, mattpocock-skills:code-review)』。iterate は Precondition を終了コード2で返すので、例をそのまま使うと止まる。962-964 の比較についての主張も同じスクリプトで再現した(引数だけの変更は記録されない: False。並べ替えは記録される: True)。
- `sk-13/v22` [正解に無い・些末] perspectives → **実行では示せない**(holds)
  - 指摘: EW_CONSTRAINT(書き込み禁止の制約)と食い違ったときにどちらが勝つかは書かれていません。「直してよい」のような指示が来ると、LLM が書き込み禁止より指示を優先する余地があります。混入の検出が後ろ盾にはなりますが、「ただし上の制約は常に優先する」と一文足すのが安価な対策です。 - argv 経由で `claude` に渡しているので、シェルインジェクションはありません(`subprocess` にリストで渡している)。 ## 並行性 - 新しい競合は見当たりません
  - 根拠: LLM が、追加の指示と書き込み禁止の制約のどちらを優先するかは、実行しても決定的には示せない。review_loop.py:744-749 の review_constraint は、REVIEW_CONSTRAINT(:74、NO_MUTATION を含む)の後ろに『スキルの手順と食い違うときは、この指示を優先してください』と足す。REVIEW_CONSTRAINT と指示が食い違ったときの優先順位は書かれていないので、指摘の言う曖昧さは文面どおり成り立つ。ただし、混入の検出(find_contamination、:972-974)が後ろ盾になっている。引用された部分の残り(argv で渡すのでシェルインジェクションがない、ロックで直列化される、test.py に指示の本文が PR に出ないことの検査がない、オプションの付け忘れ)は、事実としては正しいが、正しい挙動の確認か、テスト・設
- `sk-13/v23` [S13-2] perspectives → **実行では示せない**(holds)
  - 指摘: えば `warn:` を出すことは安くできます。 - 付け忘れると、親は観点の組が違う判定どうしを見比べることになり、SKILL.md が求める「蒸し返し・振動」の判断を誤ります。 - `--instruct` は状態に残らないので、同じ方法では検出できません。指示の本文を PR に載せたくない場合でも、ハッシュか「指示あり」という印だけ残す手があります。 - **`review_loop.py:846-847` と `JUDGE_PROMPT`(`:797` 付近)判定役の
  - 根拠: 中心の主張は『JUDGE_PROMPT に追加の指示の扱いが書かれていない』で、判定役の LLM がどう解釈するかの問題なので、実行では示せない。review_loop.py:797-836 の JUDGE_PROMPT には、指示の節の扱いが書かれていない。:805 は『対象を取り違えている』出力を観点の欠落とするよう命じている。指示は :845-847 で、見出しを付けて入力の先頭に添えられるだけ。したがって指摘は成り立つ。同じ断片の {pr} の不揃いは実行で確かめた。--perspective は『code-review high 7』に置き換わるのに、--instruct のシステムプロンプトには『PR #{pr} の本文の範囲だけ見る』がそのまま残る。SKILL.md:54 の言い切りすぎと test.py:570 の『x』は、文面とテストについての話。
- `sk-13/v24` [正解に無い・些末] mattpocock → **実行では示せない**(holds)
  - 指摘: 半分しか実装されていません。 - 指示は judge-input.md に見出し付きで添えられます(`review_loop.py:845`)。しかし JUDGE_PROMPT には、その指示をどう扱うかの一文がありません。 - むしろ JUDGE_PROMPT は「対象を取り違えている」出力を観点の欠落として載せるよう命じています(`review_loop.py:805`)。 - 例: `--instruct 'security-review=削除した .env は見ない'
  - 根拠: 1つ目(判定役が指示をどう扱うか)は LLM の解釈なので、実行では示せない。文面を追うと成り立つ。指示は judge-input.md に見出しを付けて添えられる(:845-847)。しかし JUDGE_PROMPT(:797-836)には、その扱いが書かれていない。:805 は『対象を取り違えている』を観点の欠落とするよう命じている。テスト(test.py:571)が確かめるのは、見出しがあることだけ。2つ目は実行で再現した。引数だけ変えた組は記録されず(False)、並べ替えただけの組は記録される(True)。『=』を含む指示を最初の『=』で分けるのは partition('=')(:405)なので、指摘が妥当とした点もコードどおり。
- `sk-14/v1` [S14-1] code-review → **再現した**
  - 指摘: here document` で `while ... done <<EOF` が一度も回らず、保護判定の関数が「保護対象ではない」(戻り値 1)を返しました。下の 1〜3 はこの挙動から出てくる問題です。 なお、リポジトリ内に CLAUDE.md はありません。ユーザー側の CLAUDE.md は対話の方針だけでコードの規約を含まないので、規約違反の指摘はありません。 8 findings, most severe first: 1. `skills/housekeepin
  - 根拠: (1) サンドボックス内では `lib.sh: line 43: cannot create temp file for here document: Operation not permitted` が出て、hk_is_protected は main でも entire/checkpoints/v1 でも rc=1 を返した。hk_path_in_use も同じ失敗で空を返した。制限なしでは rc_main=0、in_use=[1 cmd]。(2) apply.sh は同じエラーを出したあと `done\tbranch entire/checkpoints/v1 (...)` を出して rc=0 で終わり、保護対象のブランチが実際に消えた。補足: bash 3.2 はヒアドキュメントの一時ファイルを TMPDIR → /tmp → /var/tmp → カレントディレクトリの順に試す。
- `sk-14/v2` [S14-2] code-review → **再現した**
  - 指摘: いる。 5. `skill-dev/housekeeping/test.sh:175`: 『一時ディレクトリは HOUSEKEEPING_TMPDIR の下に作る』テストは、終了後に hk-tmp が空かどうかしか見ていない。HOUSEKEEPING_TMPDIR が無視されても通る。 Failure scenario: hk_mktemp_dir が HOUSEKEEPING_TMPDIR を読まなくなる退行が入っても、hk-tmp は空のままなので『片付ける』テストは p
  - 根拠: 中心の項目6: scan.sh は `error: 一時ディレクトリを作れない(/no-such-dir)` を出して rc=1 で止まった。しかし実行前にあった origin/gone は、実行後に消えていた。止まる前に fetch --prune が済んでいるので、SKILL.md:98 の「作れなければ何もせずに止まる」は実際の動きと違う。項目5: 変異を入れても『scan: 一時ディレクトリを片付ける』は ok だった。FAIL になったのは no-such-dir のテストだけで、片付けのテスト単独では退行を検出しない。項目7(式の重複)と項目8(案内の書き方)は、実行では確かめていない。
- `sk-14/v3` [S14-2] perspectives → **再現した**
  - 指摘: らず、修正の方針は妥当です。コメントにある「macOS の mktemp はテンプレートを付けないと TMPDIR を無視する」という前提は、この環境(macOS 27.2.1)で確かめました。`TMPDIR=/tmp/xx mktemp -u` を実行すると `/var/folders/.../T/tmp.*` が返ります。つまり、テンプレートで作る場所を明示するという対応は、問題の原因に合っています。 ## 正確性 - **`skills/housekeeping/scr
  - 根拠: scan.sh は mktemp に失敗し、error を出して rc=1 で終わった。それでも origin/gone はもう prune されていた。scan.sh では 22 行目の fetch --prune が 30 行目の hk_mktemp_dir より先に走るので、『作れなければ何もせずに止まる』は成り立たない。指摘の後半(apply.sh:21/29 は問題なし、scan.sh:31 の式の重複)は、問題がないという見立てか書き方の指摘で、挙動の再現の対象ではない。
- `sk-14/v4` [正解に無い・些末] prove → **再現した**
  - 指摘: EEPING_TMPDIR` の下に作られていない」という FAIL が出るべきでした。実際に失敗したのは、同じ変異で別に引っかかった「作れなければ止まる」のテストだけです。 ### 指摘2: apply.sh を「書き込めない TMPDIR でも動く」で検証しても、旧版の apply.sh で成功する テストでは `TMPDIR="$root/no-such-dir"` を渡し、「一時ファイルを使わないので、書き込めない TMPDIR でも動くこと」を確かめるつもりです。し
  - 根拠: 旧版の apply.sh(テンプレートなしの `input=$(mktemp)`)でも、apply の全テスト(『飛ばした行があるので終了コード 1』『偽装した保護対象の行を拒否』など)が ok になり、末尾は『全件成功』だった。ok は 53 件で、HEAD と同じ。TMPDIR=no-such-dir を渡すテストは、修正の前後を区別しない。(終了コード 143 は、後片付けで wait している busy プロセスによるもので、両方に共通。)
- `sk-14/v5` [正解に無い・些末] perspectives → **実行では示せない**(unclear)
  - 指摘: ILL.md:35** — apply.sh を `!` で実行してもらうときの案内が足りません(低〜中)。 - apply.sh は、承認した行を標準入力で受け取ります。そのため `! awk -F'\t' '$1=="delete"||$1=="prune"' <scan.tsv> | <skill-dir>/scripts/apply.sh` のような、パイプを含む形を示すべきです。 - apply.sh は、サンドボックスで失敗しても error では止まりません。`
  - 根拠: 指摘は、エージェント向けの案内文の書き方についてのもの。エージェントが実際にどう読み取るかは、実行では確かめられない。SKILL.md:35 は scan.sh について `! <skill-dir>/scripts/scan.sh > <ファイル>` の形と絶対パスを指定している。一方 apply.sh については『同じように ! で実行してもらう』とだけ書いていて、パイプの形は書いていない。ただ、手順4の SKILL.md:56-60 には `awk ... | <skill-dir>/scripts/apply.sh` というパイプの例がある。案内が欠けていると言い切れるかは、この2か所を読み合わせられるかに左右されるので、unclear とした。apply.sh がサンドボックスで失敗しても error で止まらず、skipped 行を出して終了コード1で終わる点は、apply.s
- `sk-14/v6` [S14-1] mattpocock → **再現した**
  - 指摘: *SKILL.md の箇条書きが長い**: サンドボックスの項目は1つの箇条書きに5文を詰めています。文体の規約は無いので、読みやすさの指摘にとどめます。 - **問題が無いと確かめた点**: `hk_` の接頭辞、`local` の宣言、lib.sh 冒頭の環境変数一覧への追記、`error: ...` の形式は、既存の書き方に揃っています。 ## Spec **(c) 実装が誤っていそうな要件** 1. **【高】ヒアドキュメントが一時ファイルを使い、判定が黙って誤る**
  - 根拠: `cannot create temp file for here document: Operation not permitted` のあと、hk_is_protected main main は rc=1、hk_path_in_use は空を返した。apply.sh は保護対象の entire/checkpoints/v1 を『done』として削除した。旧版の apply.sh でも test.sh は全件成功した。指摘の影響範囲の見立て(TMPDIR に書ければ成功する)は正しいが、追加の条件がある。bash 3.2 は TMPDIR・/tmp・/var/tmp のどれにも書けないとカレントディレクトリに退避する。そのため壊れるのは、カレントにも書けない場合に限られる。カレントに書ける worktree では保護判定は正しく働いた。scan.sh にヒアドキュメントが7か所あること
- `sk-14/v7` [正解に無い・些末] perspectives → **再現した**
  - 指摘: は実際の動きと違います(低)。 - 一時ディレクトリを作る前に、`git fetch --prune` がすでに走っています(scan.sh:22)。そのため、止まる時点でリモート追跡ブランチはもう刈り込まれています。 - `hk_mktemp_dir` を fetch より前に移せば、副作用を起こす前に止まり、文書の記述とも一致します。 ### 設計・文書 - **skills/housekeeping/SKILL.md:35** — apply.sh を `!` で実行し
  - 根拠: 実行前の `git branch -r` には origin/feature があった。scan.sh は mktemp のエラーと「error: 一時ディレクトリを作れない(...)」を出して rc=1 で止まった。実行後は origin/feature が消えていた。scan.sh:22 の `git fetch --prune` が scan.sh:30 の hk_mktemp_dir より先に走るので、止まった時点でリモート追跡ブランチはもう刈り込まれている。SKILL.md の「作れなければ何もせずに止まる」は実際の動きと違う。指摘の後半(SKILL.md:35 の案内、ファイル名の予測、テストの穴)はこの項目では検証していない。
- `sk-14/v8` [正解に無い・些末] mattpocock → **再現した**
  - 指摘: ekeeping はスクリプトのテストで検証する」)には違反していません。以下はすべて判断事項です。 - **既定値の連鎖が2か所にある(Duplicated Code)** - `${HOUSEKEEPING_TMPDIR:-${TMPDIR:-/tmp}}` が `lib.sh` の `hk_mktemp_dir` と `scan.sh` のエラーメッセージの両方に書かれています。 - 既定値を変えると2か所を直す必要があります。エラーの出力を `hk_mktemp_di
  - 根拠: (1) では「main protected」「in_use=[1 cmd]」で正しく判定された。bash 3.2 は TMPDIR に書けないと /tmp に切り替えるためで、PR のテスト(TMPDIR=no-such-dir で apply.sh を実行するもの)が通るのもこのせい。(2) では「lib.sh: line 43: cannot create temp file for here document: Operation not permitted」が出たあと「main NOT protected」となり、line 66 でも同じエラーが出て「in_use=[]」となった。判定は止まらずに、保護対象でない・使用中でない、という誤った側の答えを返した。apply.sh も lib.sh を読み込んでこれらの関数を使う。そのため「apply.sh は一時ファイルを使わない」(S
- `sk-16/v1` [S16-4] security-review → **実行では示せない**(holds)
  - 指摘: を通らないので、コマンドインジェクションは起きません。 * **`skill-dev/review-loop/fakes/claude`**: テスト用のフェイクが返す固定文字列に2行が足されただけです。テスト専用のファイルなので、対象外として扱いました。 * **`skills/review-loop/SKILL.md`**: `gh issue create` は、エージェントに向けた文書上の指示です。コードとして実行される経路はなく、Markdown の文書なので対象外
  - 根拠: この指摘の結論は「脆弱性なし」で、残っているのは参考の注意点(差分の外のセキュリティの指摘を公開 issue にすると、未修正の脆弱性が公開される)だけ。SKILL.md の書き方の問題で、エージェントが利用者に尋ねて作る issue の公開範囲は実行では示せない。SKILL.md:134 は、利用者が選んだものを `gh issue create` で作り、本文に場所・影響・起きる操作の順を書くよう指示している。セキュリティの指摘を区別する記述や、非公開の窓口に回す記述は無い(grep で該当するのは :154 の状態コメントの注意だけ)。作る前に尋ねる手順はあるので、利用者が気づけば防げる。ただし、本文に再現の手順まで書く指示になっているので、公開してしまったときの影響は大きい。
- `sk-16/v2` [正解に無い・些末] code-review → **挙動に関わらない**
  - 指摘: op, another says it must run again, so the same situation ends differently from run to run. 10. `skill-dev/review-loop/fakes/claude:100`: The fake verdict gains only "範囲" and "再現" and still has no "分類" field, so "再現: 対象外" does not match the
  - 根拠: 偽 claude の判定に足されたのは「範囲」と「再現」の2行だけで、「分類」の行は無い。ここまでは事実。ただし review_loop.py:837-839 のとおり、スクリプトが判定で確かめるのは VERDICT_SECTIONS(「## 指摘」「## 競合」)が行頭にあることだけで、欄は解釈しない。そのため、欄が欠けていても欄の値が食い違っていても、テストの結果もスクリプトの挙動も変わらない。指摘自身も「将来、欄を解釈するようになったら」という条件付きなので、テスト用の固定文字列の不揃いにとどまる。
- `sk-16/v3` [正解に無い・些末] mattpocock → **実行では示せない**(holds)
  - 指摘: ンプトの書き方、外部のサービスの挙動、狙って起こせないタイミングなど)」という例示が、ほぼ同じ文で SKILL.md 手順5と `JUDGE_PROMPT` の両方にあります。 - この例示は、判定役の判断の基準と、親が再現を省いてよい条件を兼ねています。片方だけ直すと食い違います。 - 対策の案は、SKILL.md 側を `JUDGE_PROMPT` への参照にすることです。 - ただ、欄の意味を SKILL.md に要約する書き方は既存の欄でもしているので、重い指摘ではあ
  - 根拠: どれもプロンプトや文書の書き方の指摘で、実行では示せない。(1) 重複: 「実行では示せない(文書やプロンプトの書き方、外部のサービスの挙動、狙って起こせないタイミングなど)」という例示が SKILL.md:102 と JUDGE_PROMPT(review_loop.py:865)の両方にある。これは事実だが、今の挙動には関わらない。片方だけ直したときに初めて食い違う。(2) Spec (b): SKILL.md:128 には、仕様に無い条件「既存のテストも通っている」と「修正が大きく…なら回す」が足されている。「回さずに終えてよい」という、してもよいことの書き方になっている点も文面どおり。(3) Spec (c): 前半は「上の基準に当たる指摘を採って直したとき」と対象を絞っている。後半の「実行で確かめていない修正が1つでもあれば」は、基準に当たらない修正まで含むのかが文面から決まらな
- `sk-16/v4` [正解に無い・些末] code-review → **再現した**
  - 指摘: check in step 1. Failure scenario: In a repository with no test directory, the parent writes repro.sh at the repo root, fixes the bug, and starts the script. The working tree is dirty, so the script exits with code 2, and that iteration's s
  - 根拠: repro.sh があるときは rc=2 で、stderr は「error: 作業ツリーがクリーンでない。コミットしてから実行する」。消すと rc=0。review_loop.py:999 が `git status --porcelain --untracked-files=all` で未追跡のファイルも数えるので、テストの置き場が無いリポジトリでルートに再現スクリプトを置いたまま起動すると、その試行は始まらない(状態には記録されないが、起動は無駄になる)。この挙動は main の時点からあり(test.py:189)、SKILL.md:32 にも書かれている。今回の PR で増えたのは、手順5で修正前に再現スクリプトを書く場面。SKILL.md:101 は「テストの置き場があれば回帰テストとして残す」とだけ書いていて、置き場が無いときにどこへ置くか・消すかを書いていない。同じ指摘の i
- `sk-16/v5` [S16-1] code-review → **実行では示せない**(holds)
  - 指摘: 10 findings, most severe first: 1. `skills/review-loop/SKILL.md:107`: 範囲の定義が「PR の変更で起きるようになったか」だけなので、PR が直すはずの問題の直し残しも「差分の外」になり、直さず、継続の理由にもしない扱いになる。 Failure scenario: PR の目的がバグ B を経路 P1 で直すことで、レビューが「同じ B が、PR の触っていない経路 P2 でも起きる」と指摘する。P2 は P
  - 根拠: 判定役(LLM)が範囲をどう付けるか、親がどう従うかという文書の指摘で、実行では示せない。(1) JUDGE_PROMPT(review_loop.py:863)は、範囲を「PR の変更で起きるようになったか」だけで決め、「PR の前から同じように起きるなら差分の外」とする。PR の意図(直すはずだったバグの直し残し)に照らした例外は無い。SKILL.md:107 は差分の外を「この PR では直さない」とし、:126 は継続の理由にしない。:107 の「自分で決め直す」の基準も「PR のベースで同じことが起きるか」で、直し残しは差分の外のまま確定する。:95 の「PR の意図に照らして覆してよい」という一般則が逃げ道になりうるが、範囲について明示した規則のほうが具体的なので、指摘どおりに読まれやすい。(2) SKILL.md:109 は、横展開を差分の内に限る規則と、規則を1か所で強制す
- `sk-16/v6` [S16-3] code-review → **実行では示せない**(holds)
  - 指摘: 10 findings, most severe first: 1. `skills/review-loop/SKILL.md:99`: For defects that meet the stop criteria, the parent must now reproduce the bug before fixing it, including by "実際に実行して". Nothing says to do this in a throwaway environment
  - 根拠: エージェントが再現をどこで実行するかという文書の指摘で、実行では示せない(実リポジトリで消してしまう操作を実際に試すのは適切でもない)。SKILL.md:99 は「修正前のコードで失敗するテストを書くか、実際に実行して」とだけ書く。再現を隔離した場所(一時リポジトリ、テストの中、dry run)で行う記述は、SKILL.md のどこにも無い(grep で該当するのは :67 の作業ディレクトリの説明だけ)。JUDGE_PROMPT(review_loop.py:865)も判定役に「実行の手順」を書かせるだけで、場所を指定していない。影響が高と判定される指摘(消すべきでないものを消す)ほど再現が必須になるので、指摘の筋は成り立つ。item 2(差分の外の扱いで直し残しが除かれる)は sk-16/v5 と同じ内容で、同じく文面どおり成り立つ。
- `sk-16/v7` [正解に無い・些末] mattpocock → **挙動に関わらない**
  - 指摘: `--instruct` で絞った範囲を指しています(SKILL.md 63行、132行、JUDGE_PROMPT)。 - 132行では、同じ1文の中に新旧2つの意味が並びます。 - 「差分との関係」や「原因の所在」のように、ほかと重ならない名前が望ましいです。 2. **5節の「横展開の候補は、差分の内にあるもの」で、同じ語の意味がずれている。** - 判定プロンプトの「差分の内」は、原因が PR の変更かどうかで決まります。 - 5節のこの文は、場所で決める読み方になりや
  - 根拠: 中心の指摘は3つで、どれも命名・重複・テストデータの話。(1) 「範囲」の語の重なり: SKILL.md:63 と :132 は `--instruct` で絞る範囲を、:86/:107/:126/:132/:134 は差分の内・外を「範囲」と呼んでいる。:132 の1文に両方の意味が入っているのは事実。(2) 同じ文が2か所にある: SKILL.md:103 と JUDGE_PROMPT(review_loop.py:865 付近)に、実行で示せない例として同じ文が書かれている。なお、指摘が「SKILL.md 78行」とした「定義は JUDGE_PROMPT が正」の文は、実際には :81。(3) fakes/claude に足した2行: test.py が判定の中身で見ているのは :146 の "### F1: s" in out だけで、スクリプトが検証するのも VERDICT_SE
- `sk-16/v8` [S16-3] perspectives → **実行では示せない**(holds)
  - 指摘: の仮説のまま issue になりえます(`:134`)。このブランチが問題にしている「確かめていない指摘」を、そのまま issue に移すことになります。 - 修正案: issue の本文に「再現済み / 未確認」を書かせる。再現はしなくてよいが、確かめたかどうかは明示させる。 ## セキュリティ - **`skills/review-loop/SKILL.md:99-103` で、再現の実行に安全の歯止めがありません** - 再現が必須になるのは影響が高の指摘で、その定義は
  - 根拠: SKILL.md への指示の書き方と、LLM の親がそれをどう実行するかの話なので、実行では示せない。文面を追うと次のとおり。(1) :134 は issue の本文に、場所・影響・起きやすさ・起きる操作の順・PR 番号を書かせている。再現したかどうかを書かせる文はない。差分の外の指摘は再現の対象外なので(:99 は終了の基準に当たる defect だけ。差分の外は :126 で継続の理由から外れる)、仮説のまま issue になりうる。(2) 再現を一時ディレクトリや一時リポジトリの中でする、外部への書き込みを避ける、という指示は :99-103 にない(grep で当たったのは :67 の作業ディレクトリの説明だけ)。(3) :134 には、公開範囲の確認、本文の案を見せること、security advisory の案内のどれもない。:154 は状態コメントに指摘の内容を載せないとして
- `sk-16/v9` [S16-8] perspectives → **実行では示せない**(holds)
  - 指摘: ないタイミング」を示せない側に置いています。しかし「試したが起きなかった」をどちらに数えるかは書かれていません。 - 確率的に起きる問題では、1回起きなかったことは反証になりません。並行性の指摘ほど、この経路で落ちやすくなっています。 - 案: 「起きなかった」として採らないのは、決定的に再現できる種類に限る。タイミングに依存するものは、試して起きなくても `:103` の扱い(コードで追って決める)にする。 ## 設計 - **`skills/review-loop/SKI
  - 根拠: 文書の判断規則の釣り合いと、LLM の親の振る舞いの話なので、実行では示せない。文面を追うと次のとおり。(1) :103 は『狙って起こせないタイミング』を実行で示せない側に置いている。一方 :102 の『再現を試みたが起きなかった: 採らない』に、決定的でない種類を除く但し書きはない。(2) :107 は、範囲の判断を親が確かめ直すのを『疑わしければ』に限っている。:126 は、差分の外とされた指摘を影響に関係なく継続の理由から外す。影響が高の指摘を確かめ直させる文はない。(3) :102 は試した手順と結果を『採らなかった理由として残す』とするが、どこに残すかは書いていない。:132 の報告は『残った指摘(採らなかったものはその理由も)』で、手順まで含むかは明示していない。(4) :128 の回さずに終える条件は、再現テストと既存テストが通ることだけで、観点別のレビューは通らない。これ
- `sk-16/v10` [正解に無い・誤り] perspectives → **実行では示せない**(holds)
  - 指摘: を `checkout main` すると、手元の変更の扱いを誤るおそれがあります。この worktree はレビュー役と共有なので、ブランチや作業ツリーの状態を変える操作自体も避けたいところです。 - 修正案: `git worktree add <一時パス> <base>` か `git show <base>:<path>` を使うよう書く。 - **`skills/review-loop/SKILL.md:99` は、複数の指摘を順に直す場合の手順が抜けています** 
  - 根拠: どれも、指示が抜けていることと、LLM がそれをどう読むかの話で、実行では示せない。(1) :107 の『PR のベースのコードで同じことが起きるかを確かめて』に、やり方の指定はない(worktree add も git show も grep で当たらない)。:16 は実行中に worktree を編集させないとしているが、修正の途中で checkout することは禁じていない。(2) :99-102 は再現と修正を1件ごとに書いており、先に全件を再現するという順序の指定はない。(3) :134 で重複をまとめるのは『反復をまたいで同じ指摘』だけで、既存の issue を確かめる手順はない。(4) :128 の『修正が大きく…なら回す』は、親が自分で判断する形になっている。(5) review_loop.py:863 は『PR の前から同じように起きるなら差分の外』としている。悪化させた
- `sk-16/v11` [S16-4] perspectives → **実行では示せない**(holds)
  - 指摘: s/` のようなもの)の中で行う。 - 外部への書き込み(push、`gh` で書き込む操作、削除)を伴う手順は、そのまま実行しない。 ## プライバシー - **`skills/review-loop/SKILL.md:134` で、指摘の内容を公開の issue に書く前の確認がありません** - このスキルはこれまで、公開の場に指摘の内容を載せない作りでした。状態コメントには「指摘の内容や判断の理由…は載せない」とあります(`:154`)。 - 今回の変更で初めて、場所
  - 根拠: 中身は v8(再現の安全の歯止め、公開 issue のプライバシー)と v10(ベースのコードで確かめる方法、複数の指摘の再現の順)の重複。どれも文書の指示の抜けで、実行では示せない。文面を追うと、:99-103 に隔離して実行する指示はなく、:107 に worktree add や git show の指定もない。:134 に公開範囲の確認や本文の提示もなく、:99-102 は1件ごとの再現と修正だけを書いている。指摘のとおり。
- `sk-16/v12` [正解に無い・誤り] mattpocock → **実行では示せない**(holds)
  - 指摘: 絞っています。後半の「実行で確かめていない修正が1つでもあれば…回す」は、基準に当たらない修正まで含むのかが読めません。 - 含むと読むと、defect でない低影響の修正を1つ混ぜるだけで毎回もう1回回すことになります。仕様の「そのための再レビュー」より広がります。 3. **(a)/(c) 「実行では示せない」が抜け道になる余地** - 仕様の「再現しなければ採らない」に対し、実装にはコードを追うだけで採否を決める第3の扱いがあります。 - 歯止めはあります。手順5の「手
  - 根拠: 文の読み方の曖昧さの話なので、実行では示せない。(1) :128 の前半は『上の基準に当たる指摘を採って直したとき…どの修正も』で、文脈から基準に当たる修正に絞られる。後半の『実行で確かめていない修正が1つでもあれば…回す』は、前半の主語を受けているとも、すべての修正とも読める。曖昧という指摘は成り立つ。(2) :103 の『実行では示せない』を、判定役がそう書いたときに親が鵜呑みにしないよう求める文はない。『判定の手順が合っていなければ組み直す』(:99)は再現の手順についての文。(3) :19 の『利用者とのやり取り』は『--new-run の確認、失敗の報告、終了時の報告』で、issue にするかを尋ねることは明記されていない。これは指摘も認めるとおり軽微で、『終了時の報告』に含むと読める。
- `sk-16/v19` [S16-5] code-review → **実行では示せない**(holds)
  - 指摘: 用されていたはずで、試したことでかえって捨てられる。コードを書いた本人が再現を担うので、起きない側に偏りやすい。起きなかったときは、コードを追う判断に戻すべき。 4. `skills/review-loop/SKILL.md:128`: 修正のすべてが再現テストで確かめられていれば、再レビューせずに終えてよいとしたため、修正のコードと新しく足した回帰テストが、どのレビューも受けずに PR に入る。 Failure scenario: 高の指摘を直すときに、関数のシグネチャを変
  - 根拠: この指摘で挙がっている項目(4〜6)は、どれも SKILL.md の文面が親エージェントの判断をどう導くか、そして外部サービス(gh・GitHub の fork 設定)がどう振る舞うかについてのもので、実行では示せない。gh issue create の項目は実際の GitHub の fork と issue 作成が要り、この環境では作れないうえ外部への書き込みになる。文面を追った結果は次のとおり。(4) SKILL.md:128 は、どの修正も再現が修正前に失敗して修正後に通り、既存のテストも通るなら回さずに終えてよいとし、『修正が大きく、再現が確かめた範囲を超えて』を判断する基準は書いていない。また『どの修正も』は『上の基準に当たる指摘を採って直したとき』の文脈にあるので、基準外の修正(style など)は再現を持たないまま再レビューされずに終わりうる。指摘どおり成り立つ。(5) :1
- `sk-16/v20` [正解に無い・些末] mattpocock → **実行では示せない**(holds)
  - 指摘: プトも `VERDICT_SECTIONS` の見出ししか検証しません。 - 偽の判定には分類の行がないのに「再現: 対象外」と書かれていて、意味が噛み合いません。 - 次のどちらかに揃えるのが妥当です。 - 足した2行を戻し、見出しだけを揃える方針に合わせる - 全部の欄を揃えたサンプルにする ## 仕様 前提として次を確かめました。 - 分類の値 `defect` は実在します(review_loop.py:874)。 - スクリプトが検証するのは判定の見出しだけなので、
  - 根拠: 偽の判定(skill-dev/review-loop/fakes/claude:100)の項目: 変更前も変更後も見出し数は 2/2 で、テストは全て成功した。分類の行がないのに『再現: 対象外』と書かれているのは事実だが、スクリプトの検証は見出しだけ(review_loop.py:839, 949-953)なので挙動には関わらない。この部分だけなら no_behavior_impact に当たる。仕様に関する項目は SKILL.md と判定役のプロンプトの文面がどう効くかの話で、実行では示せない。文面を追った結果は次のとおり。(c)1: SKILL.md:103 は、実行では示せない指摘をコードで追って採ってよいとしている。:126 が継続の理由から外すのは、差分の外と、試したが起きなかったものだけ。:128 は、実行で確かめていない修正が1つでもあればもう1回回すとしている。したがって
- `wn-306/v1` [W306-3] code-review → **再現した**
  - 指摘: 一覧に出ていない対話セッションが `claude -p` を多数起動し、トップレベルの (sub) の行だけが端末の高さを超えて並ぶ。cursor が undefined なので start=0 に固定され、下の行は見えないままになる。(2) P のすぐ下に、窓より多い (sub) の子が続く。blockLen >= avail で start=b0 になり、P の塊の末尾は切れる。次の選べる行の塊を中央に置いても途中の子は窓に入らず、PRODUCT.md の『選べない行が画
  - 根拠: (A) 見出しと s0〜s3 (sub) だけが出て、直後に `0/0` が出た。s4〜s14 は見えず、カーソルがないのでスクロールの手段もない。(B) cursor=P では `> P` と c0〜c4 が出て `1/2`。cursor=Q では c9〜c14 と `> Q` が出て `2/2`。c5〜c8 はどちらのカーソル位置でも窓に入らなかった。指摘どおり、選べない行が画面の外に残って見られなくなる。カーソルがないとき通し番号が 0/0 になることも確かめた。
- `wn-306/v2` [W306-4] perspectives → **再現した**
  - 指摘: 行のすぐ下に続く起動された行」は子の行を想定していると読めるので、`s.groups.forEach` の頭で `trailing = false` にするのが素直です。 - 単独では見える範囲が少し変わるだけですが、上の1件目と重なると、隠れる範囲が広がります。 - **[軽微] `src/ops/app.ts:263-265` と `:1215`:行が残っているのに「left the list」と出る。** - この差分で、行が更新で起動された行に変わったとき(消えてはい
  - 根拠: gb の先頭が sub のときの窓は a17, a18, > a19, ── gb ──, bs1..bs5 (sub), b1 になり、選んだ行の塊が別の区切りの見出しと (sub) の行まで伸びた。gb の先頭が b1 のときは a14〜a18 が見え、上の文脈が5行あった。trailing が区切りをまたいでも戻らないことが窓の位置に現れている。
- `wn-306/v3` [正解に無い・些末] perspectives → **挙動に関わらない**
  - 指摘: と `openWait` の `isSpawned` による断り(`:835`、`:856`)を外したので、その間に `e` を押すと起動された行にメモを書けます。`src/ops/app.ts:461` の `note: n.spawned ? undefined : …` で画面には出ませんが、状態のファイルには残ります。 - 直し方:代入をカーソル設定用の関数1か所に集めて選べるかを確かめる(または代入のたびに `followCursor` を通す)のが堅いです。もう一
  - 根拠: onReturn(app.ts:1063-1068)と pendingCursorId(app.ts:270-275)は、行を id で引いてそのまま this.cursor に入れる。選べるかは確かめない。ここまでは指摘どおり。ただ、attach できるのは kind==='background' で id を持つ行だけで(app.ts:1029 の enter)、deriveSpawners は background の行を起動された行にしない(src/input/spawners.ts の `if (r.kind === 'background') continue`)。そのため、attach 先の行が attach 中に (sub) に変わることは今のコードでは起きず、起動された行にメモが保存される経路には届かない。起動された行が id を持つ、という将来の変更があって初めて問題に
- `wn-306/v4` [正解に無い・些末] code-review → **再現した**
  - 指摘: 215`: trailing は区切りをまたいでも戻らないので、区切り A の最後の行を選ぶと、空行、次の区切り B の見出し、B の先頭にあるトップレベルの (sub) の行まで、選んだ行の塊に入る。 Failure scenario: 区切り A の最後の行を選び、区切り B の先頭に起動元が一覧にない (sub) の行が並ぶ。塊が B の見出しまで伸びるので、窓の中央寄せがずれ、選んだ行の前後の文脈が不自然に削られる。設計の『選んだ行のすぐ下に続く起動された行』を超えて
  - 根拠: B の先頭が sub のとき、窓は a17, a18, > a19, B の見出し, bs1..bs5 (sub), b1 になった。B の先頭が選べる行のときは a14〜a19 が見えた。選んだ行の塊が B の見出しと B の (sub) の行まで伸び、窓の中央寄せがずれて上の文脈が削られる(項目8)。項目9(シナリオ71のテストが /waits for:|can't/ しか見ていない)は、テストの網羅についての指摘で、挙動には関わらない。
- `wn-306/v5` [W306-6] perspectives → **再現した**
  - 指摘: す。文言が実際と食い違うだけです。行が消えた場合と、起動された行に変わった場合とで、文言を分けるのがよいです。 - **`src/ops/app.ts:275`、`:1068`(と `:1197`):「カーソルは起動された行に置かない」がこれらの経路で守られていない。** - 原因:`onReturn` と `pendingCursorId` は `cursor = row.sid` と直接入れ、選べるかを確かめません。attach している間に起動元が分かってその行が `(
  - 根拠: refresh のあと、画面は `> orchestrator` と `└ worker (sub)` になった。worker は一覧に残っている。続く C-x で `Ctrl+X ignored: worker left the list and the selection moved.` が出た。行が消えていないのに『left the list』と出ることを確かめた。onReturn の経路の件は v3 と同じで、今のコードでは届かない。
- `wn-306/v6` [W306-4] mattpocock → **再現した**
  - 指摘: ts` の `cursorBlock = [rowIndex.length === 1 ? 0 : start, …]` で、窓の始まりが先頭に固定されます。 - 実測: (sub) 15 本のあとに A・B・C を置き、高さ 10 で描くと、`> A` が出ずに `1/3` だけが出ます。 - 仕様の2文が衝突する場面です。 2. **選べる行がないとき、(sub) の行が窓の外に残ります。** - スクロールの手段がなく、`0/0` と出ます。 - 仕様の「選べない行が画
  - 根拠: 出力はヘッダ、見出し、s0〜s5 (sub)、`1/3` で、`> A` は窓に入らなかった。選べる最初の行の塊が先頭から始まり(rowIndex.length===1 ? 0)、塊の長さが窓を超えるので start=0 になる。指摘の実測どおりである。
- `wn-306/v13` [W306-7] mattpocock → **再現した**
  - 指摘: b) の行が多いと、選んだ行が窓の外に出る**: 一覧の先頭から見せるために塊の先頭を 0 にし(`screen.ts:213`)、塊が窓より大きいときは塊の先頭(=0)から窓を出します(`:227`)。トップレベルの (sub) を12行、`s0`、`s1` の順に並べ、高さ 10 で `s0` を選ぶと、`> s0` が画面に出ませんでした(サブエージェントが作業ツリーの外で試しました)。「選んだ行が見えるようにスクロールする」と「最初の選べる行なら先頭から見せる」がぶつ
  - 根拠: 窓の件: 画面は『見出し、w0〜w5 (sub)、1/2』で、`> s0` の行はどこにもない。通し番号は 1/2 なのに、選んだ行は見えない。screen.ts の cursorBlock=[0,…](最初の選べる行) と blockLen>=avail のとき start=b0=0 の組み合わせで起きる。README の件: README.md:45 に 'Both can be selected but not attached.' が残っている。通知の件: 更新のあと、worker は『└ worker (sub)』として一覧に残り、カーソルは other に移った。そのうえで『Ctrl+X ignored: worker left the list and the selection moved.』が出た(stop は呼ばれていない)。3件とも指摘どおり。
- `wn-306/v14` [正解に無い・誤り] perspectives → **再現した**
  - 指摘: ありません。 - ただし、トップレベルの `(tty)` だった行が別の区切りの起動元の下に入ると、カーソルは元の区切りに残り、その行を追いません。消した規則の理由は「見ていた組から離れてしまう」でした(PRODUCT.md の削除した段落)。それと同じ理由が、ここにも当てはまるかもしれません。これは層2(観測できる挙動)なので、「隣の行に移る」と「起動元に移る」のどちらが欲しいかを、利用者に二択で確かめる価値はあると考えます。 ## テスト - **`test/e2e/de
  - 根拠: 更新のあと、worker は lib の区切りの『└ worker (sub)』に移った。カーソルは app の区切りの『> app-other』に残り、worker にも起動元の orchestrator にも付いていかない。指摘のとおり。ただし DESIGN.md:132 の『消えたときと同じに隣の行へ移る』どおりの実装なので、不具合ではなく、層2で利用者に確かめるかどうかの問題。テストの件(deps.test.ts:446-450、464-466 で待っていない)は、harness.ts:262-267 の keys がキーごとに 150ms 待つので、まったく待たないわけではない。テストの確かさの話で、製品の挙動には関わらない。
- `wn-306/v15` [正解に無い・些末] mattpocock → **再現した**
  - 指摘: せるのは、塊が窓に収まるときだけにするべきです。 2. **Ctrl+X のガードの文言が実情と合わない**(`src/ops/app.ts:262-265`) - DESIGN.md では、選んでいた行が `(sub)` に変わったときも、消えたときと同じに隣の行へ移ります。 - このときも `Ctrl+X ignored: <名前> left the list…` と出ますが、行は一覧から消えていません。 - 層2の観測できる挙動なので、文言を変えるかどうかは利用者に二択
  - 根拠: 窓の件: (1) では `> s0` が画面に出ない。(2) で p を選ぶと c0〜c4、q を選ぶと c9〜c14 が見え、c5〜c8 はどのカーソル位置でも見えない。塊が窓に収まらないときに窓が塊の先頭に固定されるため。Ctrl+X の件: worker は (sub) で一覧に残っているのに『Ctrl+X ignored: worker left the list and the selection moved.』が出た。docs の件: PRODUCT.md:296 に『効くのは cwd と pid を示す Enter と v だけだが』が残っている。同じ段落に『起動された行はカーソルで選べない』とあるので、指摘のとおり、効く経路はない。
- `wn-306/v16` [W306-3] perspectives → **再現した**
  - 指摘: に `selectable` のような値を持たせるほうが安全です。 - **`src/model/cursor.ts:3,6` 計算量** - `selectableOrder` は行ごとに `isSpawned` で全区切りの全ノードを走査するので、O(n²) です。これがキーを押すたび(`app.ts:784`)と更新のたび(`:262`)に走ります。 - 行数が小さい間は問題になりません。気になるなら、`Layout` に `spawned` の集合を持たせれば済みます
  - 根拠: 通し番号の件: 画面は『見出し、w0〜w5 (sub)、0/0』で、0/0 が出た。start は 0 のままなので w6 から下はどうやっても見られない。指摘どおり。そのほかの指摘は挙動に関わらない。判定の出どころが2つある件(screen は marker!=='sub'、cursor は node.spawned)は、今は app.ts:447 で marker が spawned から作られるので一致している。isSpawned が O(n²) なのは事実だが、行数が少ないので体感には出ない。テストの件のうち、待っていないという指摘は、keys がキーごとに 150ms 待つので当たらない。並びを固定していないという指摘は、テストの書き方の話。
- `wn-306/v17` [正解に無い・本物] code-review → **再現した**
  - 指摘: eft the list and the selection moved.` と示される。 Failure scenario: (tty) の行 worker を選んでいる。次の更新で ps の表から起動元 P が分かり、worker は P の下の (sub) に変わって、カーソルが P に移る。2 秒以内に Ctrl+X を押すと「worker left the list」と誤った知らせが出る。worker は一覧に残っている。PRODUCT.md「操作」の守りの条件(選
  - 根拠: 2番(通知の文言): worker は『└ worker (sub)』で一覧に残っているのに『Ctrl+X ignored: worker left the list and the selection moved.』が出た。3番(窓): (sub) だけが並ぶとき w6 から下は見えない。p の下に窓より多い子が続くとき c5〜c8 は見えない。4番: (sub) だけで一覧があふれると 0/0 が出た。5番(openNote と openWait の守りを外した件)は指摘自身が『今は届かない』と書いているとおりで、起動された行が id を持つ変更が入って初めて問題になる。そのため挙動には関わらない。
- `wn-306/v18` [正解に無い・些末] code-review → **再現した**
  - 指摘: me が付き、Ctrl+X の保護が『left the list』の文言で出る。実際には行は一覧に残っている。 Failure scenario: (tty) の worker を選んでいる間に、次の更新で起動元 P が一覧に出て worker が P の下に (sub) で入る。カーソルは隣の行に移り、2秒以内の Ctrl+X には『Ctrl+X ignored: worker left the list and the selection moved.』と出る。worke
  - 根拠: 通知の件: 更新のあと、画面には『orchestrator / └ worker (sub) / > other』と『Ctrl+X ignored: worker left the list and the selection moved.』が並んだ。worker が画面に残っているのに消えたと示され、指摘どおり食い違う。5番(DESIGN.md:132 にしか書かれていない): PRODUCT.md:296 は『カーソルが自動で移るときも選ばない』と書くだけで、選んでいた行が (sub) に変わったときに隣へ移ることは書いていない。文書の件なので実行では示せないが、文面を追うと指摘は成り立つ。6番(判定の出どころが2つ)と7番(O(n²))は、今は app.ts:447 で marker が spawned から作られて一致しており、挙動には関わらない。

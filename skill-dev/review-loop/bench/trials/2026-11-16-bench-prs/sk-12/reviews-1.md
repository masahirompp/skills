===== 観点: code-review =====
PR #1(`review-loop-multi-result` → `main`)の差分を、8つの観点で見ました。修正すべき不具合の候補は上位3件です。

- **判定役の出力の扱い**(`review_loop.py:802`): 判定役の `result` 行をすべてつないでいるため、重複や後ろの雑談が `verdict.md` と標準出力に混ざります。
- **異常終了の詳細が消える**(`review_loop.py:263`): 本当の理由が入る最後の行を表示していません。
- **`tool_use_id` が None のとき**(`review_loop.py:309`): 止める側に倒すはずの拒否まで素通りします。

設定のルールでの拒否で止めない方針そのものは、ここでは否定していません。ただ、権限の拒否の扱いが前提にしている `source` の値は偽の claude で定めたものです。本物の claude の stream に同じ形で出るかは確かめていないので、マージ前に一度実物で見ておく価値があります。

9 findings, most severe first:

1. `skills/review-loop/scripts/review_loop.py:802`: 判定役の result の行をすべてつないだテキストから、最初の見出しより後を全部判定として扱っている。このため、途中の行の下書きの判定と最後の判定の両方や、判定の後に出た短い文が verdict.md と標準出力に混ざる。

   Failure scenario: 判定役がコードの確認にサブエージェントをバックグラウンドで使い、1ターン目で『## 指摘 / ## 競合』の下書きを、2ターン目で修正版を出す → verdict に F1 などが2組並び、親はどちらが正か分からない。また、1ターン目に前置きとコードフェンスで包んだ判定を出し、最後の行が『前のメッセージの内容から変わりません』の場合、text[:start] のフェンスの数は奇数でも、verdict の末尾が閉じフェンスでないので L805 の re.sub が効かない。結果、閉じフェンスと『変わりません』が判定に残る(標準出力は判定だけ、という約束に反する)。

2. `skills/review-loop/scripts/review_loop.py:263`: child_error の詳細が、最後の result の行(エラーの本文が入る行)ではなく、つないだテキストの先頭500文字になった。そのため、異常終了の本当の理由が表示されない。

   Failure scenario: レビュー役が途中のターンで長いレビューの本文を出し、最後のターンで is_error=true や 'API Error: …' で終わる → stderr と failure.txt には最初の行のレビュー本文の先頭500文字しか出ず、最後の行のエラー文が切り捨てられる。以前は data['result'] を出していたので、原因を報告できていた。

3. `skills/review-loop/scripts/review_loop.py:309`: config_denied は tool_use_id をキーにしており、tool_use_id のない拒否のイベントは None に集まる。後のものは前のものを上書きするので報告から漏れる。さらに check_result の seen に None が入るので、tool_use_id のない permission_denials はどれも黙って無視される。

   Failure scenario: source=config で tool_use_id のないイベントが2件出る → 2件目は値の上書きで長さが増えず、new_config_denials に出ないので、denials.txt にも stderr にも残らない。同じ試行で、イベントに出ず result の permission_denials にだけ載った、tool_use_id のない拒否(出どころの分からない拒否)があると、seen に None が入っているため、止める側に倒すはずの拒否が素通りして試行が成功扱いになる。

4. `skills/review-loop/scripts/review_loop.py:337`: 設定のルールでの拒否は、拒否されたものが何であっても warn と denials.txt に残すだけで続ける。判定役への入力にも入れないので、読めなかった観点の欠落を判定役が検出できない。

   Failure scenario: `gh pr diff 7; grep -n KEY .env` が deny ルールでコマンドごと拒否され、子が diff を取り直さずに『指摘なし』で終わる → 判定役は欠落を知らず、指摘なしの判定が成功として記録される。SKILL.md は『観点の欠落が出たときは denials.txt を確かめる』としているが、欠落が出ないので親は見ない。同じく、子が禁じられた git push や Edit を試みて利用者の deny ルールで拒否された場合も、以前は permission_denied で止まっていたのが warn だけになり、子が禁止操作を試みた事実が判定や記録に残らない。

5. `skills/review-loop/scripts/review_loop.py:711`: あるレビュー役が失敗して例外が出ると、ほかの動いているレビュー役の stream に、最後の poll 以降に出た設定のルールでの拒否が denials.txt に残らない。

   Failure scenario: security-review に config の拒否が出た直後、同じ巡回で前の code-review が timeout や permission_denied で raise する → security-review の tail は poll されず、denials.txt と stderr にその拒否が残らない。親は失敗の調査に必要な材料を一部欠く。

6. `skills/review-loop/scripts/review_loop.py:237`: docstring の『modelUsage はセッションの累計で、どの行も同じ値になる』は自己矛盾している(累計なら行ごとに増える)。前提の真偽をテストでは確かめておらず、偽の claude が全ての行に同じ値を入れているだけ。

   Failure scenario: 本物の claude の modelUsage がターンごとの値だった場合、最後の result の行だけを足すので、バックグラウンドのサブエージェントを使う観点のトークン数を大幅に少なく数える。test.py の 4*300 の確認は偽の claude の仕様をなぞっているだけなので、この誤りを検出できない。

7. `skill-dev/review-loop/test.py:179`: check_result の重複除去(seen)と、『result にしか載っていない拒否は止める』という分岐のテストがない。

   Failure scenario: seen の組み立てを誤り、config の拒否以外も seen に入れたり、permission_denials の照合を壊したりしても、今のテスト(denyconfig は event と result の id が一致する1件だけ)はすべて通る。config の拒否と source なしの拒否が同じ子に混ざる場合や、イベントのない result だけの拒否の場合を偽の claude に足すべき。

8. `skills/review-loop/scripts/review_loop.py:253`: check_result が tail.denial から {tool_name, tool_input} を自前で組み立てており、StreamTail.summary と同じ処理を重複して書いている。

   Failure scenario: 拒否の要約の形(tool_input の引き方など)を変えるときに2か所を直す必要があり、片方を忘れると、走っている子を止めたときと終わった子を見たときで stderr の拒否の表示が食い違う。StreamTail に denial_dict(d) を持たせ、両方から使えばよい。

9. `skills/review-loop/scripts/review_loop.py:323`: new_config_denials が poll のたびに list(self.config_denied.values()) で dict 全体を複製している。辞書の挿入順と reported の数に頼った、壊れやすい作りになっている。

   Failure scenario: 同じキーへの上書き(L309)では長さが増えず報告から漏れる(3件目の指摘と同じ原因)。拒否は普通の list に append し、tool_use_id は set で別に持てば、複製も、上書きによる取りこぼしもなくなる。
===== ここまで: code-review =====

===== 観点: code-review-2 =====
9 findings, most severe first:

1. `skills/review-loop/scripts/review_loop.py:308`: 拒否イベントの `source == "config"` だけで「止めない拒否」と決めている。`reason_type` が `subcommandResults` の拒否には、deny ルールに当たったものだけでなく、許可ルールのないサブコマンドが -p で拒否されたものも含まれうる。後者にも source=config が付くなら、本来止めるべき許可漏れを素通りさせる

   Failure scenario: 観点スキルが `gh pr diff 7; <許可されていないコマンド>` を実行する。許可ルールがないためサブコマンド単位で拒否され、イベントは source=config・reason_type=subcommandResults で出る。watch_denials は warn を出すだけで試行を続け、check_result も seen で除外するので、レビューは欠けた情報のまま成功扱いになる。SKILL.md の前提「許可されていない呼び出しは試行が失敗になる」が崩れる(偽の claude は deny ルールの形しか再現していないので、テストでは検出できない)

2. `skills/review-loop/scripts/review_loop.py:803`: 判定役の result の行をすべてつないだあとで前置きの除去と閉じフェンスの除去をしているため、最後の短い result の行が verdict.md の末尾に混ざる。閉じフェンスも末尾に来なくなるので、正規表現で落とせない

   Failure scenario: 判定役が 1行目に「以下が判定です\n```markdown\n## 指摘…\n```」、2行目に「前のメッセージの内容から変わりません」を出す。text の末尾は「```\n\n前のメッセージの…」になり、`\n```\s*$` が当たらない。verdict.md の 競合 節の末尾に、閉じフェンスと無関係な文が残る。フェンスがない場合でも、末尾の文が最後の C 項目の一部として親に読まれる

3. `skills/review-loop/scripts/review_loop.py:263`: child_error の詳細が、失敗した最後の result の行のテキストではなく、つないだテキストの先頭500文字になった。途中の行があると、肝心のエラー文が切り捨てられる

   Failure scenario: バックグラウンドのサブエージェントを使う観点で、途中の行に「2つのレビューをバックグラウンドで実行しています」と本文(500文字超)があり、最後の行が is_error=true(例: max turns の文)になる。stderr と failure.txt には途中経過と本文の冒頭しか出ず、失敗の原因が読めない。以前は data['result']、つまり最後の行を出していた

4. `skills/review-loop/scripts/review_loop.py:245`: トークン数を最後の result の行の modelUsage だけで数えているのは、modelUsage がセッションの累計だという前提に依存している。前提が誤っていてターンごとの値なら、複数ターンの子の消費を大きく少なく数える。docstring の「累計で、どの行も同じ値になる」も、累計なら値は増えていくはずなので自己矛盾している

   Failure scenario: サブエージェントをバックグラウンドで動かす観点で、本文を作るターン(大きな出力)のあとに、短い最後のターンが続く。modelUsage がターン単位なら、attempt.tokens には最後のターンの分しか載らず、状態コメントの費用の記録が実際より大幅に少なくなる(テストは偽の claude が毎行同じ値を出すので、この前提を検証していない)

5. `skills/review-loop/scripts/review_loop.py:249`: seen を config_denied のキー(tool_use_id)から作っているため、tool_use_id のない config 拒否イベントがあると None が seen に入る。その後、tool_use_id のない result 側の permission_denials がすべて「記録済み」として無視される

   Failure scenario: tool_use_id を持たない source=config の拒否イベントが 1件出る(config_denied[None])。同じ子の result に、tool_use_id のない別の拒否(source の分からない、止めるべきもの)が載る。`d.get('tool_use_id') not in seen` が偽になり、permission_denied で止まらず成功扱いになる。config_denied も None をキーにまとめるので、2件目以降の config 拒否は denials.txt と warn にも出ない

6. `skills/review-loop/scripts/review_loop.py:712`: 子が終わったあと(running=False)は watch_denials が止める拒否で例外を出さない。そのため、拒否のあとに result の行を出さずに終わった子は、permission_denied ではなく child_error「result の行がない」に分類され、拒否の内容が失われる

   Failure scenario: 子の stream に source のない permission_denied が出た直後に、子が result を書かずに異常終了する(ポーリングの間の2秒以内)。check_result は `if not tail.results` で child_error を先に出すので、stderr に拒否されたコマンドが出ない。SKILL.md の「同じ権限の拒否で2回続けて失敗したら報告」の判断材料が欠ける

7. `skills/review-loop/scripts/review_loop.py:778`: run_judge が、run_reviews の子1つ分の処理(stream-json での起動、StreamTail のポーリング、watch_denials、タイムアウトの判定、finish、最後の poll、watch_denials、check_result)をほぼそのまま複製している

   Failure scenario: 拒否の扱いや終了時の読み残し対策を変えるたびに、2か所を同じように直す必要がある。今回の PR でも、両方に watch_denials を2回ずつ書き足している。「子を1つ起動して結果のテキストを返す」ヘルパー(spawn と StreamTail の組を受け取り、ポーリングから check_result までを行うもの)にまとめ、run_reviews はそれを並列に回す形にすれば、1か所で済む

8. `skills/review-loop/scripts/review_loop.py:249`: 止める拒否の判定が、watch_denials(tail.denial)と check_result(tail.denial、results の permission_denials、config_denied による除外)の2か所に分かれていて、同じ要約を作るコードも重複している(tail.summary と check_result 内の辞書の組み立て)

   Failure scenario: check_result の denial の組み立ては tail.summary(tail.denial) と同じ内容を手で作っている。拒否の分類の規則(source の扱いなど)を変えると、StreamTail.poll と check_result の seen の両方を直す必要があり、片方だけ直すと判定が食い違う。StreamTail に「止める拒否の一覧」を返すメソッドを1つ持たせれば足りる

9. `skills/review-loop/scripts/review_loop.py:271`: 最上位の result の行をすべてつなぐため、最終ターンが本文を再掲するスキルでは、判定役への入力で本文が重複し、トークンが無駄に増える

   Failure scenario: 観点スキルが途中のターンで本文を出し、最後のターンで「最終結果:」として同じ本文をもう一度出す。judge-input.md にはその観点の本文が2回入り、判定役の入力トークンと読む手間が倍になる。同じ指摘を2件として扱う誤りも誘発しうる
===== ここまで: code-review-2 =====

===== 観点: security-review =====
# セキュリティレビュー結果: `review-loop-multi-result`(0f6501d)

**報告する脆弱性はありません(0 件)。**

確信度 8 以上の候補が出なかったため、偽陽性を振り落とす段階は実行していません。

## 確認した点

調べた結果、どれも悪用できる道筋は見つかりませんでした。

### 1. `permission_denied` の `source: "config"` を偽装して安全停止をすり抜けられるか

対象は `skills/review-loop/scripts/review_loop.py` の `StreamTail.poll` 付近です。

- stream-json の最上位のイベント(`type` / `subtype` / `source`)を出すのは `claude` CLI 自身です。モデルの出力や PR の内容は assistant メッセージの中に文字列として入るだけで、最上位の `system` イベントや `result` 行を作り出すことはできません。
- 停止せずに続けるのは、設定のルールで拒否された呼び出しだけです。ツールの呼び出しそのものは CLI がすでに拒否しているので、何かが許可されるわけではありません。
- `source` のない拒否は、これまでどおり停止します。判断できないときは止める側に倒しています。
- 判定役も stream-json で動かして同じ処理を通すようになりました。実行中の拒否でも止まるので、以前より厳しくなっています。

### 2. 拒否されたツールの入力を stderr と `denials.txt` に書くことによる情報の露出

- 書き出すのはコマンドの文字列で、ファイルの中身ではありません。1 件あたり 200 文字で切っています。
- 書き出し先の作業ディレクトリは 0700 で作られるので、ほかのユーザーからは読めません。
- 拒否された入力を stderr に出す処理は、この PR より前からあります。

### 3. `result` 行の連結

- 使うのは最上位の `result` 行だけです。つないだ文字列は `.result.md` と判定役へのプロンプトに入るだけで、シェルの実行、パスの組み立て、`eval` などには流れません。

### 4. 判定役の起動でコマンドを注入できるか

- 引数をリストで渡す `children.spawn` で起動しており、シェルを通しません。

`skill-dev/` の下(`fakes/claude`、`test.py`)はテストにしか使わず、`SKILL.md` は文書なので、除外の規則に従って対象から外しました。
===== ここまで: security-review =====


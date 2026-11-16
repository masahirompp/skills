PR #1(`review-loop-multi-result` を `origin/main` = `6a30964` と比べた差分、コミットは `0f6501d` の1つ)をレビューしました。仕様は issue がないので PR 本文とコミットメッセージを使っています。どちらの軸でも確定的な違反や大きな欠落はなく、急いで直すべきなのは Spec 軸 (c-1) の1件です。`python3 skill-dev/review-loop/test.py` は両方のサブエージェントが流し、全件成功しました(実行後も `git status` はクリーン)。

## Standards

**(a) 文書化された標準への違反:なし**
- README.md の「`skill-dev/` は開発用資産」「偽の claude/gh を使い、GitHub と API に触れない」というルールに沿っています。
- SKILL.md の frontmatter は変わっていません。
- SKILL.md とスクリプトの記述は一致しています(`judge.*`、`denials.txt`、`warn:` の行、`no_output` の文言)。旧名の `verdict.stdout.json` や `denial_summary` を参照している箇所も残っていません。
- **判断事項(文書の精度)**:SKILL.md の「失敗したとき」には「`source` がなければ止める」と書かれています。実際のコードは `source == "config"` 以外をすべて止めます。「`config` 以外(ないときも含む)なら止める」と書けばコードと一致します。

**(b) ベースラインのスメル(どれも判断事項)**
- **Duplicated Code の可能性**:`run_reviews` と `run_judge` は、poll → `watch_denials(running=True)` → タイムアウトの確認 → finish → poll → `watch_denials(running=False)` → `check_result` を同じ順に並べています。1つの子を見張る処理は抜き出せそうです。
- **Mysterious Name とフラグ引数**:`watch_denials` は、設定のルールでの拒否を記録する仕事と、止める拒否で例外を投げる仕事を兼ねています。`running=False` のときは記録しかしません。
- **Mysterious Name の可能性**:`denial_summary` を `StreamTail.summary` に変えたので、引数が拒否のイベントだと名前から読めなくなりました。
- **Primitive Obsession / Data Clumps の可能性**:`{"tool_name", "tool_input"}` の dict を何か所かで組み立てています。
- `fakes/claude` で `emit`、`deny`、`multi` を抜き出したのは、重複を減らす良い変更です。

## Spec

**(a) 欠落・部分的な要件**
- 判定役が `source` のない拒否で途中で止まる経路にはテストがありません。仕様には「source のない拒否は従来通り止まる」「判定役も同じ処理を通す」とあります。既存の `denylive` が確かめているのはレビュー役だけで、`FAKE_JUDGE` には拒否を出すモードがありません。

**(b) スコープクリープ**
- 見当たりません。`child_error` がつないだ後のテキストの先頭500字を出すようになった点は、小さな副次変更です。

**(c) 実装が誤っていそうな点**
1. **`tool_use_id` がない拒否が、止める側に倒れない**:仕様には「tool_use_id が一致するものは除く」、Blast Radius には「入れ子なら止める側に倒れる」とあります。コードで確かめました(`review_loop.py`)。
   - `review_loop.py:309`:config 拒否を `self.config_denied[msg.get("tool_use_id")]` で記録するので、id がなければキーは `None` になります。
   - `review_loop.py:249`、`:256`:`seen = set(tail.config_denied)` に `None` が入ります。その結果、result 側の `permission_denials` のうち id がないものがすべて除かれます。
   - 出どころの分からない拒否が通ってしまうので、「分からなければ止める」という PR の方針とは逆の方向に外れます。`None` は記録しない、または照合に使わないのが安全です。実際に起きるかは本物の出力の形しだいです。
2. **判定役の判定が二重になりうる**:判定は最初の見出しから末尾までを切り出します。判定役が途中の行で下書きの判定を出し、最後の行で最終版を出すと、両方が `verdict.md` に入ります。最後の行が「変わりません」のような短い文なら、それが判定の末尾に付きます。テストの `multi` が確かめているのは、最後の行が空のケースだけです。

---

**まとめ**:Standards は確定的な違反0件、判断事項5件(一番重いのは `run_reviews` と `run_judge` の重複)。Spec は欠落1件、スコープクリープ0件、実装の疑い2件(一番重いのは `tool_use_id` が `None` のとき拒否が素通りする点で、マージ前に直すかどうか決めておく価値があります)。

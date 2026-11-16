ふたつの軸のレビューが終わりました。結果を軸ごとにまとめます。

- **対象**: `git diff main...HEAD`(コミット 0f6501d の1件)
- **仕様**: Issue や PR がないので、コミットメッセージと更新後の `skills/review-loop/SKILL.md` を仕様として扱いました。
- **標準**: `CODING_STANDARDS.md` も `CONTRIBUTING.md` もないので、`README.md`、`SKILL.md`、既存コードの慣習で照合しました。

## Standards

ハード違反はありません。以下はすべて判断事項です。

- **標準との照合**
  - 新しい振る舞いには、偽の `claude` のモードとテストが付いています。README の「スクリプトの振る舞いをテストで検証する」方針に合っています。
  - `SKILL.md` は frontmatter を変えておらず、追記した文の文体と用語は既存に揃っています。
  - `judge.*` と `review-*.result.md` というファイル名は、既存の命名に揃っています。
- **`review_loop.py`**
  - **Feature Envy の可能性**: `check_result` で拒否を集めるループは、`StreamTail` のデータしか使っていません。`StreamTail.blocking_denials()` のようにデータの側へ移す余地があります。
  - **Duplicated Code の可能性**:
    - `{"tool_name": ..., "tool_input": tail.tool_inputs.get(...)}` を組み立てる形が `StreamTail.summary` にもあります。
    - `run_judge` の新しい見張りのループ(poll → watch_denials → 時間切れの判定 → finish → check_result)は、`run_reviews` で子1つを見張る処理とほぼ同じです。1つの子を見張る関数にまとめられます。
  - **Mysterious Name の可能性**:
    - `denial_summary` を `summary` に改名したことで、何の要約かが名前から消えました。
    - `self.reported` は報告済みの設定拒否の件数ですが、名前から読み取れません(例: `config_reported`)。
    - `watch_denials(running=...)` は、記録と「試行を止める例外の送出」を兼ねています。名前と引数からはそれが読みにくいです。
  - **Primitive Obsession(軽微)**: 文字列 `"config"` が実装、偽 `claude`、`SKILL.md` に散らばっています。定数が1つあれば十分です。
- **コミット全体**
  - **Divergent Change の可能性**: result の行をつなぐ変更と、設定のルールでの拒否を許す変更は互いに独立しています。コミットを分けたほうが、レビューと切り戻しがしやすくなります。

## Spec

仕様の各項目は実装されています。次の点はコードとテストで確認しました。

- 「最上位」かどうかは `parent_tool_use_id` で判定しています。
- 空の行を除き、出た順につないでいます。
- トークン数と成否は `tail.results[-1]`(最後の result の行)から取っています。
- 判定役も、観点と同じく `StreamTail`、`watch_denials`、`check_result` を通っています。

**(a) 欠けている・部分的なもの(いずれもテストの穴)**
1. source が `config` 以外の値(例: `hook`)の拒否にテストがなく、`SKILL.md` にも書かれていません。実装は `== "config"` なので、そうした拒否も止めます。安全側なので振る舞いとしては妥当です。
2. 判定役が source のない拒否で途中で止まる経路(`running=True`)にテストがありません。「判定役も同じ処理を通す」の半分しか確かめられていません。
3. 1つの子で、設定のルールでの拒否と、イベントの出ない拒否(result の `permission_denials` にだけ載るもの)が混在する場合のテストがありません。

**(b) スコープの逸脱**
- 判定役の出力ファイル名が `verdict.stdout.json` から `judge.*` に変わりました。`verdict.md` との衝突を避けるための変更と読め、`SKILL.md` にも反映されているので問題ありません。

**(c) 実装の誤りが疑われるもの(境界条件)**
1. `tool_use_id` のない拒否を取りこぼすことがあります。私もコードで裏を取りました(`review_loop.py:308-309` と `:249-256`)。
   - `tool_use_id` のない config の拒否は、`config_denied[None]` に入ります。そのため2件目以降は上書きされ、denials.txt に残りません。
   - さらに `seen` に `None` が入るので、result にしか載らない `tool_use_id` のない拒否は「既に見た」と扱われます。その結果、止めるべき拒否が素通りします。
   - 本物の stream で `tool_use_id` が欠けることがあるかは確かめていないので、実害は不明です。
2. 子が result の行を出さずに終わると、拒否のイベントが出ていても `child_error` に分類されます。これは差分の前からある振る舞いです。

**テストの不安定さ**: Spec 担当のエージェントが `test.py` を4回実行し、最初の1回だけ失敗しました。「前置きでフェンスを開いていなければ…」のケース以降が FAIL になり、`test.py:248` の `[-1]` で IndexError が出ています。残りの3回は成功し、再現できなかったので原因は特定できていません。タイミングに依存して不安定な可能性があります。

---

**まとめ**:
- Standards 軸は判断事項が8件で、ハード違反はありません。いちばん重いのは `run_judge` と `run_reviews` の見張りのループの重複です。同じ処理を2か所で直す必要が出てきます。
- Spec 軸は5件、それにテストの不安定さの観察が1件あります。いちばん重いのは (c)1 で、`tool_use_id` のない拒否では、止めるべき拒否が `seen` の `None` を理由に素通りしうることです。

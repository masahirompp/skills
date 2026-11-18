## Summary

観点の結果に、最後の `result` 行だけでなく、空でない最上位の `result` 行をすべてつないで使う。設定のルールで拒否されただけでは試行を止めない。判定役も同じ処理を通す。

```diff
 check_result(tail)
-  data = 最後の result 行
-  text = data.result                      # 空や「変わりません」だと本文が消える
+  text = 最上位の result 行のうち空でないものを、出た順につなぐ
+  data = 最後の result 行                 # modelUsage は累計なので、トークン数はここだけで数える
   permission_denials があれば permission_denied
+    (ただし source: config の拒否イベントと tool_use_id が一致するものは除く)
-  text が空なら no_output
+  空でない行が1つもなければ no_output
```

```diff
 watch_denials(子が動いている間)
-  permission_denied のイベント → その時点で試行を止める
+  source: config   → stderr に warn を出し、denials.txt に残して続ける
+  それ以外 / source なし → その時点で試行を止める
```

```diff
 run_judge
-  claude -p --output-format json → verdict.stdout.json
+  claude -p --output-format stream-json --verbose → judge.stdout.jsonl を StreamTail で読む
   VERDICT_SECTIONS の確認は、つないだ後のテキストに対して行う
```

SKILL.md: `no_output` と `permission_denied` の定義、作業ディレクトリのファイル(`judge.*`、`denials.txt`)、「失敗したとき」の拒否の扱いを直した。

## Evidence

- **Before:** whatnext #308 の試行1は、mattpocock-skills:code-review の stream に `result` 行が4行あり(本文は3行目、最後の行は `num_turns: 0` の空文字)、`no_output` で失敗した。
  **After:** 同じ stream に新しい `StreamTail` と `check_result` を当てると、4行から本文を含む約3000字を拾い、トークン数は二重に数えなかった(出力 18004)。
- `python3 skill-dev/review-loop/test.py` → 全て成功。偽の claude に足したケース:
  - 複数の `result` 行を出し、最後の行が空 → 成功。本文と途中経過の文を出た順につなぎ、最上位でない `result` 行は拾わない
  - 複数の `result` 行を出し、最後の行が短い文 → 成功。本文も最後の行も残す
  - 複数の `result` 行がどれも空 → `no_output`
  - 判定役が複数の `result` 行を出す → 見出しを確かめ、前置きは落とす
  - `source: config` の拒否のあと正常に終わる(レビュー役と判定役) → 成功。`denials.txt` と stderr に残る
  - `source` のない拒否(既存の `denylive`) → 今までどおり `permission_denied` で止まる

## Merge Danger

**Door:** two-way

スクリプトと SKILL.md だけの変更で、状態コメントの形は変えていない。戻せば元の挙動に戻る。

**Blast Radius:** 小

- 拒否イベントの実物はローカルに残っていなかったので、`source` がイベントの最上位にある前提で書いている。入れ子の場所にあった場合は、全ての拒否が止める側に倒れる(今までと同じ挙動。危ない方向には外れない)
- 許可ルールが無いための拒否も `source: config` になるなら、止まらずに続く。その場合は、判定役が「観点の欠落」として拾う流れと、親が `denials.txt` を確かめる手順に頼る
- 本文が一度も `result` 行に出ないまま終わるケースは、この変更では見分けられない(実運用ではまだ観測していない)


## レビューループの経緯

### 反復 1(レビューした SHA: 0f6501d)
- 未決: 実物の `system/permission_denied` イベントには `source` が無い(claude 2.1.327 のスキーマと、イベントを出す2か所のコードで確かめた。フィールドは `tool_name` / `tool_use_id` / `agent_id` / `decision_reason_type` / `decision_reason_code` / `decision_reason` / `message` / `uuid` / `session_id` だけ)。このため `source == "config"` の分岐は実物では一度も成り立たず、「設定のルールでの拒否では試行を止めない」が働かない(止める側に倒れるので、今までと同じ挙動)。連結コマンドの deny は `decision_reason_type: subcommandResults` になり、許可ルールが無いための拒否と区別できるかは、実物で観測しないと分からない。PR の前提に関わるので、直し方を利用者に尋ねている
- 未決: `source` の判別に関わらず、設定のルールでの拒否を止めない設計そのものへの懸念(必要な読み取りが拒否されて観点の中身が欠けても成功になり、偽の収束になりうる。拒否の記録が判定役の入力に渡らない)。上の判断と合わせて決める
- 未決: 途中経過の文しか出ずに終わった子や、途中のターンのエラー文が、本文として成功扱いになる(以前は最後の行が空なら `no_output`)。その形の stream は観測していない
- 起きなかった: `tool_use_id` が無い拒否のイベントで `seen` に None が入る — 実物のスキーマで `tool_use_id` は必須

<details><summary>対象でない指摘</summary>

- 判定役の result の行をつなぐと、判定の後ろに2行目の短い文(実物の stream で「判定は先に出したもののままで、変更はありません…」を観測)が残り、前置きでフェンスを開いたときの閉じフェンスも落ちない(影響が低い defect。判定を2回全文で出す形は未観測)
- child_error の詳細が、つないだテキストの先頭500字になり、最後の行のエラー文が切れる(影響が低い defect)
- modelUsage のコメント「どの行も同じ値」は不正確。実物では累計で行ごとに増える(11419 → 11695)。最後の行だけ数える処理は正しい(doc)
- result の行が無いまま終わった子の拒否が child_error になる(差分の外。PR の前から同じ)
- run_judge と run_reviews の待ち方の重複、拒否の要約の組み立ての重複(style)
- 本文を子の最後のメッセージに出させる、という根本の直し方の代案(設計の代案)
- security-review: 指摘なし

</details>

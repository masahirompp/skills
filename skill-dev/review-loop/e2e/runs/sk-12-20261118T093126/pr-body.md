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
- 直さなかった: 設定のルールでの拒否を `source == "config"` で見分けている点 — 利用者の判断(ループを終える)。ローカルに残っていた本物の `claude -p`(2.1.325)の `permission_denied` イベント21件はどれも `source` を持たず、理由は `decision_reason_type`(`rule` / `subcommandResults` / `safetyCheck` / `classifier`)に入っていた。利用者の deny ルール(`cat .env`、`cat a.txt; cat .env`)の拒否も `source` なしで、今のコードでは止める側に倒れる。PR の目的(設定のルールでの拒否では止めない)が実物では果たせない
- 直さなかった: `tool_use_id` のない拒否が `None` のキーにまとまり、id のない result の拒否を隠す — 起きなかった。実物の21件はどれも `tool_use_id` を持つ
- 利用者の判断: ここでループを終える。前提(拒否イベントの実物の形)を確かめ直してから、PR を作り直す。止めない拒否を `decision_reason_type` のどの値で見分けるかと、偽の claude の拒否イベントを実物の形に合わせるかは、作り直しのときに決める

<details><summary>対象でない指摘</summary>

- 判定役が見出しのあとに別の result 行を出すと、閉じフェンスと後続の文が verdict.md に残る(影響が低い defect。実物の判定役で複数の result 行は未観測)
- 見出しの確かめを、つないだ後のテキストで行うので、途中の下書きでも通る(影響が低い defect)
- child_error のメッセージが、最後の result 行ではなく、つないだテキストの先頭を出す(影響が低い defect)
- トークン数を最後の result 行だけで数える前提(影響が低い。PR の Evidence で実物の stream で確かめ済み)
- 子が result 行を出さずにすぐ終わると、拒否が出ていても child_error になる(差分の外)
- 必要な読み取りが設定のルールで拒否されても、試行が静かに成功する(PR が意図した設計。判定役と denials.txt に頼る旨は PR 本文に記載済み)
- サブエージェントを前面で動かせば複数の result 行を避けられる(設計の代案)
- run_judge と run_reviews の監視ループの重複、watch_denials の二度呼び、拒否の要約の組み立ての重複(style)
- test.py の `saved.index("本文")` が本文の欠落で例外になる(test_gap)
- security-review: 指摘なし

</details>


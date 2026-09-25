# Skill Benchmark: cycle-rewrite — iteration 16(lib/ 昇格の縮小と transition-check 改訂の検証)

**Model**: executor / grader とも claude-opus-5-5
**Skill**: `80ac1fd`(lib/ 昇格を原則だけに縮小、transition-check の移行作法を判断軸に変更し部分適用を追加)
**Evals**: 1, 3 のみ(変更の影響範囲)。1 run

## Summary

| Eval | iteration-15 slim | iteration-16 |
|------|------|------|
| 1 cycle-end | 19/19 | 19/19 |
| 3 transition | 7/7 | 7/7 |

GitHub 書き込みの権限拒否は今回は発生しなかった。

## 所見

- **cycle-end**: パーサー温存の要望を削除の例外ではなく昇格として扱い、根拠を仕様の収束に置いた(依存ゼロ・テスト2件で Safari 未検証、と fixture どおりに点検)。lib/ や4点セットの記述が無くても、ADR への記録を計画に含めた。#6(タグ一本化)がパーサーに波及するリスクを自分から指摘した。難点は見出し番号の飛び(§1, §2, §5, §7)と、数値文字参照のデコードに関する記述の軽い不正確さ
- **transition**: 移行の作法2通りを判断軸(src/ を追えているか、磨き込んだ部分があるか)とともに示し、選択を人間に委ねた。spec-change 件数の推移(3→1→0)と open issue の内訳に誤記なし(iteration-15 の current で見られた件数の誤記は再発せず)。見落としは tests/ の不在のみ
- **制約**: 1 run。部分適用(移行後の再開)を試す eval は無い

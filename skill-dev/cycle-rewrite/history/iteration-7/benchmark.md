# Skill Benchmark: cycle-rewrite — iteration 7

**Model**: sonnet_with_skill = claude-sonnet-5 / haiku_with_skill = claude-haiku-4-5
**Date**: 2026-07-09T15:07:41Z
**Evals**: 0, 1, 2, 3, 4 (1 run each per configuration)
**Skill**: c3b8879 / a7598ff 時点(モジュール昇格・層パスの init 時確定・cycle-start の実装ルート委譲を含む)

## Summary

| Metric | Haiku With Skill | Sonnet With Skill | Delta |
|--------|------------|---------------|-------|
| Pass Rate | 60% ± 34% | 97% ± 6% | -0.37 |
| Assertions | 31/49 | 47/49 | — |

## Per-eval

| Eval | Haiku | Sonnet |
|------|-------|--------|
| 0 init | 10/12 | 12/12 |
| 1 cycle-end(昇格 assertion 4本を含む) | 9/15 | 13/15 |
| 2 capture | 1/7 | 7/7 |
| 3 transition | 3/7 | 7/7 |
| 4 cycle-start(新規) | 8/8 | 8/8 |

## 所見

- **eval-4 cycle-start は両モデル満点**。N=2 の git タグからの導出、cycle-2 マイルストーン作成、蒸留済み docs 限定(close 済み旧 issue を読まない)、grilling 開始、PRODUCT.md の先回り更新なし、実装ルート非固定、をすべて遵守。
- **昇格挙動(今回の焦点)**: Sonnet は「削除の例外ではなく lib/ への昇格」と正しく再構成し、仕様の収束・使い捨て層への非依存・実データ検証の再現コストを根拠に挙げて承認前に停止。Haiku は lib/ 行きにはできたが、根拠が「検証済みだから」の受け売り(収束確認なし)で、ADR への昇格記録も欠落。
- **Sonnet の FAIL 2本は構造的**: cycle-end で承認ループ 1/8 で正しく停止したため、タグ作成・削除対象一覧(棚卸し完了後のフェーズ)に未到達のまま採点された。grader も「正しい早期停止ほど FAIL になる」と指摘。スキル側で「儀式全体の段取りを先に提示してから逐次承認に入る」ことを促すか、assertion を承認後継続の別ターンに切り出すかの判断が必要。
- **Haiku の主要な失敗モード**: capture で期待動作の決定をユーザーに迫って停止し起票せず終了(1/7)。cycle-end で台帳一括の包括承認を要求・ADR-0002 をスキル化に誤ルーティング・CONTEXT.md 剪定漏れ。transition で open issue の名指し点検と移行作法2通りの中身が欠落。
- **eval 改善候補(grader 指摘)**: 状態+発話の複合 assertion の分割(eval-0)、単一ターン構造とタグ/削除 assertion のズレ解消(eval-1)、照合結果の issue 本文への反映要求(eval-2)、収束シグナルの実データ点検要求(eval-3)。
- 計測上の注意: time/tokens はサブエージェント通知から取得できず未計測(0)。

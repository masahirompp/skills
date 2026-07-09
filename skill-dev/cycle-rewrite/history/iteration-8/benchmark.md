# Skill Benchmark: cycle-rewrite — iteration 8

**Model**: sonnet_with_skill = claude-sonnet-5 / haiku_with_skill = claude-haiku-4-5
**Date**: 2026-07-09T15:55:16Z
**Evals**: 0, 1, 2, 3, 4 (1 run each per configuration)
**Skill**: iteration-7 の分析に基づく修正済み working tree(儀式段取り提示・起票先行・1件目で締める・宛先判別・剪定連動・昇格実点検・transition 応答骨子)
**Evals 定義**: assertion 49→51本に強化(複合分割・issue 本文反映・実データ点検・ルート委譲明示・decision-log 誤 ADR 化否定チェック)

## Summary

| Metric | Haiku With Skill | Sonnet With Skill | Sonnet(環境要因除外) |
|--------|------------|---------------|---------------|
| Pass Rate | 76% (39/51) | 86% (44/51) | **96% (44/46)** |

## Per-eval

| Eval | Haiku | Sonnet | it7 Haiku | it7 Sonnet |
|------|-------|--------|-----------|------------|
| 0 init | **12/12** | 12/12 | 10/12 | 12/12 |
| 1 cycle-end | 7/17 | **16/17** | 9/15 | 13/15 |
| 2 capture | **6/7** | 2/7 ※環境要因 | 1/7 | 7/7 |
| 3 transition | **7/7** | 7/7 | 3/7 | 7/7 |
| 4 cycle-start | 7/8 | 7/8 | 8/8 | 8/8 |

※ assertion セットが iteration-7 より厳しくなっているため、率の直接比較は参考値。

## 所見

- **スキル修正の効果が4点で確認できた**: init の遅延作成説明(Haiku 満点回復)、capture の起票先行(Haiku が issue #8 を起票してから報告、1/7→6/7)、transition の名指し点検+応答骨子(Haiku 3/7→7/7 満点)、cycle-end の段取り提示(Sonnet 16/17、タグ→承認→削除の順序・台帳 8/8 照合・昇格4基準の実点検・1件目で締める、を全て遵守)。
- **capture sonnet 2/7 はスキル起因ではない**: 規律どおり即起票を試みたが、ハーネスの外部書き込みガードが `gh issue create` をブロック(iteration-7 は通過。発火は非決定的)。成果物不在で assertion 1〜5 が機械的に FAIL。除外すると Sonnet 実質 96%。
- **Haiku cycle-end の新 failure mode(7/17)**: ロードマップは提示するが台帳(issue 毎の宛先割当)を作らず、昇格の承認だけを単独で先に求めて停止。次の改善候補は「台帳は承認不要の分析 — 最初のメッセージに含め、承認質問を台帳より先に単独で出さない」の明文化。
- **cycle-start 両モデル 7/8**: 唯一の FAIL は強化した「ルート委譲の明示(沈黙不可)」で、両モデルとも沈黙。スキルに明示を義務づけるか、assertion を「断定禁止」のみに戻すか、設計判断が必要(grader も乖離の可能性を指摘)。
- **eval 側の次の改善候補**: eval-1 の「7件」ハードコード(ふりかえり起票で8件になる)→「シードの全 open issue」へ。否定チェックの肯定側との対化。collect-evidence.sh への `git status -sb` / ADR 本文ダンプの追加。
- 計測上の注意: time/tokens 未計測。1 run/config。外部書き込みガードの発火は非決定的。

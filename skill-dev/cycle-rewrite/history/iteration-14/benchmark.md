# Skill Benchmark: cycle-rewrite — iteration 14

**Model**: sonnet_with_skill = claude-sonnet-5 / haiku_with_skill = claude-haiku-4-5
**Date**: 2026-07-26T04:00:00Z
**Evals**: 5 のみ(スコープ実行)。eval 0-4 は未実行 — cycle-end 儀式 §0 の変更はサイクル2以降でのみ発火し、eval-1 の fixture はサイクル1のため挙動不変
**Skill**: commit `9f15a0c`(監査台帳の issue 起票 + cycle-end 事前確認の issue 判定化)+ `8a5b528`(台帳 issue の assertion 追加 → 14本)
**Runs**: sonnet 1 run / haiku 1 run(fixture は run ごとに新規リポ: -i14 / -i14h)

## Summary

| Metric | Haiku run-1 | Sonnet run-1 |
|--------|------------|---------------|
| Pass Rate (eval-5, 14本) | 71% (10/14) | **86% (12/14)** |

assertion が 13本 → 14本に増えたため、pass_rate は iteration-13 と直接比較不可。

## 所見

- **新規定「監査台帳の issue 起票」は sonnet が初回 run で遵守**: `#10 cycle-audit: サイクル2 監査台帳`(decision-log、ms=cycle-2)を A/B を含む全差分の分類付きで起票し、新 assertion #14 を PASS。haiku は台帳を最終応答のテキストとしてのみ提示して issue 化せず #14 FAIL — sonnet/haiku を分別し、かつ haiku の失敗は「台帳が痕跡として残らない」というこの規定が防ぎたい行動そのものを捕捉しており、assertion の判別力・妥当性とも確認できた。
- **sonnet 12/14。失点2はどちらも検出系**: 仕込みの D(パーサーの place: 内部エントリ除外の喪失)を今回は未検出(#7 FAIL)。iteration-13 の sonnet は検出していたため、**検出力の run 間揺らぎが sonnet でも観測された**(it13 で haiku について記録した現象と同型。規律系 12本は全て PASS で、揺れたのは検出のみ)。代わりに「検索のあいまい一致(表記ゆれ・タイプミス許容)の喪失」を D として issue #11 に二択併記で起票し、これが #11(ADR 証跡ありの検索方式変更を起票しない)FAIL と判定された。
- **assertion #11 の判定には eval 設計の曖昧さがある**(grader も指摘): ADR-0002 Rejected → ADR-0003 Accepted が証跡になるのは「実装方式の変更」であり、「あいまい一致という観測可能な挙動を捨てる」トレードオフは fixture のどの docs にも明記されていない。層2の語彙ではこれを D と読む解釈も成立し、sonnet の起票は決め打ちせず二択併記で規律にも沿っていた。次 iteration の課題: fixture の ADR-0003 Consequences に「検索は前方一致のみ(あいまい一致は提供しない)」を明記して仕込みを厳密化するか、#11 を「層1のみの差分(挙動が同一)の起票禁止」に限定して再定義する。
- **haiku 10/14 — iteration-13(7/13・6/13)から規律系が大幅改善**: it13 で再現率100%で FAIL していた規律系5本のうち、4分類台帳(#2)・層2二択(#6)・旧コード引用(#12)の3本が今回 PASS(A/B/C/D の分類体系と証跡列を持つ台帳を自力で構成)。スキルの今回変更はこの部分に触れていないため、モデル出力の揺らぎの可能性が高く 1 run では断定しない。残る FAIL 4本は D 系一式(#7 見逃し・#8 起票なし・#9 従属 FAIL)+ #14 で、**「issue 出口の欠落」という it13 と同型の構造的失敗**に集約される。
- **grader からの eval 改善提案**(次 iteration 向け、優先度順): (1) #8・#9・#14 は「起票ゼロの run」で常に連動 FAIL する — #9 は #8 に完全従属しており分解能が低い。(2) D 見逃しの根本原因(旧サイクルのテストコードまで挙動目録に含めたか)を直接見る assertion がない — 「cycle-1 のテストに現れる挙動が比較対象に含まれている」を検討。(3) #12 の「コード片の引用」の許容閾値(判定根拠の補助まで可)を明文化すると採点が安定する。
- fixture の既知の非計画ギャップ(タグ絞り込み未実装・検索結果の DOM 非表示が両サイクル共通)は it13 記録どおり両モデルが C として検出し、採点では不利に扱っていない。
- 計測上の注意: time/tokens 未計測。1 run/config。

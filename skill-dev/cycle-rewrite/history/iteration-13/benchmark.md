# Skill Benchmark: cycle-rewrite — iteration 13

**Model**: sonnet_with_skill = claude-sonnet-5 / haiku_with_skill = claude-haiku-4-5
**Date**: 2026-07-20T14:40:00Z
**Evals**: 5 のみ(新設 cycle-audit のスコープ実行。eval 0-4 はスキル該当部の変更が無いため未実行)
**Skill**: commit `26055b5`(cycle-audit モード新設)+ `b8a5a8a`(eval-5 追加: 4分類の正解を仕込んだ fixture と assertion 13本)

## Summary

| Metric | Haiku With Skill | Sonnet With Skill |
|--------|------------|---------------|
| Pass Rate (eval-5) | 54% (7/13) | **100% (13/13)** |

## 所見

- **sonnet は新モードの手順を完全遵守で 13/13**。サブエージェント隔離で cycle-1 の挙動目録を抽出し(本体に旧コードを読み込まない規律を自己申告+最終応答にコード片引用なし)、A/B/C/D の4分類台帳を証跡列付きで一括提示、D は「復活/廃止確定」二択併記の spec-change issue(#10)を回答待ちにせず起票、C は「今直す/先送り確定」の層2二択で人間に委譲、docs 非編集。仕込み4件(フォルダ=A、ピン留め=B、フォールバック=C、place: 除外=D)を全て正しく分類した。
- **haiku の失点6はすべて「蒸留漏れ(D)」系に集中**: D の概念を経由せず監査を「完了条件チェック」に還元したため、docs に痕跡の無い喪失(パーサーの place: 除外等)を見落とし(HTMLインポートを「実装済 ✅」と誤認)、起票・二択併記も連鎖的に不成立(#7,8,9)。分類体系にも D が無く台帳 assertion FAIL(#2)。加えて層2の二択確認をせず「実装すべき」と処方(#6)、旧コードのコード片を最終応答に直接引用(#12)。references/cycle-audit.md の手順(4分類・二択・隔離)を読まずに自己流で監査した形跡が濃い。
- **gh 起票の環境ブロック(it10-12 の既知問題)は今回発生せず**: sonnet の `gh issue create` が一発で通った。プロジェクト settings.json への allow ルール追加(4d04ce4)後の初確認。
- **fixture の非計画ギャップ**: タグ絞り込みが両サイクルとも未実装のまま完了条件に含まれており、両モデルがこれを実装漏れとして検出した(実在のギャップなので誤検出ではなく、assertion にも干渉しない)。sonnet はさらに検索の関連度順ランキングの喪失(Fuse.js の関連度順 → 順不同)も C として拾った — これも実在の挙動差で正当。次 iteration で仕込みを厳密に保ちたい場合は、タグ絞り込みを cycle-2 src に実装するか完了条件から外す。
- **eval 設計の妥当性確認**: 仕込み4件は sonnet が全て素直に検出・分類できており、閾値の曖昧さ(「一定規模以上」)を挙動目録+証跡照合に置き換えた設計は機能している。haiku との差分が assertion にきれいに現れており、判別力もある。
- 計測上の注意: time/tokens 未計測。1 run/config。eval-5 は今回が初計測のため過去 iteration との率比較は不可。

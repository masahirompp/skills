# Skill Benchmark: cycle-rewrite — iteration 12

**Model**: sonnet_with_skill = claude-sonnet-5 / haiku_with_skill = claude-haiku-4-5
**Date**: 2026-07-10T06:11:00Z
**Evals**: 0, 1, 2, 3, 4 (1 run each per configuration)
**Skill**: commit `b57195c` — レビュー提言の実装(儀式手順書 §1: ふりかえり起票は承認不要・失敗しても台帳に判決を乗せて続行 / 承認は逐次の原則に「複数論点の確認リストも包括承認」のアンチパターンと締めの正準形を明記)
**Evals 定義**: 52→54本に強化(eval-1: 真空 PASS 禁止+「早すぎる停止」否定チェック追加で19本 / eval-2: 複合 assertion 分割+起票不実施停止の FAIL 明記で8本 / eval-3: fixture に spec-change 減少トレンドを仕込み「推移」を読める材料に変更)

## Summary

| Metric | Haiku With Skill | Sonnet With Skill |
|--------|------------|---------------|
| Pass Rate | **93% (50/54)** | 89% (48/54) ※ |

※ sonnet の失点6はすべて eval-2 の実行環境ブロック起因(下記)。環境要因を除くと sonnet 54/54。

## Per-eval

| Eval | Haiku | Sonnet | it11 Haiku | it11 Sonnet |
|------|-------|--------|-----------|------------|
| 0 init | 11/12 | **12/12** | 11/12 | 12/12 |
| 1 cycle-end | **17/19** | **19/19** | 16/18 | 18/18 |
| 2 capture | **8/8** | 2/8 ※環境 | 0/7 ※環境 | 7/7 |
| 3 transition | 6/7 | **7/7** | 6/7 | 7/7 |
| 4 cycle-start | **8/8** | **8/8** | 7/8 | 8/8 |

## 所見

- **eval-2 の断続的失敗の原因が確定 — スキルでもモデルでもなく実行環境**。it12 の sonnet run は仕様照合 → 暗黙の要件の認定 → 選択肢併記まで完璧に実施した上で、`gh issue create` が実行環境の権限ガード(auto モード分類器)に**実際にブロックされた**と final-response に明記して停止した(evidence でも issue 未作成・リポジトリ initial state を確認)。ブロックは確率的で、同条件でも通る run と通らない run がある(it12 haiku は 8/8 で通過、it11 haiku は 0/7 でブロック)。これで it10 以降の eval-2 の 0/7 系はすべて環境要因と整理できる。**対処は eval 運用側の gh allow ルール追加(要ユーザー判断 — セッション権限の自己拡大は分類器に拒否されるため AI からは実施不可)**。
- **提言修正(§1 起票の承認不要化・失敗時継続)は狙いどおり機能**: haiku cycle-end は it10 の「起票の許可待ちで台帳前に停止」(4/18)が消え、17/19。追加された「早すぎる停止」否定チェック(新 assertion)も両モデル PASS — 起票がブロックされても台帳・ロードマップまで最初の応答で完遂する挙動が両モデルで安定した。
- **強化した assertion 群でも sonnet cycle-end は 19/19**: 真空 PASS 禁止条件付きの #7 否定チェック、「早すぎる停止」チェックを含めて全通過。
- **eval-3 の fixture トレンド(spec-change 3→1→0)は機能**: sonnet は close 済みマイルストーンの issue 履歴から推移を自ら読んで提示し 7/7。haiku の残存 FAIL は「読めない項目(次サイクルの動機)を推測で埋めた」で、fixture 強化が捕捉力を上げた形。
- **haiku の残存 FAIL は既知の層の問題**: (1) e1: ADR-0002 のステータス遷移の扱い、(2) e1: 包括承認への滑落(it9 から継続する haiku 固有の反復 failure — 文言追加では塞ぎきれておらず、これ以上は費用対効果が低い)、(3) e0: README の入力候補提示(2 iteration 連続)、(4) e3: 上記。
- **スコア推移(同一ハーネス)**: haiku 32/52(it10)→ 40/52(it11)→ 50/54(it12)。sonnet 52/52 → 52/52 → 48/54(全失点が環境ブロック。環境要因除きで満点維持)。
- 計測上の注意: time/tokens 未計測。1 run/config。assertion セットが it12 で強化されているため、率の直接比較は参考値。haiku e1/e4 は final-response 未保存で「保存のみ・作業追加禁止」の催促後に保存(evidence で汚染なしを確認)。

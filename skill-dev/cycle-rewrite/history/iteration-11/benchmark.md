# Skill Benchmark: cycle-rewrite — iteration 11

**Model**: sonnet_with_skill = claude-sonnet-5 / haiku_with_skill = claude-haiku-4-5
**Date**: 2026-07-10T05:30:00Z
**Evals**: 0, 1, 2, 3, 4 (1 run each per configuration)
**Skill**: commit `449292d` — レビュー指摘2+3 の書き直し(棚卸しを「分析は一括・全体像は先に見せる・承認は逐次」の3原則+手順5段に再構成、cycle-start / transition-check を references/ に降ろして SKILL.md を骨子化。SKILL.md 14.5k → 10.5k chars)
**Evals 定義**: iteration 9・10 と同一(52本)。executor ハーネスは iteration 10 と完全同一

## Summary

| Metric | Haiku With Skill | Sonnet With Skill |
|--------|------------|---------------|
| Pass Rate | 77% (40/52) | **100% (52/52)** |

## Per-eval

| Eval | Haiku | Sonnet | it10 Haiku | it10 Sonnet |
|------|-------|--------|-----------|------------|
| 0 init | 11/12 | **12/12** | 12/12 | 12/12 |
| 1 cycle-end | **16/18** | **18/18** | 5/18 (追試 4/18) | 18/18 |
| 2 capture | 0/7 ※環境要因の疑い | **7/7** | 0/7 (追試 5/7) | 7/7 |
| 3 transition | 6/7 | **7/7** | 7/7 | 7/7 |
| 4 cycle-start | 7/8 | **8/8** | 8/8 | 8/8 |

## 所見

- **指摘2+3(3原則化・reference 化)による sonnet の退行なし — 52/52 を維持**。cycle-start / transition-check の詳細を references/ に降ろしても、両モードの全 assertion が PASS。e4-sonnet は references/cycle-start.md を読んだ上で、ADR-0001(クライアントサイドのみ)とユーザー要望(複数端末)の正面衝突を検出し、業務的完了条件を grilling の最初の質問群に含めた — reference 化で「読んでから実行する」が機能している一次証拠。
- **haiku cycle-end が 5/18 → 16/18 に大幅改善 — 3原則化の狙いどおりの挙動変化**。it10 では haiku は儀式を丸ごと委譲(run-1)または §1 起票の許可待ちで台帳前に停止(run-2)していた。it11 の haiku は、ふりかえり issue の起票が permission で失敗しても**停止せず**、7件全件の台帳・件数照合・正準ロードマップ転記・昇格4点まで最初の応答で完遂した。「分析は一括(台帳より先に承認質問を挟まない)」を原則として前置した効果と整合する。ただし 1 run/config のため分散の寄与は排除できない。
- **haiku の残存 FAIL は既知の層の問題に収斂**: (1) 締めの「確認事項」で台帳全体への一括合意を求めた(包括承認 — it9 追試でも観測された haiku の反復 failure)。(2) 起票できなかったふりかえりを台帳に乗せる代替手当てなし。(3) e0: README を入力候補として提示せず前提化寄り。(4) e3: 境界に直結する issue(Supabase RLS)の名指し漏れ。(5) e4: マイルストーン cycle-2 の作成も手順明示もなし。
- **eval-2 capture haiku 0/7 は it10 と同型の環境要因の疑い**: 「権限の制限により GitHub issue は直接起票できません」と自己申告して起票せず停止。このリポジトリの permission 設定に gh の allow ルールが無く、バックグラウンド subagent の `gh issue create` は権限プロンプトに当たると応答者不在で拒否されうる。同一 fixture で it10 run-2 は起票に成功しており(gh 経由の書き込み自体は可能)、**拒否後にフォールバックせず諦めるのが haiku、回避して完遂するのが sonnet** という行動差が実態。スキル文言では塞ぎにくく、eval 運用側の手当て(gh allow ルールの明示)が先。
- **it10 → it11 の正味変化(同一ハーネス)**: sonnet 52/52 → 52/52(維持)、haiku 32/52 → 40/52(+8。うち cycle-end +11、init −1・transition −1・cycle-start −1 は run 分散の範囲)。
- **grader からの eval 改善提案(累積)**: 否定チェックの真空 PASS 対策(#7 close 判定に #3 正ルーティング成立を前提条件化)、「承認前に台帳・ロードマップ全体像を提示できているか」の独立 assertion 化、eval-2 assertion 6 の分割、eval-3 fixture への spec-change 減少トレンドの仕込み。
- 計測上の注意: time/tokens 未計測。1 run/config。haiku の e0/e2/e4 と e1(注: it11 では e1-haiku も)は final-response 未保存で「保存のみ・作業追加禁止」の催促後に保存(evidence で汚染なしを確認)。

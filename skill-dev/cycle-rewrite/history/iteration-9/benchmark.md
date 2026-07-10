# Skill Benchmark: cycle-rewrite — iteration 9

**Model**: sonnet_with_skill = claude-sonnet-5 / haiku_with_skill = claude-haiku-4-5
**Date**: 2026-07-10T00:18:15Z
**Evals**: 0, 1, 2, 3, 4 (1 run each per configuration)
**Skill**: レビュー指摘の修正済み working tree(参照ずれ修正・ロードマップにテストシナリオ更新追加・cycle-end 手順2 の不変条件への縮約(重複解消)・実装セッションの規律の独立・--limit 照合注記)
**Evals 定義**: assertion 51→52本(ロードマップ完全性の追加)。「7件」ハードコードを相対表現に修正(iteration-8 grader 指摘)

## Summary

| Metric | Haiku With Skill | Sonnet With Skill |
|--------|------------|---------------|
| Pass Rate | 88% (46/52) | 92% (48/52) |

## Per-eval

| Eval | Haiku | Sonnet | it8 Haiku | it8 Sonnet |
|------|-------|--------|-----------|------------|
| 0 init | 11/12 | **12/12** | 12/12 | 12/12 |
| 1 cycle-end | **15/18** | **16/18** | 7/17 | 16/17 |
| 2 capture | **7/7** | **7/7** | 6/7 | 2/7 ※環境要因 |
| 3 transition | 6/7 | 6/7 | 7/7 | 7/7 |
| 4 cycle-start | 7/8 | 7/8 | 7/8 | 7/8 |

※ assertion セットが毎回強化されているため率の直接比較は参考値。

## 所見

- **重複縮約(レビュー指摘4の(a)案)による退行なし**: cycle-end 手順2 を SKILL.md 側で不変条件3点に縮約したが、Haiku cycle-end が 7/17 → 15/18 と大幅改善。iteration-8 の failure mode(台帳を作らず昇格承認だけ単独で先行して停止)は両モデルで解消 — 台帳先出し・段取り提示・1件目で締める、をすべて遵守。縮約後も要点は伝わっており、詳細を ceremony に一本化する方針は成立。
- **新 assertion(ロードマップにテストシナリオ更新)は両モデル PASS**: 修正2(ロードマップ欠落)の反映を確認。
- **capture 両モデル満点**: iteration-8 の Sonnet 2/7 が環境要因(書き込みガード)だったことの裏付け。起票先行・選択肢併記・issue 本文への仕様照合の反映まで一次証拠で確認済み。
- **新しい共通 failure(eval-4)**: 両モデルとも「業務的な完了条件を grilling で人間と合意すべき項目として扱う」を落とした(it8 の FAIL はルート委譲明示で、今回それは PASS — FAIL 箇所が移動)。grilling の質問が設計パラメータ(同期方式・件数目安等)に終始し、「何がどう動けばこのサイクルは完成か」を問わない。SKILL.md cycle-start 手順4 に記述はあるが、grilling 開始応答の質問設計まで届いていない — 次の改善候補(例: 手順4 に「grilling の最初の質問群に完了条件の問いを含める」を明文化するか、質問例を1つ添える)。
- **eval-1 残存 FAIL は「最初の応答のロードマップ・台帳に落ちにくい細部」**: (1) #6 の宛先で「User Stories の該当項目の削除」の明示漏れ(両モデル。「User Story 修正」止まり)、(2) 昇格4手順のうちテスト持ち越しへの言及漏れと、削除除外の「lib/ とそのテスト」の「そのテスト」明示漏れ(Haiku は両方、Sonnet は後者のみ)。ceremony §5/§8 には明記されているが、初回応答の要約時に脱落する。
- **eval-3 は各モデル1件ずつ別方向の FAIL**: Sonnet は移行作法2の「棚卸しは常に必須」を状況依存の注意に弱めた表現、Haiku は「次サイクルの動機」をユーザーの一言から断定(人間に聞くべき項目)。応答骨子5点そのものは両モデルとも機能。
- **grader からの eval 改善提案**: eval-1 assertion 16/17 は根本原因が同一で統合可能。eval-3 assertion 6 は「2作法の提示」と「作法2の棚卸し必須性」の2基準を1本に束ねており分割すると診断性が上がる。点検数値の正確性を検証する assertion が無い(今回は fixture 裏取りで正確と確認)。executor の transcript(ツール呼び出し履歴)保存で検証強度が上がる。
- 計測上の注意: time/tokens 未計測(benchmark.json の Tokens 行は一部 grader の独自記入によるノイズ)。1 run/config。

## 追試(run-2): eval-4 共通 failure への修正検証

cycle-start 手順4 に「完了条件は終了間際の点検ではなく grilling の**最初の質問群に含めて**問う(理由: 完了条件が先に立つと以降の質問の要否と深さが定まる)+質問例」を追記(コミット `12023d4`)し、新規 fixture(`cycle-rewrite-eval-start-*-i9b`)で eval-4 のみ再実行した。

| Eval | Haiku run-2 | Sonnet run-2 | run-1 |
|------|-------|--------|-------|
| 4 cycle-start | **8/8** | **8/8** | 7/8 / 7/8 |

- 両モデルとも、完了条件を具体例付きの質問として最初の質問群に含めた。FAIL していた assertion は実質的な合意事項化として PASS(語への言及だけではない)
- Sonnet は「複数端末対応の結論が検索方式の選択に依存する」という質問間の依存関係を自ら発見して質問順序に反映(assertion 外の質の高い挙動)
- **注意(Haiku run-2)**: final-response に「マイルストーン cycle-2 を作成し」とあるが GitHub 実体には未作成 — assertion 2 の OR 条件(「作成を手順として明示」)で PASS したが、「言い切りだけで実行を伴わない」報告を拾えない assertion の弱点として grader が指摘。evidence 収集に milestone 実体の事後確認を組み込む改善提案あり
- benchmark.json は run-1 のみの集計(run-2 はスキル版が異なるため混ぜない)

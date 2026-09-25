# Skill Benchmark: cycle-rewrite — iteration 15(Opus 前提の簡素化)

**Model**: executor / grader とも claude-opus-5-5
**Configs**: opus_current = 簡素化前(`6af8e82`)/ opus_slim = 簡素化版(SKILL.md 28.7KB → 9.2KB、スキル全体 81KB → 44KB)
**Evals**: 0〜5 全件、1 run/config
**Evals 定義の変更**: eval-1 の書式依存 assertion 3本(#2 件数照合、#13 ロードマップの独立ステップ、#19 台帳とロードマップの同一応答)を結果判定に書き換え

## Summary

| Eval | current | slim |
|------|---------|------|
| 0 init | 12/12 | 12/12 |
| 1 cycle-end | 19/19 | 19/19 |
| 2 capture | 8/8 | 8/8 |
| 3 transition | 7/7 | 7/7 |
| 4 cycle-start | 8/8 | 8/8 |
| 5 cycle-audit | 11/14 ※ | 14/14 |

※ current の失点3本は、すべて `gh issue create` が実行環境の権限判定で拒否されたことによる連鎖 FAIL。slim の eval-1 でも同じ拒否が1回起きた(ふりかえり起票。台帳行へのフォールバックで assertion は PASS)。設定差ではなく環境要因と判断する。

## 所見

- **簡素化による退行は検出されなかった**。Opus では、Haiku 向けに足した応答書式の指定(正準ロードマップの逐語転記、「1件目で締める」、確認リストの禁止例など)を外しても、全 assertion を満たした
- **assertion は天井に張り付いており、判別力を失っている**。Opus では両設定とも満点で、「差が無い」ことは言えても「どちらが良い」は言えない
- 採点者の質的所見(ブラインド判定): slim が上回ったとされたのは capture(解決経路と続行の明記)、transition(判定不能項目の明示、current は件数の誤記あり)、cycle-start(質問間の依存の説明)、cycle-end(分析の深さ)。current が上回ったとされたのは init(README の3択提示、永続層の明記)と cycle-end(昇格4手順の具体性)
- **計測上の制約**: 1 run/config。ブラインドは evidence.txt 内のリポジトリ名(-with / -base)から推測可能だった。background サブエージェントの GitHub 書き込みが非決定的に拒否される

## 次の改善候補(grader 提案)

- 質を測る assertion の追加: 昇格判断の根拠の質、issue 本文に解決の場を明記しているか、件数など数値が実体と一致するか
- 起票失敗1件が複数 assertion に連鎖する構造(eval-5 #8・#9・#14)の分解
- collect-evidence.sh の出力からリポジトリ名を匿名化する
- 権限拒否を避けるため、fixture リポジトリにも `gh issue create` 等の allow 設定を置く

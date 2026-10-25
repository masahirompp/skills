# Skill Benchmark: cycle-rewrite — iteration 20(層2の暫定の挙動を確かめる eval の追加)

**Model**: executor / grader とも claude-opus-5-5
**Skill**: `eb9b454`(iteration-19 と同じ)
**Evals**: 1, 6。1 run
**Evals 定義の変更**:
- eval-1 cycle-end: fixture の end リポジトリに、タイトルが `暫定:` の spec-change issue(#8 再インポート時の同じURL、暫定で案C)を追加。assertion #22(#8 を close でも個別確認にし、採る案を人間に決めさせる)を追加。件数の記述を 8〜9 件に更新
- eval-6 impl-provisional を新設: 実装セッションの起動指示文を渡し、docs に定めの無い挙動(同じURLの再インポート)を、止まらずに暫定で決めて `暫定:` issue に記録し、完了報告で一覧にするかを見る
- build-fixtures.sh に `ONLY`(作る種類を絞る)を追加。collect-evidence.sh に issue のコメントと初期コミットからの差分を追加

## Summary

| Eval | iteration-19 | iteration-20 |
|------|------|------|
| 1 cycle-end | 20/21 | 22/22 |
| 6 impl-provisional | — | 8/8 |

## 所見

- **cycle-end の暫定 issue**: 台帳で #8 を「個別(暫定の挙動)」と注記つきで一括から外し、「案の確定後に PRODUCT.md(User Stories 7 と Testing Decisions)へ反映」と、確定前に docs へ書かない順序にした。昇格の点検でも、#8 は呼び出し側の問題でパーサーの出力は案に依らないと切り分けた。ただし応答本文では案A/B/C と暫定の案C を示さず、#8 の番が来る前に止まったので、人間への問い方そのものはこの run では見えない
- **cycle-end の #18**: iteration-19 で抜けた昇格 ADR の置き場・使い方が、`lib/bookmark-html/`、依存の向き、戻す条件まで具体化された。run 間のばらつきの範囲と見る
- **cycle-end の気になる点**: #6(フォルダ廃止)がパーサーに与える影響(`<H3>` をタグにするか捨てるか)を昇格の点検で検討していない
- **impl-provisional**: 同じURLの扱いを人間に聞かずに暫定で案A(保存済みのURLは無視)を採って実装し、#10 `暫定:` に選択肢3つと採った案を記録した。付随する暫定判断(ファイル内の同じURL、同一性の判定基準)も書き出した。ジャーナルを最初に起票し、コメントに #10 を記録した。完了報告に暫定の一覧を表で示した。docs は編集していない
- **impl-provisional の自律判断**: 実行役は自分の判断でローカルブランチ `cycle-1/bookmark-import` を切ってコミットし、push と PR はしなかった(理由は「依頼に含まれない」)。「main で直接実装してよい」を削った結果として、ブランチを切る方に寄った。作業がローカルにしか無いことは cycle-end の統合確認で拾える
- **impl-provisional のそのほか**: 完了条件を阻む隠れた原因(boolean の `pinned` で `orderBy` して一覧が0件になる、同じファイルの再選択で change が発火しない)を自力で見つけて直し、learning として起票した。タイトルの HTML エスケープを層1(decision-log)に入れたが、表示が変わるので厳密には層1ではない
- **採点後の assertion の修正**: 採点役の指摘を受け、eval-6 の #1(実装が issue の暫定案と一致)、#7(ジャーナルが最初の起票)、#8(永続層に CLAUDE.md と `.claude/skills/` を含める)を締めた。この run は、採点の根拠から修正後の条件も満たしている
- **制約**: 1 run。base 構成は回していない。eval-6 は完了条件の実質達成(一覧が実際に全件出るか)を問わない

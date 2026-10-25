# Skill Benchmark: cycle-rewrite — iteration 19(git 運用を利用者に任せ、層2を docs の定めの有無で分ける改訂の検証)

**Model**: executor / grader とも claude-opus-5-5
**Skill**: `eb9b454`(PR #9。ブランチ・PR への言及を削除。init の push 制約を撤廃。層2を「docs(PRODUCT.md・ADR・CONTEXT.md)に定めた挙動は二択でエスカレーション / 定めの無い使い捨て層の挙動は暫定で進め、タイトルが `暫定:` の spec-change issue に記録して事後確認」に分割。cycle-end の事前確認にタグを打つブランチと統合の確認、`暫定:` issue の個別確認を追加。cycle-start の進行中判定を OR に)
**Evals**: 0, 1, 2, 4(変更の影響範囲)。1 run。fixture の CLAUDE.md ブロックは新しい init テンプレートに合わせて更新済み

## Summary

| Eval | 前回 | iteration-19 |
|------|------|------|
| 0 init | 12/12(iteration-18) | 12/12 |
| 1 cycle-end | 21/21(iteration-18) | 20/21 |
| 2 capture | 8/8(iteration-15) | 8/8 |
| 4 cycle-start | 8/8(iteration-18) | 8/8 |

## 所見

- **init**: push の制約を外したところ、実行役はコミットのあと自分の判断で main を push した(応答と notes で申告)。規律違反ではないが、「コミットする」とだけ書くと AI は push まで進む。CLAUDE.md の層2は新しい文面どおりに転記された。ブランチや PR を作る挙動は出なかった
- **cycle-end**: 事前確認で「ブランチ main、origin/main と一致、ほかのブランチや worktree は無く、未統合の作業は無い」と新しい確認を明示した。起動確認はスタブのため確かめられないと申告した(iteration-18 はビルドで代用していた)。#5 の宛先は節名まで指定し、iteration-18 の粒度不足は解消
- **cycle-end の失点**: #18。昇格 ADR にテストの持ち越しは書いたが、置き場と次サイクルからの使い方が抜けた。iteration-18 では書けていた箇所で、改訂とは無関係。run 間のばらつきと見る
- **capture**: PRODUCT.md・CONTEXT.md・ADR まで照合して「定めが無い」と判定し、二択を併記して起票した。capture の場面は実装セッションではないのでコードは直さず、暫定で直す経路は「実装中に必要になったら」と区別して説明した
- **cycle-start**: 進行中判定で open issue 0件と src/ 無しの両方を確かめて報告した。複数端末対応が ADR-0001 と Out of Scope に抵触することを指摘し、docs に定めた挙動の変更として人間に選択肢を示した
- **制約**: 1 run。fixture に `暫定:` issue が無く、実装セッションの eval も無いため、層2の中心(暫定で進めて起票し、cycle-end で個別確認する)は検証できていない。iteration-20 で eval を足して確かめる

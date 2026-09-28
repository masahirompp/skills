# Skill Benchmark: cycle-rewrite — iteration 18(main ブランチ縛りと PRODUCT.md 単一正本の縛りを緩める改訂の検証)

**Model**: executor / grader とも claude-opus-5-5
**Skill**: `099ae0f`(PR 禁止と「main は常に起動する」を削除し「main で直接実装してよい」を許可として追加。サイクルをブランチで分けない禁止を外す。PRODUCT.md の単一ファイル・戦略同居の規定を削除し、設計は `docs/` 配下の別ファイルに分けてよいとした)
**Evals**: 0, 1, 4(変更の影響範囲)。1 run。fixture の CLAUDE.md ブロックを新しい init の「ブランチ」節に合わせて更新

## Summary

| Eval | 前回 | iteration-18 |
|------|------|------|
| 0 init | 12/12(iteration-15) | 12/12 |
| 1 cycle-end | 21/21(iteration-17) | 21/21 |
| 4 cycle-start | 8/8(iteration-15) | 8/8 |

## 所見

- **init**: CLAUDE.md の「ブランチ」節はテンプレートどおり「使い捨て層の実装は main で直接行ってよい」になり、旧文言は残らなかった。スタック未定のまま既定の層定義で進め、フレームワークが `app/`・直下の `package.json` を使う場合に削除範囲が曖昧になる点を確認事項に挙げた(手順違反ではない)
- **cycle-end**: 回答待ちの #8 を一括に置かず「他に判決が無ければ close」と条件付きにした(iteration-17 の疑わしい点が解消)。仕様の宛先はすべて PRODUCT.md で、別ファイルへの分散は起きなかった。事前確認は「build が通る」で起動確認を代用しているが、iteration-17 も同じ挙動で改訂による変化ではない
- **cycle-end の軽微な後退**: #5 の宛先が「CLAUDE.md の cycle-rewrite ブロック」止まりで節名が無い。#4 の反映案に Testing Decisions の性能シナリオが無い。#2 の反映案で localStorage フォールバックが抜けた。いずれも改訂箇所とは無関係で、run 間のばらつきの範囲と見る
- **cycle-start**: 改訂の影響は観測されなかった。ただし grilling の第1ラウンドで止まるため、どちらの改訂も効かない段階
- **制約**: 1 run。設計を別ファイルに分ける挙動(PRODUCT.md の合成・更新)と、main 直接実装の実装セッションを試す eval は無い

# init の手順

新規プロジェクト(グリーンフィールド)のセットアップ。

1. **前提確認**: git リポジトリであること、`gh auth status` が通ること。issue トラッカー等の設定(`docs/agents/issue-tracker.md` 等)が無ければ、先に /setup-matt-pocock-skills を促す(issue トラッカーは GitHub。目的は grilling と capture の前提整備)。旧名の `CONTEXT.md` が残っていれば、同じスキルが `GLOSSARY.md` への改名を持ちかける。domain-modeling は `GLOSSARY.md` しか読み書きしないので、改名しておく。既存の README や構想メモがあれば、最初の grilling の入力候補として提示し、扱いを人間に確認する
2. **`docs/adr/`・`GLOSSARY.md`・`docs/PRODUCT.md` は作らない。** 空の器を先に置くと grilling 前に推測で埋められ、仕様が汚染される。`docs/adr/` と `GLOSSARY.md` は grilling と併用する domain-modeling が最初の ADR・用語と共に作り、PRODUCT.md は最初の grilling の結果から合成する
3. **層のパスを確定し、CLAUDE.md に規約ブロックを追記する**(下記テンプレート)。既定(使い捨て層 = `src/` とテストコード)で足りるなら聞かずに進む。monorepo や `src/` を使わない構成など既定が合わないときだけ、削除対象パスを人間と合意する
4. **ラベル**: `learning` / `spec-change` / `decision-log` を作る。この3つの付いた open な issue が受信箱になる
5. **コミット**: 作成・変更したファイルをコミットする
6. **報告**: rewrite(最初の仕様詰めと実装)に進むことを提案する。未作成の docs は作り忘れと区別がつかないので、意図的に作らなかったことと理由を報告に含める

## gh コマンド

```bash
gh label create learning --color FBCA04 --description "実装・確認で得た学び"
gh label create spec-change --color D93F0B --description "仕様変更・要件の判明"
gh label create decision-log --color 0E8A16 --description "AI の内部設計判断の記録(自律判断 層1)"
```

## CLAUDE.md 追記ブロック

CLAUDE.md の末尾に追記する(CLAUDE.md が無く AGENTS.md があればそちらに、どちらも無ければ CLAUDE.md を作成)。層の定義のパスは確定した実パスに置き換える。文言はプロジェクトに合わせて調整してよいが、3層自律判断・学びの捕捉と棚卸し・ADR の基準は省略しない。セッションを跨いで確実に効かせる必要があり、それを保証できるのは毎セッション読まれる CLAUDE.md だけ。

```markdown
## サイクル型リライト開発(cycle-rewrite)

このプロジェクトは、コードをいつでもゼロから作り直せるように、仕様と学びを docs に積み上げて開発する。学びの起票・棚卸し・作り直しは cycle-rewrite スキルに従う。

### 層の定義

- 永続層: `docs/`(PRODUCT.md、adr/)、`GLOSSARY.md`、`.claude/skills/`、CLAUDE.md — 厳格に維持する
- 使い捨て層: `src/` とテストコード — 作り直しで全削除する。品質は「動けばOK」

作り直しの削除対象はこの定義を正とする。作り直しても残すコードは、この定義から外す。

**使い捨て層の削除は、人間が作り直しを頼んだときだけ行う。** 受信箱を空にする → `git tag rewrite-YYYY-MM-DD` → 削除、の順を守る。

### AI の自律判断(3層)

1. **内部設計の変更**(外から見える挙動が変わらない): 自律で進めてよい。判断内容を `decision-log` ラベル付き issue に記録する。
2. **観測可能な挙動・仕様の変更**: docs(PRODUCT.md・ADR・GLOSSARY.md)に定めた挙動を変えるなら、人間へのエスカレーション必須。質問は「挙動 A と挙動 B のどちらが欲しいか」というドメイン語の二択で行う。コードの理解を要求する質問はしない。docs に定めの無い挙動は、暫定の挙動を選んで進め、選択肢と暫定で採った案を、タイトルが `暫定:` で始まる `spec-change` issue に記録する(確定は棚卸しで人間が行う)。
3. **不可逆・外部影響**(課金、外部 API 契約、本番データ、公開等): 常に同期エスカレーション。例外なし。

### 学びの捕捉と棚卸し

実装・確認中に得た学び(エッジケース、想定外挙動、暗黙の要件、ライブラリのハマり、AI の設計判断)は発見の都度 GitHub issue に起票する。ラベルは `learning` / `spec-change` / `decision-log`。この3つの付いた open な issue が受信箱で、本文の最後に `branch: <起票したときの作業ブランチ>` の1行を書く。

作業を終えて報告する前に、受信箱のうちこのセッションの作業ブランチの issue を棚卸しする(cycle-rewrite スキルの「棚卸し」): docs に反映して閉じる。人間が決めるのは仕様(要件と用語)・`暫定:` の確定・ADR だけで、それ以外は反映して報告する。起票しただけの短いやり取りでも、応答を終える前に行う。実装のインプットは docs で、受信箱の issue はインプットにしない。

### ADR の基準

ADR を書く3条件(覆すのが難しい・文脈なしでは意外・本当のトレードオフの結果)のうち、「覆すのが難しい」は本プロジェクトでは「**コードを作り直しても覆らないか**」で解釈する。捨てる予定のコードに紐づく実装レベルの判断は ADR にしない(`decision-log` issue でよい)。

### 作り直す前のコードの参照

作り直す前のコードを作業ツリーに置かない。参照が必要なら `git show <タグ>:src/...` か、作業ツリー外への `git worktree` を使う。
```

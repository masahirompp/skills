# init の手順

新規プロジェクト(グリーンフィールド)のセットアップ。

1. **前提確認**: git リポジトリであること、`gh auth status` が通ること。issue トラッカー等の設定(`docs/agents/issue-tracker.md` 等)が無ければ、先に /setup-matt-pocock-skills を促す(issue トラッカーは GitHub。目的は grilling と capture の前提整備)。既存の README や構想メモがあれば、サイクル1の grilling の入力候補として提示し、扱いを人間に確認する
2. **`docs/adr/`・`CONTEXT.md`・`docs/PRODUCT.md` は作らない。** 空の器を先に置くと grilling 前に推測で埋められ、仕様が汚染される。`docs/adr/` と `CONTEXT.md` は grilling と併用する domain-modeling が最初の ADR・用語と共に作り、PRODUCT.md はサイクル1の grilling の結果から合成する
3. **層のパスを確定し、CLAUDE.md に規約ブロックを追記する**(下記テンプレート)。既定(使い捨て層 = `src/` とテストコード)で足りるなら聞かずに進む。monorepo や `src/` を使わない構成など既定が合わないときだけ、削除対象パスを人間と合意する
4. **ラベルとマイルストーン**: `learning` / `spec-change` / `decision-log` と `cycle-1` を作る(`bug` は GitHub 既定)。ラベル = 種別、マイルストーン = サイクル区分
5. **コミット**: ローカルに留める。push のタイミングは人間が決める
6. **報告**: cycle-start に進むことを提案する。未作成の docs は作り忘れと区別がつかないので、意図的に作らなかったことと理由を報告に含める

## gh コマンド

ラベル(`bug` は GitHub 既定なので作成不要):

```bash
gh label create learning --color FBCA04 --description "実装・確認で得た学び"
gh label create spec-change --color D93F0B --description "仕様変更・要件の判明"
gh label create decision-log --color 0E8A16 --description "AI の内部設計判断の記録(自律判断 層1)"
```

マイルストーン:

```bash
gh api -X POST "repos/{owner}/{repo}/milestones" -f title=cycle-1
```

## CLAUDE.md 追記ブロック

CLAUDE.md の末尾に追記する(CLAUDE.md が無く AGENTS.md があればそちらに、どちらも無ければ CLAUDE.md を作成)。層の定義のパスは確定した実パスに置き換える。文言はプロジェクトに合わせて調整してよいが、3層自律判断と ADR 解釈ルールは省略しない。この2つはセッションを跨いで確実に効かせる必要があり、それを保証できるのは毎セッション読まれる CLAUDE.md だけ。

```markdown
## サイクル型リライト開発(cycle-rewrite)

このプロジェクトはサイクル型リライト方式で開発する。サイクルの開始・終了・移行判断は cycle-rewrite スキルに従う。

### 層の定義

- 永続層: `docs/`(PRODUCT.md、adr/)、`CONTEXT.md`、`.claude/skills/`、CLAUDE.md — 厳格に維持する
- 使い捨て層: `src/` とテストコード — サイクル末に全削除する。品質は「動けばOK」

パスは init で確定した値。cycle-end の削除対象はこの定義を正とする。コードは雑に、ドキュメントは厳格に。

サイクルを跨いで残すコードは、cycle-end で人間の承認と ADR への記録を経て永続層へ昇格したものに限る。

**使い捨て層の削除は cycle-end の儀式の中でのみ行う**: issue 棚卸しの完了 → `git tag cycle-N` の作成 → 人間の明示的な承認、を必ずこの順で経ること。タグ前・承認前の削除は、学びと復元手段を同時に失う。

### AI の自律判断(3層)

1. **内部設計の変更**(外から見える挙動が変わらない): 自律で進めてよい。ただし判断内容を `decision-log` ラベル付き issue に記録し、確認フェーズで一括報告する。
2. **観測可能な挙動・仕様の変更**: 人間へのエスカレーション必須。質問は「挙動 A と挙動 B のどちらが欲しいか」というドメイン語の二択で行う。コードの理解を要求する質問はしない。二択で表現できない変更は層1として扱う。
3. **不可逆・外部影響**(課金、外部 API 契約、データ破壊等): 常に同期エスカレーション。例外なし。

### 学びの捕捉

実装・確認中に得た学び(エッジケース、想定外挙動、暗黙の要件、ライブラリのハマり)は発見の都度 GitHub issue に起票する。ラベル(`bug` / `learning` / `spec-change` / `decision-log`)+ 現在サイクルのマイルストーンを付ける。issue は受信箱であり、次サイクルのインプットは蒸留済み docs のみ。

### ブランチ・マージ方針

- PR は使わない。短命ブランチ(worktree)で作業し、ローカルチェック(build/lint、テストがあればテスト)通過を条件にローカルで main にマージする
- 不変条件: main は常に起動する

### ADR の基準

ADR を書く3条件(覆すのが難しい・文脈なしでは意外・本当のトレードオフの結果)のうち、「覆すのが難しい」は本プロジェクトでは「**サイクルを跨いでも覆らないか**」で解釈する。捨てる予定のコードに紐づく実装レベルの判断は ADR にしない(`decision-log` issue でよい)。

### 旧サイクルコードの参照

旧サイクルのコードを作業ツリーに置かない。参照が必要なら `git show cycle-N:src/...` か、作業ツリー外への `git worktree` を使う。
```

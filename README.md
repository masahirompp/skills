# skills

masahirompp の Claude Code 用 [Agent Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) 集。

## 構成

リポジトリ直下の各ディレクトリが1スキル。[Agent Skills の仕様](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/skill-authoring-best-practices)に従い、`SKILL.md`（YAML frontmatter の `name` はディレクトリ名と一致、`description` は 1024 文字以内）と、必要に応じて `references/` などの補助ファイルを置く。

```
<skill-name>/
├── SKILL.md          # frontmatter (name, description) + 本文
└── references/       # 必要時に読み込まれる詳細ドキュメント
```

`skill-dev/` はスキル本体ではなく開発用資産（eval 定義・fixture 生成スクリプト・ベンチマーク履歴）。Claude Code には読み込ませない。

## スキル一覧

| スキル | 概要 |
| --- | --- |
| [cycle-rewrite](cycle-rewrite/SKILL.md) | サイクル型リライト開発ワークフローの管理。PoC/プロトタイプをサイクル単位でゼロから書き直し、仕様と学び（PRODUCT.md・ADR・CONTEXT.md・プロジェクトスキル）を永続資産として積み上げる開発方式のオーケストレーション |

## インストール

user scope で使う場合はシンボリックリンクを張る:

```sh
ln -s ../../ghq/github.com/masahirompp/skills/cycle-rewrite ~/.claude/skills/cycle-rewrite
```

## 開発（eval の回し方）

スキルの改善は skill-creator の eval で計測しながら行う。資産は `skill-dev/<skill-name>/` にある:

- `evals/evals.json` — eval 定義（プロンプト・assertion）
- `fixtures/build-fixtures.sh` — eval 用の使い捨て GitHub リポジトリ（`cycle-rewrite-eval-*`）を生成・シードする。イテレーション番号をサフィックスに渡す（例: `build-fixtures.sh -i7`）
- `fixtures/collect-evidence.sh` — 実行後の各 fixture リポの状態を evidence.txt にダンプする（例: `collect-evidence.sh 7`）
- `history/iteration-N/` — 過去イテレーションのベンチマーク結果とフィードバック

実行時の作業ディレクトリ（fixture リポのクローンや eval 出力）は `~/.claude/skill-dev/cycle-rewrite-workspace/` に作られる（`CYCLE_REWRITE_WS` で変更可）。生成物はコミットせず、結果の要約（benchmark.md 等）だけを `history/` に取り込む。

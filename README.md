# skills

masahirompp の Claude Code 用 [Agent Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) 集。[Claude Code plugin](https://code.claude.com/docs/en/plugins) として配布している。このリポジトリは plugin marketplace で、系統ごとに3つのプラグインを載せている。

| プラグイン | 中身 |
| --- | --- |
| `cycle-rewrite` | サイクル型リライト開発ワークフロー（スキル cycle-rewrite） |
| `dev-tools` | どのリポジトリでも使う開発作業の道具（スキル review-loop・housekeeping・issue-check） |
| `session-timeline` | Claude Code の画面を拡張する mod（関数フック） |

## 構成

プラグインは `plugins/<plugin-name>/` に1つずつ置き、スキルはその中の `skills/<skill-name>/` に置く。各スキルは[Agent Skills の仕様](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/skill-authoring-best-practices)に従い、`SKILL.md`（YAML frontmatter の `name` はディレクトリ名と一致、`description` は 1024 文字以内。`description` に `: ` などを含む場合は `>-` のブロックスカラーで書く。Claude Code は寛容に読むが、`npx skills` は厳密な YAML パーサーを使うため、そのままだと読み込みに失敗する）と、必要に応じて `references/` などの補助ファイルを置く。スキルを追加するときは、合うプラグインの `skills/` にディレクトリを足すだけでそのプラグインに含まれる。

```
.claude-plugin/
└── marketplace.json        # マーケットプレイス定義（名前 "masahirompp"。plugins/ の3つを載せる）
plugins/
├── cycle-rewrite/          # スキルのプラグイン
│   ├── .claude-plugin/plugin.json   # skills/ を参照
│   └── skills/
│       └── <skill-name>/
│           ├── SKILL.md    # frontmatter (name, description) + 本文
│           └── references/ # 必要時に読み込まれる詳細ドキュメント
├── dev-tools/              # スキルのプラグイン（構成は cycle-rewrite と同じ）
└── session-timeline/       # mod（独自の .claude-plugin/plugin.json と hooks/ を持つ）
skill-dev/                  # 開発用資産（どのプラグインにも含まれない）
```

`skill-dev/` はスキル本体ではなく開発用資産（eval 定義・fixture 生成スクリプト・ベンチマーク履歴、スクリプトのテストと偽コマンド）。プラグインのディレクトリの外にあるので、インストール時にプラグインのキャッシュへ複製されず、Claude Code にも読み込まれない。

## スキル一覧

| スキル | プラグイン | 概要 |
| --- | --- | --- |
| [cycle-rewrite](plugins/cycle-rewrite/skills/cycle-rewrite/SKILL.md) | cycle-rewrite | サイクル型リライト開発ワークフローの管理。PoC/プロトタイプをサイクル単位でゼロから書き直し、仕様と学び（PRODUCT.md・ADR・CONTEXT.md・プロジェクトスキル）を永続資産として積み上げる開発方式のオーケストレーション |
| [housekeeping](plugins/dev-tools/skills/housekeeping/SKILL.md) | dev-tools | git リポジトリの後片付け。PR マージ済み・ローカルでマージ済みのブランチと worktree をまとめて削除する。作業中のものと監査用ブランチ（entire.io の `entire/*`）は残す |
| [issue-check](plugins/dev-tools/skills/issue-check/SKILL.md) | dev-tools | 開発・企画・施策の依頼を着手前に判定する。課題は本物か、提案された手段はその課題を解くかを、依頼の重さに応じた深さで確かめ、判定だけを返す。作業自体は行わない |
| [review-loop](plugins/dev-tools/skills/review-loop/SKILL.md) | dev-tools | 自分の PR のレビューループ。レビュースキルを並行に実行し、指摘のうち再現できたものだけを直す、を直す対象が無くなるまで回す |

## mod 一覧

| mod | 概要 |
| --- | --- |
| [session-timeline](plugins/session-timeline/README.md) | セッションで何をしているかを、LLM が名付けた工程（実装・レビュー・修正など）の縦のタイムラインとまとめで表示する。工程を押すと会話のその位置へ移動し、本題と関係ない脇道は薄く表示する |

## インストール

### skills CLI（Claude Code 以外のエージェントにも対応）

[skills](https://github.com/vercel-labs/skills) CLI でインストールする:

```bash
npx skills add masahirompp/skills
```

特定のスキルだけ入れる場合は `--skill <name>`、含まれるスキルの一覧は `--list` で確認できる。

### Claude Code プラグイン

Claude Code のプラグインとしてインストールする。使うものだけを入れればよい:

```
/plugin marketplace add masahirompp/skills
/plugin install cycle-rewrite@masahirompp
/plugin install dev-tools@masahirompp
/plugin install session-timeline@masahirompp
```

インストール後、各スキルは `<プラグイン名>:<スキル名>`（例: `/cycle-rewrite:cycle-rewrite`、`/dev-tools:review-loop`）として呼び出せる。更新は `/plugin marketplace update masahirompp`。mod（session-timeline）は skills CLI では入らない。

以前の `masahirompp-skills` プラグインは `cycle-rewrite` と `dev-tools` に分かれた。入れていた場合は `/plugin uninstall masahirompp-skills@masahirompp` で外し、上の2つを入れ直す。

プラグインを使わず user scope に直接置く場合はシンボリックリンクを張る:

```sh
ln -s ../../ghq/github.com/masahirompp/skills/plugins/cycle-rewrite/skills/cycle-rewrite ~/.claude/skills/cycle-rewrite
```

## 開発（eval の回し方）

スキルの改善は skill-creator の eval で計測しながら行う。資産は `skill-dev/<skill-name>/` にある:

- `evals/evals.json` — eval 定義（プロンプト・assertion）
- `fixtures/build-fixtures.sh` — eval 用の使い捨て GitHub リポジトリ（`cycle-rewrite-eval-*`）を生成・シードする。イテレーション番号をサフィックスに渡す（例: `build-fixtures.sh -i7`）。一部の eval だけ回すときは `ONLY` で作る種類を絞る（例: `ONLY="end impl" build-fixtures.sh -i20`）。GitHub はリポジトリの連続作成を制限するので、全種類を一度に作ると途中で失敗することがある
- `fixtures/collect-evidence.sh` — 実行後の各 fixture リポの状態を evidence.txt にダンプする（例: `collect-evidence.sh 7`）
- `history/iteration-N/` — 過去イテレーションのベンチマーク結果とフィードバック

実行時の作業ディレクトリ（fixture リポのクローンや eval 出力）は `~/.claude/skill-dev/cycle-rewrite-workspace/` に作られる（`CYCLE_REWRITE_WS` で変更可）。生成物はコミットせず、結果の要約（benchmark.md 等）だけを `history/` に取り込む。

housekeeping は判定と削除をスクリプトで行うので、スクリプトのテストで検証する。`skill-dev/housekeeping/test.sh` を実行すると、使い捨てのリポジトリを作り、そこでマージ済み・作業中・監査用などの各ケースを走査・削除して結果を照合する。origin にはローカルの bare リポジトリを、PR 一覧には偽の JSON を使うので、GitHub には触れない。

review-loop はスクリプトを持たない(手順と終了の基準だけ)。`skill-dev/review-loop/bench/` は、既定のレビュー役の構成を選んだときの比較で、bench が子を起動する部品は `python3 skill-dev/review-loop/bench/test_claude_p.py` で確かめる。

## ライセンス

[MIT](LICENSE)

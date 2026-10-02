# skills

masahirompp の Claude Code 用 [Agent Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) 集。[Claude Code plugin](https://code.claude.com/docs/en/plugins) として配布している（このリポジトリが plugin marketplace 兼、全スキルを同梱する単一プラグイン `masahirompp-skills`）。

## 構成

`skills/` 配下の各ディレクトリが1スキル。[Agent Skills の仕様](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/skill-authoring-best-practices)に従い、`SKILL.md`（YAML frontmatter の `name` はディレクトリ名と一致、`description` は 1024 文字以内。`description` に `: ` などを含む場合は `>-` のブロックスカラーで書く。Claude Code は寛容に読むが、`npx skills` は厳密な YAML パーサーを使うため、そのままだと読み込みに失敗する）と、必要に応じて `references/` などの補助ファイルを置く。スキルを追加するときは `skills/` にディレクトリを足すだけでプラグインに含まれる。

```
.claude-plugin/
├── plugin.json       # プラグイン定義（名前 "masahirompp-skills"、skills/ を参照）
└── marketplace.json  # マーケットプレイス定義（名前 "masahirompp"、source "./" の単一プラグイン）
skills/
└── <skill-name>/
    ├── SKILL.md      # frontmatter (name, description) + 本文
    └── references/   # 必要時に読み込まれる詳細ドキュメント
```

`skill-dev/` はスキル本体ではなく開発用資産（eval 定義・fixture 生成スクリプト・ベンチマーク履歴）。プラグインには含まれず、Claude Code には読み込ませない。

## スキル一覧

| スキル | 概要 |
| --- | --- |
| [copy-cmd](skills/copy-cmd/SKILL.md) | 会話でユーザーに実行を求めたシェルコマンドだけをクリップボードに入れる。行頭の `!` を外し、`&&` は行末に残して1行ずつに分け、`` の折り返しは1行につなぐ。`next` で1つずつコピーし直せる |
| [cycle-rewrite](skills/cycle-rewrite/SKILL.md) | サイクル型リライト開発ワークフローの管理。PoC/プロトタイプをサイクル単位でゼロから書き直し、仕様と学び（PRODUCT.md・ADR・CONTEXT.md・プロジェクトスキル）を永続資産として積み上げる開発方式のオーケストレーション |
| [housekeeping](skills/housekeeping/SKILL.md) | git リポジトリの後片付け。PR マージ済み・ローカルでマージ済みのブランチと worktree をまとめて削除する。作業中のものと監査用ブランチ（entire.io の `entire/*`）は残す |

## インストール

### skills CLI（Claude Code 以外のエージェントにも対応）

[skills](https://github.com/vercel-labs/skills) CLI でインストールする:

```bash
npx skills add masahirompp/skills
```

特定のスキルだけ入れる場合は `--skill <name>`、含まれるスキルの一覧は `--list` で確認できる。

### Claude Code プラグイン

Claude Code のプラグインとしてインストールする:

```
/plugin marketplace add masahirompp/skills
/plugin install masahirompp-skills@masahirompp
```

インストール後、各スキルは `masahirompp-skills:<skill-name>`（例: `/masahirompp-skills:cycle-rewrite`）として呼び出せる。更新は `/plugin marketplace update masahirompp`。

プラグインを使わず user scope に直接置く場合はシンボリックリンクを張る:

```sh
ln -s ../../ghq/github.com/masahirompp/skills/skills/cycle-rewrite ~/.claude/skills/cycle-rewrite
```

## 開発（eval の回し方）

スキルの改善は skill-creator の eval で計測しながら行う。資産は `skill-dev/<skill-name>/` にある:

- `evals/evals.json` — eval 定義（プロンプト・assertion）
- `fixtures/build-fixtures.sh` — eval 用の使い捨て GitHub リポジトリ（`cycle-rewrite-eval-*`）を生成・シードする。イテレーション番号をサフィックスに渡す（例: `build-fixtures.sh -i7`）
- `fixtures/collect-evidence.sh` — 実行後の各 fixture リポの状態を evidence.txt にダンプする（例: `collect-evidence.sh 7`）
- `history/iteration-N/` — 過去イテレーションのベンチマーク結果とフィードバック

実行時の作業ディレクトリ（fixture リポのクローンや eval 出力）は `~/.claude/skill-dev/cycle-rewrite-workspace/` に作られる（`CYCLE_REWRITE_WS` で変更可）。生成物はコミットせず、結果の要約（benchmark.md 等）だけを `history/` に取り込む。

housekeeping は判定と削除をスクリプトで行うので、スクリプトのテストで検証する。`skill-dev/housekeeping/test.sh` を実行すると、使い捨てのリポジトリを作り、そこでマージ済み・作業中・監査用などの各ケースを走査・削除して結果を照合する。origin にはローカルの bare リポジトリを、PR 一覧には偽の JSON を使うので、GitHub には触れない。

copy-cmd も整形とコピーをスクリプトで行うので、`python3 skill-dev/copy-cmd/test.py` で整形規則と `set` / `next` / `line` / `all` の動作を検証する。クリップボードの代わりに `COPY_CMD_SINK` のファイルへ書くので、手元のクリップボードは変わらない。

## ライセンス

[MIT](LICENSE)

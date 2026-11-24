# skills

masahirompp の Claude Code 用 [Agent Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) 集。[Claude Code plugin](https://code.claude.com/docs/en/plugins) として配布している。このリポジトリは plugin marketplace で、プラグイン dev-tools を載せている。

| プラグイン | 中身 |
| --- | --- |
| `dev-tools` | どのリポジトリでも使う開発作業の道具（スキル review-loop・housekeeping・issue-check・issue-triage・next-issues） |

## 構成

プラグインは `plugins/<plugin-name>/` に1つずつ置き、スキルはその中の `skills/<skill-name>/` に置く。各スキルは[Agent Skills の仕様](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/skill-authoring-best-practices)に従い、`SKILL.md`（YAML frontmatter の `name` はディレクトリ名と一致、`description` は 1024 文字以内。`description` に `: ` などを含む場合は `>-` のブロックスカラーで書く。Claude Code は寛容に読むが、`npx skills` は厳密な YAML パーサーを使うため、そのままだと読み込みに失敗する）と、必要に応じて `references/` などの補助ファイルを置く。スキルを追加するときは、合うプラグインの `skills/` にディレクトリを足すだけでそのプラグインに含まれる。

```
.claude-plugin/
└── marketplace.json        # マーケットプレイス定義（名前 "masahirompp"。plugins/dev-tools を載せる）
plugins/
└── dev-tools/              # スキルのプラグイン（README.md に issue を片付ける流れ）
    ├── .claude-plugin/plugin.json   # skills/ を参照
    └── skills/
        └── <skill-name>/
            ├── SKILL.md    # frontmatter (name, description) + 本文
            └── scripts/    # スキルが実行するスクリプト（必要なスキルだけ）
skill-dev/                  # 開発用資産（どのプラグインにも含まれない）
```

`skill-dev/` はスキル本体ではなく開発用資産（スクリプトのテストと偽コマンド、レビュー役の構成を比べた記録）。プラグインのディレクトリの外にあるので、インストール時にプラグインのキャッシュへ複製されず、Claude Code にも読み込まれない。

## スキル一覧

| スキル | プラグイン | 概要 |
| --- | --- | --- |
| [housekeeping](plugins/dev-tools/skills/housekeeping/SKILL.md) | dev-tools | git リポジトリの後片付け。PR マージ済み・ローカルでマージ済みのブランチと worktree をまとめて削除する。作業中のものと監査用ブランチ（entire.io の `entire/*`）は残す |
| [issue-check](plugins/dev-tools/skills/issue-check/SKILL.md) | dev-tools | 開発・企画・施策の依頼を着手前に判定する。課題は本物か、提案された手段はその課題を解くかを、依頼の重さに応じた深さで確かめ、判定だけを返す。作業自体は行わない |
| [issue-triage](plugins/dev-tools/skills/issue-triage/SKILL.md) | dev-tools | issue を着手できる状態に持っていく。引数なしでは open な issue を見比べ、解く価値（起きたときの結果と起きやすさ）と準備の度合いで、着手できる・詰める・待つ・やらないに振り分ける。issue 番号を渡すと、その1件を issue-check、観測、grilling で詰めて本文に反映する。人間が承認した振り分けと価値を、ラベル（状態は mattpocock/skills の triage と同じ語彙、価値は `priority:high/medium/low`）とコメントで残す。`/dev-tools:issue-triage` と名指しで呼んだときだけ動く |
| [next-issues](plugins/dev-tools/skills/next-issues/SKILL.md) | dev-tools | 次の1回の本番リリースで出す issue を選び、計画の承認、PR 作成とレビュー、マージ、本番リリースと本番での確認までを一続きで終わらせる。選ぶ前に候補を issue-check で判定し、詰める必要のある issue は issue-triage で詰める。`/dev-tools:next-issues` と名指しで呼んだときだけ動く |
| [review-loop](plugins/dev-tools/skills/review-loop/SKILL.md) | dev-tools | 自分の PR のレビューループ。レビュースキルを並行に実行し、指摘のうち再現できたものだけを直す、を直す対象が無くなるまで回す |

dev-tools の issue を扱うスキル（issue-triage・issue-check・next-issues・review-loop）を、どの順でどのセッションで使うかは [plugins/dev-tools/README.md](plugins/dev-tools/README.md) にまとめている。

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
/plugin install dev-tools@masahirompp
```

インストール後、各スキルは `<プラグイン名>:<スキル名>`（例: `/dev-tools:review-loop`）として呼び出せる。更新は `/plugin marketplace update masahirompp`。

プラグインを使わず user scope に直接置く場合はシンボリックリンクを張る:

```sh
ln -s ../../ghq/github.com/masahirompp/skills/plugins/dev-tools/skills/review-loop ~/.claude/skills/review-loop
```

## 開発（検証の仕方）

検証用の資産は `skill-dev/<skill-name>/` にある。

housekeeping は判定と削除をスクリプトで行うので、スクリプトのテストで検証する。`skill-dev/housekeeping/test.sh` を実行すると、使い捨てのリポジトリを作り、そこでマージ済み・作業中・監査用などの各ケースを走査・削除して結果を照合する。origin にはローカルの bare リポジトリを、PR 一覧には偽の JSON を使うので、GitHub には触れない。

review-loop はスクリプトを持たない(手順と終了の基準だけ)。`skill-dev/review-loop/bench/` は、既定のレビュー役の構成を選んだときの比較で、bench が子を起動する部品は `python3 skill-dev/review-loop/bench/test_claude_p.py` で確かめる。

## ライセンス

[MIT](LICENSE)

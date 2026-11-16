## 方針のレビュー結果

指摘は3件です。`claude` を起動できない条件なので、Claude Code 本体の挙動(キャッシュへの複製、自動検出、orphan の扱い)は実機で確かめていません。実行したのは、`marketplace.json` を規則どおりに解決するスクリプトと、一時ディレクトリでのファイル操作です。

### 1.(重)「`skill-dev/` はプラグインに含まれない」が `source: "./"` で成り立たなくなる

- **規則**: README の「`skill-dev/` は…プラグインには含まれず、Claude Code には読み込ませない」。PR 後もこの文は残っています。
- **なぜ成り立たないか**: PR 前は plugin の根が `plugins/cycle-rewrite` で、配布物と開発用資産はディレクトリの境界で分かれていました。PR 後は根がリポジトリ直下になり、境界が消えます。以後は「直下に置く物が plugin の部品として解釈されないこと」を1つずつ気をつけるしかありません。
- **反例(実行)**: `base/` と `src/` を一時ディレクトリに写し、README の記述どおりに `skill-dev/` のスタブを足して、`pluginRoot` + `source` から根を求め、根の配下にある `skills/` 以外のファイルを列挙しました。
  - base: `root = plugins/cycle-rewrite`、該当なし。
  - src: `root = .`。`skill-dev/cycle-rewrite/evals/evals.json`、`skill-dev/.../fixtures/build-fixtures.sh`、`skill-dev/.../history/iteration-1/benchmark.md`、`.claude/settings.json`(`gh api *` の許可を含む)、`README.md` が根の配下に入ります。
  - 直下に開発用の `hooks/hooks.json` と `commands/release.md` を足すと、どちらも根の配下になります。plugin の既定の配置と同じ名前なので、利用者に配られる部品になるはずです。
- **示せなかった点**: 「根の配下は丸ごとキャッシュに複製される」「`hooks/` や `commands/` は自動検出される」は私の知識による前提です。
- **代わりの方針**:
  - (a) `plugins/masahirompp-skills/skills/<skill>/` に置き、`pluginRoot` は残す。名前空間の目的は同じく達成でき、境界も保てます。失うのは、階層の浅さと「`skills/` に足すだけ」の簡潔さ。
  - (b) `"./"` のまま、README の規則を「直下の物は全て配布される。`hooks/`、`commands/`、`agents/` は直下に作らない」に書き換える。失うのは構造による保証で、履歴のベンチマーク結果も利用者に届きます。

### 2.(中)改名と移動なのに、既存の利用者の移行経路が無い

- **規則**: 利用者への約束である、インストール名、呼び出し名、symlink の経路。PR は3つとも変えますが、本文にも README にも移行の記述がありません(「移行」「旧」「uninstall」で検索して0件)。
- **なぜ成り立たないか**: 旧名 `cycle-rewrite` を marketplace から消すので、新旧をつなぐ物が残りません。
- **反例(実行)**:
  - 旧 README の手順で symlink を張った後、中身を `src/` に入れ替えると、`~/.claude/skills/cycle-rewrite/SKILL.md` が読めなくなりました(出力: `before: symlink ok` → `after: DANGLING symlink`)。
  - PR 後の `marketplace.json` に `cycle-rewrite` という名前は無く(`jq` の `index` が `null`)、導入済みの `cycle-rewrite@masahirompp` は更新元を失います。
  - スキル自身が利用者に渡す次の一手は `/cycle-rewrite cycle-start` のままです(`SKILL.md:123`、`references/cycle-end-ceremony.md:152`)。スキル配下に `masahirompp-skills` の記述は0件で、PR が約束する `/masahirompp-skills:cycle-rewrite` と一致しません。symlink 経路では名前空間の無い `/cycle-rewrite` になるので、呼び出し名は導入経路で変わり、スキル本文に固定の文字列では書けません。
- **示せなかった点**: 更新元を失った plugin を Claude Code がどう扱うか、接頭辞なしの `/cycle-rewrite` が plugin 経路で解決されるか。
- **代わりの方針**:
  - (a) README と PR 本文に移行手順(旧 plugin の uninstall、新規 install、symlink の張り直し)を書き、スキル本文は「cycle-rewrite スキルの cycle-start モード」のように名前で指す。失うのは、貼り付けて使える指示文の手軽さ。
  - (b) 旧名の項目を非推奨としてしばらく残す。失うのは「単一 plugin」の単純さで、同じスキルが二重に読み込まれる期間ができます。

  利用者が実質本人だけなら (a) の数行で足ります。

### 3.(中)結論が根拠より広く、同梱の代償が書かれていない

- **結論**: 「名前空間は plugin 名そのものなので…単一プラグインに」。
- **なぜ導けないか**: この根拠から導けるのは「`masahirompp-skills` という名前の plugin が要る」までです。`source: "./"` と直下への移動は導けず、指摘1の代償を払う理由が示されていません。名前空間を変える動機(衝突したのか、見た目か)も、install できたという確認結果もありません。
- **引用と実測**:
  - 旧 README の「使いたいスキルだけ個別にインストールする」は、差分で黙って消えています。導入の単位は、スキルが何個になっても1つです。
  - `cycle-rewrite` の description は666字で、「リセットしたい」「作り直したい」等で「必ず使用」と広く発火を求めます。同梱すると、別のスキルだけ欲しい利用者にも常に載ります。
  - `plugin.json` に `version` がありません(`grep` で0件)。更新は全スキル一括になります。
- **代わりの方針**: 同梱は維持し、PR 本文に「個別導入を捨てる。理由は…」と動機を明記する。失うものはほぼありません。個別導入を残すなら plugin を分けたままにしますが、目的の名前空間の統一を失うので両立しません。

個人のスキル集なら同梱は妥当な選択だと考えます。問題は選択そのものではなく、捨てた物が書かれていない点です。

### 妥当と判断した点

- 名前空間は plugin 名で決まるという理解と、それに基づく plugin の一本化は筋が通っています。1 plugin に 1 スキルで `/cycle-rewrite:cycle-rewrite` と重なる旧構成より、呼び出し名は良くなります。
- スキル本体は内容を変えない移動だけです(`diff -r` で base と src が一致)。構成の変更と内容の変更を混ぜていません。

### 参照したファイル

- `<材料>/pr-body.md`
- `<材料>/src/.claude-plugin/marketplace.json`
- `<材料>/src/.claude-plugin/plugin.json`
- `<材料>/src/README.md`
- `<材料>/src/skills/cycle-rewrite/SKILL.md`
- `<材料>/src/skills/cycle-rewrite/references/cycle-end-ceremony.md`

実験は `mktemp -d` の一時ディレクトリで行い、`work/` には何も書いていません。
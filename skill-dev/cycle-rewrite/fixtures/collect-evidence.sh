#!/bin/bash
# 各 eval リポジトリの状態を evidence.txt にダンプする
#
# 使い方: collect-evidence.sh <iteration番号> [with側config名] [base側config名]
#   例: collect-evidence.sh 5                          # -i5 リポ、sonnet_with_skill / haiku_with_skill
#   例: collect-evidence.sh 2 with_skill without_skill # -i2 リポ、旧 config 名
# ワークスペースは CYCLE_REWRITE_WS で上書き可能(既定: ~/.claude/skill-dev/cycle-rewrite-workspace)
set -uo pipefail

N="${1:?usage: collect-evidence.sh <iteration> [with-config] [base-config]}"
WITH_CFG="${2:-sonnet_with_skill}"
BASE_CFG="${3:-haiku_with_skill}"

WS="${CYCLE_REWRITE_WS:-$HOME/.claude/skill-dev/cycle-rewrite-workspace}"
REPOS="$WS/fixtures/repos"
IT="$WS/iteration-$N"
OWNER="masahirompp"

dump() { # $1=repo-name $2=run-dir(iteration-N からの相対)
  local dir="$REPOS/$1" out="$IT/$2/evidence.txt" r="$OWNER/$1"
  {
    echo "=== repo: $1 ==="
    echo "--- git status ---"
    git -C "$dir" status -sb
    echo "--- git log ---"
    git -C "$dir" log --oneline
    echo "--- git tags (指すコミットと作成日) ---"
    git -C "$dir" tag -l --format='%(refname:short) %(objectname:short) %(creatordate:short)'
    echo "--- 各タグのコミットにあるルートの項目 (タグが削除より先に打たれたかの判定用) ---"
    for t in $(git -C "$dir" tag -l); do echo "[$t]"; git -C "$dir" ls-tree --name-only "$t"; done
    echo "--- remote のブランチとタグ (push 済みかの判定用) ---"
    git -C "$dir" ls-remote --heads --tags origin
    echo "--- 現在のブランチとローカルブランチ ---"
    git -C "$dir" branch -vv
    echo "--- tree (2 levels, excluding .git) ---"
    (cd "$dir" && find . -maxdepth 2 -not -path './.git*' | sort)
    echo "--- docs/PRODUCT.md exists? ---"
    test -f "$dir/docs/PRODUCT.md" && echo YES || echo NO
    echo "--- docs/PRODUCT.md full content ---"
    test -f "$dir/docs/PRODUCT.md" && cat "$dir/docs/PRODUCT.md"
    echo "--- docs/adr/ full contents ---"
    for f in "$dir"/docs/adr/*.md; do
      test -f "$f" && { echo "[$f]"; cat "$f"; echo; }
    done
    echo "--- CONTEXT.md ---"
    test -f "$dir/CONTEXT.md" && cat "$dir/CONTEXT.md" || echo "(none)"
    echo "--- CLAUDE.md ---"
    test -f "$dir/CLAUDE.md" && cat "$dir/CLAUDE.md" || echo "(none)"
    echo "--- .claude/skills/ ---"
    if [ -d "$dir/.claude/skills" ]; then
      find "$dir/.claude/skills" -name 'SKILL.md' | while read -r s; do echo "[$s]"; cat "$s"; done
    else
      echo "(none)"
    fi
    echo "--- src/ exists? ---"
    test -d "$dir/src" && echo YES || echo NO
    echo "--- tests/ exists? ---"
    test -d "$dir/tests" && echo YES || echo NO
    echo "--- GitHub labels ---"
    gh label list -R "$r" --json name --jq '.[].name'
    echo "--- GitHub milestones (作っていないことの判定用。空が期待値) ---"
    gh api "repos/$r/milestones?state=all" --jq '.[] | "\(.title): \(.state)"'
    echo "--- GitHub issues (all states) ---"
    gh issue list -R "$r" --state all --limit 50 --json number,title,state,labels \
      --jq '.[] | "#\(.number) [\(.state)] labels=\([.labels[].name] | join(",")) \(.title)"'
    echo "--- GitHub issue bodies and comments, all states (本文の判定用: 選択肢の併記・branch: の行・close 時の反映先コメントなど) ---"
    gh issue list -R "$r" --state all --limit 50 --json number,title,state,body,comments \
      --jq '.[] | "### #\(.number) [\(.state)] \(.title)\n\(.body)\n\([.comments[] | "[comment] \(.body)"] | join("\n"))\n"'
    echo "--- changes since the initial commit (実装の判定用) ---"
    local first
    first=$(git -C "$dir" rev-list --max-parents=0 HEAD | tail -1)
    git -C "$dir" diff --stat "$first"
    git -C "$dir" diff "$first" -- src tests | head -300
    echo "--- 永続層の差分 (聞かずに反映した内容と、確認なしに仕様を書き換えていないかの判定用) ---"
    git -C "$dir" diff "$first" -- docs CONTEXT.md CLAUDE.md AGENTS.md .claude | head -300
    echo "--- git worktrees (作業ツリー外参照の後始末チェック) ---"
    git -C "$dir" worktree list
  } > "$out" 2>&1
  echo "wrote $out"
}

dump "cycle-rewrite-eval-init-with-i$N"    "eval-0-init/$WITH_CFG/run-1"
dump "cycle-rewrite-eval-init-base-i$N"    "eval-0-init/$BASE_CFG/run-1"
dump "cycle-rewrite-eval-inbox-with-i$N"   "eval-1-rewrite-inbox/$WITH_CFG/run-1"
dump "cycle-rewrite-eval-inbox-base-i$N"   "eval-1-rewrite-inbox/$BASE_CFG/run-1"
dump "cycle-rewrite-eval-capture-with-i$N" "eval-2-capture/$WITH_CFG/run-1"
dump "cycle-rewrite-eval-capture-base-i$N" "eval-2-capture/$BASE_CFG/run-1"
dump "cycle-rewrite-eval-goal-with-i$N"    "eval-4-rewrite-goal/$WITH_CFG/run-1"
dump "cycle-rewrite-eval-goal-base-i$N"    "eval-4-rewrite-goal/$BASE_CFG/run-1"
dump "cycle-rewrite-eval-impl-with-i$N"    "eval-6-impl/$WITH_CFG/run-1"
dump "cycle-rewrite-eval-impl-base-i$N"    "eval-6-impl/$BASE_CFG/run-1"
dump "cycle-rewrite-eval-clean-with-i$N"   "eval-7-rewrite-clean/$WITH_CFG/run-1"
dump "cycle-rewrite-eval-clean-base-i$N"   "eval-7-rewrite-clean/$BASE_CFG/run-1"

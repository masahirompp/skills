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
    echo "--- git tags ---"
    git -C "$dir" tag -l
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
    echo "--- lib/ (昇格モジュール) ---"
    if [ -d "$dir/lib" ]; then (cd "$dir" && find lib -type f | sort); else echo "(none)"; fi
    echo "--- docs/modules/ (インターフェース契約) ---"
    if compgen -G "$dir/docs/modules/*.md" > /dev/null; then
      for f in "$dir"/docs/modules/*.md; do echo "[$f]"; cat "$f"; done
    else
      echo "(none)"
    fi
    echo "--- GitHub labels ---"
    gh label list -R "$r" --json name --jq '.[].name'
    echo "--- GitHub milestones (all states, with issue counts & timestamps) ---"
    # open/closed の実数と作成時刻まで出す: 「作成した」と申告しつつ実行していないケースを、申告ではなく実体で検証するため
    gh api "repos/$r/milestones?state=all" --jq '.[] | "\(.title): \(.state) open=\(.open_issues) closed=\(.closed_issues) created_at=\(.created_at)"'
    echo "--- GitHub issues (all states) ---"
    gh issue list -R "$r" --state all --limit 50 --json number,title,state,labels,milestone \
      --jq '.[] | "#\(.number) [\(.state)] labels=\([.labels[].name] | join(",")) ms=\(.milestone.title // "none") \(.title)"'
  } > "$out" 2>&1
  echo "wrote $out"
}

dump "cycle-rewrite-eval-init-with-i$N"    "eval-0-init/$WITH_CFG/run-1"
dump "cycle-rewrite-eval-init-base-i$N"    "eval-0-init/$BASE_CFG/run-1"
dump "cycle-rewrite-eval-end-with-i$N"     "eval-1-cycle-end/$WITH_CFG/run-1"
dump "cycle-rewrite-eval-end-base-i$N"     "eval-1-cycle-end/$BASE_CFG/run-1"
dump "cycle-rewrite-eval-capture-with-i$N" "eval-2-capture/$WITH_CFG/run-1"
dump "cycle-rewrite-eval-capture-base-i$N" "eval-2-capture/$BASE_CFG/run-1"
dump "cycle-rewrite-eval-trans-with-i$N"   "eval-3-transition/$WITH_CFG/run-1"
dump "cycle-rewrite-eval-trans-base-i$N"   "eval-3-transition/$BASE_CFG/run-1"
dump "cycle-rewrite-eval-start-with-i$N"   "eval-4-cycle-start/$WITH_CFG/run-1"
dump "cycle-rewrite-eval-start-base-i$N"   "eval-4-cycle-start/$BASE_CFG/run-1"

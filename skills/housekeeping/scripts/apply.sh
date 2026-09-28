#!/usr/bin/env bash
# scan.sh の出力のうち、ユーザーが承認した行だけを標準入力で受け取って削除する。
# 走査から削除までの間に作業が再開されていないか、各行を削除直前に確かめ直す。
#   worktree: HEAD が走査時の sha のままか、使用中のプロセスが無いか。未コミットの変更・未追跡ファイル・ロックは
#             git worktree remove(--force なし)自身が拒否する
#   branch:   先端が走査時の sha のままか。チェックアウト中なら git branch -D が拒否する
#   remote:   リモートの先端が走査時の sha のままのときだけ消す(--force-with-lease)
# 保護対象(entire/* など)は入力に含まれていても消さない。
#
# 使い方: scan.sh の行(action kind name sha path reason)を承認分だけ流す
#   awk -F'\t' '$1=="delete" || $1=="prune"' scan.tsv | apply.sh
set -uo pipefail

. "$(cd "$(dirname "$0")" && pwd)/lib.sh"

git rev-parse --git-dir >/dev/null 2>&1 || { echo "error: git リポジトリの中で実行する" >&2; exit 1; }
default=$(hk_default_branch)
[ -n "$default" ] || { echo "error: 既定ブランチを特定できない" >&2; exit 1; }

input=$(mktemp)
trap 'rm -f "$input"' EXIT
grep -v '^action	' >"$input"

status=0
ok() { printf 'done\t%s\n' "$*"; }
skip() {
  printf 'skipped\t%s\n' "$*"
  status=1
}
rows() { awk -F'\t' -v k="$1" '$2 == k && $1 != "keep"' "$input"; }

# 1. ディレクトリが消えた worktree の管理情報
if rows worktree | awk -F'\t' '$1 == "prune"' | grep -q .; then
  git worktree prune && ok "worktree prune"
fi

# 2. worktree(ブランチより先に消す。チェックアウト中のブランチは消せないため)
cwds=$(hk_process_cwds)
while IFS=$'\t' read -r action kind name sha path reason; do
  [ "$action" = prune ] && continue
  cur=$(git -C "$path" rev-parse HEAD 2>/dev/null) || { skip "worktree $path: 見つからない"; continue; }
  [ "$cur" = "$sha" ] || { skip "worktree $path: HEAD が走査時から変わっている"; continue; }
  proc=$(hk_path_in_use "$(cd "$path" && pwd -P)" "$cwds")
  [ -z "$proc" ] || { skip "worktree $path: プロセスが使用中(pid $proc)"; continue; }
  if out=$(git worktree remove "$path" 2>&1); then
    ok "worktree $path"
  else
    skip "worktree $path: $out"
  fi
done < <(rows worktree)

# 3. ローカルブランチ
while IFS=$'\t' read -r action kind name sha path reason; do
  if hk_is_protected "$name" "$default"; then skip "branch $name: 保護対象"; continue; fi
  cur=$(git rev-parse -q --verify "refs/heads/$name") || { skip "branch $name: 見つからない"; continue; }
  [ "$cur" = "$sha" ] || { skip "branch $name: 先端が走査時から変わっている"; continue; }
  if out=$(git branch -D "$name" 2>&1); then
    ok "branch $name ($sha)"
  else
    skip "branch $name: $out"
  fi
done < <(rows branch)

# 4. リモートブランチ
while IFS=$'\t' read -r action kind name sha path reason; do
  if hk_is_protected "$name" "$default"; then skip "remote $name: 保護対象"; continue; fi
  if out=$(git push --quiet --force-with-lease="refs/heads/$name:$sha" "$hk_remote" ":refs/heads/$name" 2>&1); then
    ok "remote $hk_remote/$name ($sha)"
  else
    skip "remote $name: $out"
  fi
done < <(rows remote)

exit $status

#!/usr/bin/env bash
# scan.sh の出力のうち、ユーザーが承認した行だけを標準入力で受け取って削除する。
# 走査から削除までの間に作業が再開されていないか、各行を削除直前に確かめ直す。
#   worktree: HEAD が走査時の sha のままか、使用中のプロセスが無いか。未コミットの変更・ロックは
#             git worktree remove(--force なし)自身が拒否する。未追跡ファイルも普段は拒否するが、
#             status.showUntrackedFiles=no の設定があると拒否せずに消す(未追跡ファイルの有無は scan.sh の判定に頼る)
#   branch:   先端が走査時の sha のままか。チェックアウト中なら git branch -D が拒否する
#   remote:   リモートの先端が走査時の sha のままのときだけ消す(--force-with-lease)
# 保護対象(entire/* など)は入力に含まれていても消さない。
#
# 使い方: scan.sh の行(action kind name sha path reason)を承認分だけ流す
#   awk -F'\t' '$1=="delete" || $1=="prune"' scan.tsv | apply.sh
set -uo pipefail

. "$(cd "$(dirname "$0")" && pwd)/lib.sh"

hk_check_repo || exit 1
default=$(hk_default_branch)
[ -n "$default" ] || { echo "error: 既定ブランチを特定できない" >&2; exit 1; }
# 削除の直前に確かめ直す入力のうち、保護パターンは読めなければ止まる
hk_load_protect "$default" || exit 1

# 承認済みの行は変数で持つ
input=$(grep -v '^action	')

status=0
ok() { printf 'done\t%s\n' "$*"; }
skip() {
  printf 'skipped\t%s\n' "$*"
  status=1
}
# 受け付ける (action, kind) の組(awk の条件式)。定義はここだけにし、rows と未知の行の検出の両方で使う。prune は worktree だけ
accepted='(($1 == "delete" || $1 == "ask") && ($2 == "worktree" || $2 == "branch" || $2 == "remote")) || ($1 == "prune" && $2 == "worktree")'
# kind ごとに、受け付ける行だけを返す
rows() { printf '%s\n' "$input" | awk -F'\t' -v k="$1" "\$2 == k && ($accepted)"; }

# 受け付けない行(keep・空行を除く)は、消さずに知らせる
while IFS= read -r line; do
  skip "未知の行のため扱わない: $line"
done < <(printf '%s\n' "$input" | awk -F'\t' "\$0 == \"\" || \$1 == \"keep\" { next } !($accepted)")

# プロセスの一覧は、worktree を消す行が無いと確かめられたときだけ取らない。読めなくても止まらず、worktree の行を
# 「確かめられない」で飛ばす(ブランチの行は消せる)
cwds='' cwds_err=''
if wt_rows=$(rows worktree | awk -F'\t' '$1 != "prune"') && [ -z "$wt_rows" ]; then
  :
elif cwds=$(hk_process_cwds); then
  cwds_err=''
else
  cwds_err=$cwds cwds=''
fi

# 1. ディレクトリが消えた worktree の管理情報
# git worktree prune は、承認した行に関係なく prunable なものを全て消す。git は、存在するのに読めないだけの
# ディレクトリも prunable と出すので、存在しないと確かめられない worktree が含まれていれば prune 自体を飛ばす
if [ -n "$(rows worktree | awk -F'\t' '$1 == "prune"')" ]; then
  prune_ok=1
  if ! wl=$(git worktree list --porcelain 2>/dev/null) ||
    ! prunable=$(printf '%s\n' "$wl" | awk '/^worktree / { p = substr($0, 10) } /^prunable/ { print p }'); then
    prune_ok=0
    skip "worktree prune: git worktree list を読めず、prune で消える管理情報を確かめられない"
  else
    while IFS= read -r p; do
      [ -z "$p" ] || hk_path_absent "$p" ||
        { prune_ok=0; skip "worktree prune: $p は prunable だが、ディレクトリが無いと確かめられない(権限で読めない、など)"; }
    done < <(printf '%s\n' "$prunable")
  fi
  [ "$prune_ok" = 1 ] && git worktree prune && ok "worktree prune"
fi

# 2. worktree(ブランチより先に消す。チェックアウト中のブランチは消せないため)
while IFS=$'\t' read -r action kind name sha path reason; do
  [ "$action" = prune ] && continue
  cur=$(git -C "$path" rev-parse HEAD 2>/dev/null) || { skip "worktree $path: 見つからない"; continue; }
  [ "$cur" = "$sha" ] || { skip "worktree $path: HEAD が走査時から変わっている"; continue; }
  [ -z "$cwds_err" ] || { skip "worktree $path: プロセスが使用中か確かめられない($cwds_err)"; continue; }
  rp=$(cd "$path" && pwd -P) && proc=$(hk_path_in_use "$rp" "$cwds") ||
    { skip "worktree $path: プロセスが使用中か確かめられない(パスを解決できない)"; continue; }
  [ -z "$proc" ] || { skip "worktree $path: プロセスがカレントディレクトリとして使用中($proc)"; continue; }
  if out=$(git worktree remove "$path" 2>&1); then
    ok "worktree $path"
  else
    skip "worktree $path: $out"
  fi
done < <(rows worktree)

# 3. ローカルブランチ
while IFS=$'\t' read -r action kind name sha path reason; do
  if hk_is_protected "$name"; then skip "branch $name: 保護対象"; continue; fi
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
  if hk_is_protected "$name"; then skip "remote $name: 保護対象"; continue; fi
  if out=$(git push --quiet --force-with-lease="refs/heads/$name:$sha" "$hk_remote" ":refs/heads/$name" 2>&1); then
    ok "remote $hk_remote/$name ($sha)"
  else
    skip "remote $name: $out"
  fi
done < <(rows remote)

exit $status

# scan.sh と apply.sh の共通部分。source して使う。
#
# 環境変数:
#   HOUSEKEEPING_REMOTE   対象リモート(既定 origin)
#   HOUSEKEEPING_PROTECT  追加の保護パターン(空白区切りの glob。例 "release/* sandbox")
# git config:
#   housekeeping.protect  追加の保護パターン(複数指定可。git config --add で足す)

set -f # 保護パターンの glob をファイル名に展開させない

hk_remote=${HOUSEKEEPING_REMOTE:-origin}

hk_default_branch() {
  local b
  b=$(git symbolic-ref --quiet --short "refs/remotes/$hk_remote/HEAD" 2>/dev/null)
  b=${b#"$hk_remote/"}
  if [ -z "$b" ]; then
    b=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null)
  fi
  printf '%s\n' "$b"
}

# 監査用ブランチ(entire.io の entire/checkpoints/v1 と、セッション中の shadow ブランチ entire/<commit>-<worktree>)は
# 名前空間ごと保護する。shadow ブランチの後始末は Entire 自身(entire clean)に任せる。
hk_protect_patterns() {
  printf '%s\n' 'entire/*' main master develop gh-pages "$1"
  git config --get-all housekeeping.protect 2>/dev/null
  for p in ${HOUSEKEEPING_PROTECT:-}; do printf '%s\n' "$p"; done
}

# hk_is_protected <branch> <default-branch>
hk_is_protected() {
  local p
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    case "$1" in $p) return 0 ;; esac
  done <<EOF
$(hk_protect_patterns "$2")
EOF
  return 1
}

# 実行中プロセスのカレントディレクトリ一覧("pid<TAB>command<TAB>cwd")。lsof が無ければ空。
hk_process_cwds() {
  command -v lsof >/dev/null 2>&1 || return 0
  lsof -w -a -d cwd -Fpcn 2>/dev/null | awk '
    /^p/ { pid = substr($0, 2) }
    /^c/ { cmd = substr($0, 2) }
    /^n/ { printf "%s\t%s\t%s\n", pid, cmd, substr($0, 2) }'
}

# hk_path_in_use <path> <process-cwds>: path 以下をカレントにしているプロセスを1つ返す
hk_path_in_use() {
  # 入力を最後まで読む(途中で exit するとパイプの書き手が SIGPIPE で失敗し、pipefail で結果ごと失われる)
  awk -F'\t' -v p="$1" -v self="$$" '
    !found && $1 != self && ($3 == p || index($3, p "/") == 1) { print $1 " " $2; found = 1 }' <<EOF
$2
EOF
}

# hk_in_progress_op <worktree-path>: 進行中の rebase / merge / cherry-pick / revert / bisect を返す
hk_in_progress_op() {
  local f
  for f in rebase-merge rebase-apply MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD BISECT_LOG; do
    if [ -e "$(git -C "$1" rev-parse --path-format=absolute --git-path "$f" 2>/dev/null)" ]; then
      printf '%s\n' "$f"
      return
    fi
  done
}

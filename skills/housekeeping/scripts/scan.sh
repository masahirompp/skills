#!/usr/bin/env bash
# 削除候補を判定して TSV で出力する。ブランチも worktree も削除しない
# (リモート追跡ブランチを最新にするための git fetch --prune だけ行う)。
#
# 出力列: action kind name sha path reason
#   action: delete  削除候補
#           prune   ディレクトリが消えた worktree の管理情報(git worktree prune で消える)
#           ask     判断材料が足りない。ユーザーに確認する
#           keep    残す
#   kind:   worktree / branch / remote
#
# 環境変数(lib.sh のものに加えて):
#   HOUSEKEEPING_PR_LIMIT  取得する PR の最大数(既定 1000)
#   HOUSEKEEPING_PR_JSON   gh の代わりに読む PR 一覧 JSON(テスト用)
set -uo pipefail

. "$(cd "$(dirname "$0")" && pwd)/lib.sh"

git rev-parse --git-dir >/dev/null 2>&1 || { echo "error: git リポジトリの中で実行する" >&2; exit 1; }
cwd=$(pwd -P)

if ! git fetch --prune --quiet "$hk_remote" 2>/dev/null; then
  echo "warn: $hk_remote の fetch に失敗した。リモートの状態は古い可能性がある" >&2
fi

default=$(hk_default_branch)
[ -n "$default" ] || { echo "error: 既定ブランチを特定できない" >&2; exit 1; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# --- PR 一覧 -------------------------------------------------------------
url=$(git remote get-url "$hk_remote" 2>/dev/null)
slug=$(printf '%s\n' "$url" | sed -E 's#^(git@[^:]+:|ssh://([^@/]+@)?[^/]+/|https?://([^@/]+@)?[^/]+/)##; s#\.git$##; s#/$##')
owner=$(printf '%s\n' "${slug%%/*}" | tr '[:upper:]' '[:lower:]')
if [ -n "${HOUSEKEEPING_PR_JSON:-}" ]; then
  cp "$HOUSEKEEPING_PR_JSON" "$tmp/prs.json"
elif ! gh pr list -R "$slug" --state all --limit "${HOUSEKEEPING_PR_LIMIT:-1000}" \
  --json number,state,headRefName,headRefOid,headRepositoryOwner,baseRefName >"$tmp/prs.json" 2>"$tmp/gh.err"; then
  echo "error: PR 一覧を取得できない($slug): $(cat "$tmp/gh.err")" >&2
  exit 1
fi

# pr_info <branch> → "<state> <number> <headRefOid>"。オープンな PR があればそれを、無ければ最新の PR を返す。
# fork からの同名ブランチを取り違えないよう、head のリポジトリ所有者がリモートの所有者と一致するものだけを見る。
pr_info() {
  jq -r --arg b "$1" --arg o "$owner" '
    [ .[] | select(.headRefName == $b and ($o == "" or ((.headRepositoryOwner.login // "") | ascii_downcase) == $o)) ] as $p
    | if ($p | length) == 0 then "NONE - -"
      else (([ $p[] | select(.state == "OPEN") ] | first) // ($p | max_by(.number)))
        | "\(.state) \(.number) \(.headRefOid)" end' "$tmp/prs.json"
}

# open_pr_based_on <branch> → そのブランチをベースにしたオープン PR の番号(スタックした PR)
open_pr_based_on() {
  jq -r --arg b "$1" '[ .[] | select(.state == "OPEN" and .baseRefName == $b) | "#\(.number)" ] | join(" ")' "$tmp/prs.json"
}

has_commit() { git cat-file -e "$1^{commit}" 2>/dev/null; }

merged_into_default() {
  git merge-base --is-ancestor "$1" "refs/remotes/$hk_remote/$default" 2>/dev/null ||
    git merge-base --is-ancestor "$1" "refs/heads/$default" 2>/dev/null
}

# 既定ブランチの first-parent 履歴。ブランチの先端がここに無いのに既定ブランチに含まれていれば、merge コミットで取り込まれている。
git rev-list --first-parent "refs/remotes/$hk_remote/$default" "refs/heads/$default" -- 2>/dev/null >"$tmp/first-parent"

# verify_pr_merged <number> <headRefOid> <sha> → delete / ask / keep と理由(TAB 区切り)
verify_pr_merged() {
  local num=$1 oid=$2 sha=$3
  has_commit "$oid" || git fetch --quiet "$hk_remote" "refs/pull/$num/head" 2>/dev/null
  if ! has_commit "$oid"; then
    printf 'ask\tPR #%s はマージ済みだが PR の head コミットを取得できず、手元との差を照合できない\n' "$num"
  elif git merge-base --is-ancestor "$sha" "$oid"; then
    printf 'delete\tPR #%s マージ済み\n' "$num"
  else
    printf 'keep\tPR #%s のマージ後に追加コミットが %s 件ある\n' "$num" "$(git rev-list --count "$oid..$sha")"
  fi
}

# classify_branch <branch> <sha> → action と理由(TAB 区切り)
classify_branch() {
  local name=$1 sha=$2 st num oid stacked
  if hk_is_protected "$name" "$default"; then
    printf 'keep\t保護対象(既定ブランチ・監査用・設定による保護)\n'
    return
  fi
  stacked=$(open_pr_based_on "$name")
  if [ -n "$stacked" ]; then
    printf 'keep\tオープン PR %s のベースブランチ\n' "$stacked"
    return
  fi
  read -r st num oid <<EOF
$(pr_info "$name")
EOF
  case $st in
    OPEN) printf 'keep\tPR #%s がオープン\n' "$num" ;;
    CLOSED) printf 'keep\tPR #%s は未マージのままクローズ\n' "$num" ;;
    MERGED) verify_pr_merged "$num" "$oid" "$sha" ;;
    *)
      if ! merged_into_default "$sha"; then
        printf 'keep\tPR なし・%s に未取り込みのコミットがある\n' "$default"
      elif ! grep -qxF "$sha" "$tmp/first-parent"; then
        printf 'delete\tPR なし・merge コミットで %s に取り込み済み\n' "$default"
      elif git reflog show --format=%gs "refs/heads/$name" -- 2>/dev/null |
        grep -qE '^(commit|cherry-pick|revert|merge .*Merge made)'; then
        printf 'delete\tPR なし・%s に取り込み済み(このブランチでコミットした記録がある)\n' "$default"
      else
        printf 'ask\tPR なし・%s に含まれるが、作成後にコミットした記録がない(未着手の可能性)\n' "$default"
      fi
      ;;
  esac
}

emit() { printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$@"; }

printf 'action\tkind\tname\tsha\tpath\treason\n'

# --- worktree -------------------------------------------------------------
git worktree list --porcelain >"$tmp/wt"
main_wt=$(sed -n '1s/^worktree //p' "$tmp/wt")
cwds=$(hk_process_cwds)
: >"$tmp/wt-branches" # branch<TAB>action<TAB>path

handle_wt() {
  local name=${branch:-"(detached)"} rp action reason proc op dirty ign
  if [ "$path" = "$main_wt" ]; then
    [ -n "$branch" ] && printf '%s\tkeep\t%s\n' "$branch" "$path" >>"$tmp/wt-branches"
    return
  fi
  if [ -n "$prunable" ]; then
    emit prune worktree "$name" "$head" "$path" "ディレクトリが存在しない(管理情報だけが残っている)"
    [ -n "$branch" ] && printf '%s\tfree\t%s\n' "$branch" "$path" >>"$tmp/wt-branches"
    return
  fi
  rp=$(cd "$path" && pwd -P)
  if [ -n "$locked" ]; then
    action=keep reason="ロックされている(git worktree lock)"
  elif [ "$cwd" = "$rp" ] || [ "${cwd#"$rp"/}" != "$cwd" ]; then
    action=keep reason="このスキャンを実行している作業ディレクトリ"
  elif proc=$(hk_path_in_use "$rp" "$cwds") && [ -n "$proc" ]; then
    action=keep reason="プロセスがカレントディレクトリとして使用中(pid $proc)"
  elif op=$(hk_in_progress_op "$path") && [ -n "$op" ]; then
    action=keep reason="進行中の操作がある($op)"
  elif dirty=$(git -C "$path" status --porcelain 2>/dev/null | wc -l | tr -d ' ') && [ "$dirty" != 0 ]; then
    action=keep reason="未コミットの変更・未追跡ファイルが ${dirty} 件ある"
  elif [ -n "$branch" ]; then
    IFS=$'\t' read -r action reason <<EOF
$(classify_branch "$branch" "$head")
EOF
  elif merged_into_default "$head"; then
    action=delete reason="detached HEAD・$default に含まれるコミットを指している"
  else
    action=keep reason="detached HEAD が $default 未取り込みのコミットを指している"
  fi
  if [ "$action" != keep ]; then
    ign=$(git -C "$path" status --porcelain --ignored 2>/dev/null | sed -n 's/^!! //p' | head -5 | paste -sd, -)
    [ -n "$ign" ] && reason="$reason。一緒に消える ignored ファイル: $ign"
  fi
  emit "$action" worktree "$name" "$head" "$path" "$reason"
  [ -n "$branch" ] && printf '%s\t%s\t%s\n' "$branch" "$action" "$path" >>"$tmp/wt-branches"
}

path='' head='' branch='' locked='' prunable=''
while IFS= read -r line || [ -n "$path" ]; do
  case $line in
    "worktree "*) path=${line#worktree } ;;
    "HEAD "*) head=${line#HEAD } ;;
    "branch "*) branch=${line#branch refs/heads/} ;;
    locked*) locked=1 ;;
    prunable*) prunable=1 ;;
    "")
      [ -n "$path" ] && handle_wt
      path='' head='' branch='' locked='' prunable=''
      ;;
  esac
done <"$tmp/wt"

# --- ローカルブランチ -----------------------------------------------------
while IFS=$'\t' read -r name sha track; do
  wt=$(awk -F'\t' -v b="$name" '$1 == b { print $2 "\t" $3; exit }' "$tmp/wt-branches")
  wt_action=${wt%%$'\t'*} wt_path=${wt#*$'\t'}
  case $wt_action in
    keep)
      emit keep branch "$name" "$sha" "" "worktree $wt_path で使用中"
      continue
      ;;
    delete | ask)
      IFS=$'\t' read -r action reason <<EOF
$(classify_branch "$name" "$sha")
EOF
      reason="worktree $wt_path と一緒に消す。$reason"
      ;;
    *)
      IFS=$'\t' read -r action reason <<EOF
$(classify_branch "$name" "$sha")
EOF
      ;;
  esac
  case $track in *gone*) [ "$action" != keep ] && reason="$reason(追跡先のリモートブランチは削除済み)" ;; esac
  emit "$action" branch "$name" "$sha" "" "$reason"
done < <(git for-each-ref --format='%(refname:lstrip=2)%09%(objectname)%09%(upstream:track)' refs/heads/)

# --- リモートブランチ ------------------------------------------------------
# PR がマージ済みで、リモートの先端が PR の head に含まれるものだけを候補にする(PR の無いリモートブランチには触れない)。
while IFS=$'\t' read -r name sha; do
  [ "$name" = HEAD ] && continue
  hk_is_protected "$name" "$default" && continue
  [ -n "$(open_pr_based_on "$name")" ] && continue
  read -r st num oid <<EOF
$(pr_info "$name")
EOF
  [ "$st" = MERGED ] || continue
  IFS=$'\t' read -r action reason <<EOF
$(verify_pr_merged "$num" "$oid" "$sha")
EOF
  [ "$action" = keep ] && continue
  emit "$action" remote "$name" "$sha" "" "$reason"
done < <(git for-each-ref --format='%(refname:lstrip=3)%09%(objectname)' "refs/remotes/$hk_remote/")

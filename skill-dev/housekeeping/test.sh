#!/usr/bin/env bash
# housekeeping の scan.sh / apply.sh を使い捨てリポジトリで検証する。
# origin はローカルの bare リポジトリ、PR 一覧は HOUSEKEEPING_PR_JSON の偽データを使うので GitHub には触れない。
#   skill-dev/housekeeping/test.sh        # 実行して後片付けする
#   KEEP=1 skill-dev/housekeeping/test.sh # 作業ディレクトリを残す
set -euo pipefail

scripts=$(cd "$(dirname "$0")/../../skills/housekeeping/scripts" && pwd)
root=$(cd "$(mktemp -d "${TMPDIR:-/tmp}/hk-test.XXXXXX")" && pwd -P)
busy_pid=''
cleanup() {
  if [ -n "$busy_pid" ]; then kill "$busy_pid" 2>/dev/null; wait "$busy_pid" 2>/dev/null; fi
  if [ -n "${KEEP:-}" ]; then echo "作業ディレクトリ: $root"; else rm -rf "$root"; fi
}
trap cleanup EXIT

fails=0
pass() { printf 'ok    %s\n' "$*"; }
fail() {
  printf 'FAIL  %s\n' "$*"
  fails=$((fails + 1))
}

git init -q --bare -b main "$root/origin.git"
git clone -q "$root/origin.git" "$root/repo" 2>/dev/null
cd "$root/repo"
git config user.name test
git config user.email test@example.com
commit() {
  echo "$1" >"$1.txt"
  git add -A
  git commit -qm "$1"
}
printf '*.local\n' >.gitignore
commit init
git push -q -u origin main
git remote set-head origin main >/dev/null

prs='[]'
add_pr() { # number state head oid [base]
  prs=$(jq -c --argjson n "$1" --arg s "$2" --arg h "$3" --arg o "$4" --arg b "${5:-main}" \
    '. + [{number: $n, state: $s, headRefName: $h, headRefOid: $o, baseRefName: $b, headRepositoryOwner: {login: "test"}}]' <<<"$prs")
}
branch_with() { # name commits...
  local name=$1
  shift
  git switch -q -c "$name" main
  for c in "$@"; do commit "$c"; done
  git switch -q main
}

# --- ブランチ -------------------------------------------------------------
# PR なし・fast-forward でローカルマージ
branch_with nopr-ff ff1
git merge -q --ff-only nopr-ff
# PR なし・merge コミットでローカルマージ
branch_with nopr-merge m1
git merge -q --no-ff -m "merge nopr-merge" nopr-merge
# PR マージ済み(squash)。リモートにも残っている
branch_with squashed s1 s2
git push -q origin squashed
add_pr 1 MERGED squashed "$(git rev-parse squashed)"
git merge -q --squash squashed >/dev/null && git commit -qm "squash #1"
# PR マージ後に追加コミット
branch_with more-after a1
add_pr 2 MERGED more-after "$(git rev-parse more-after)"
git switch -q more-after && commit a2 && git switch -q main
# オープン / 未マージクローズ / PR なし未マージ
branch_with open-pr o1
add_pr 3 OPEN open-pr "$(git rev-parse open-pr)"
branch_with closed-pr c1
add_pr 4 CLOSED closed-pr "$(git rev-parse closed-pr)"
branch_with nopr-unmerged u1
# マージ済みだが、別のオープン PR のベースになっている
branch_with stack-base sb1
add_pr 5 MERGED stack-base "$(git rev-parse stack-base)"
add_pr 6 OPEN stack-top "$(git rev-parse stack-base)" stack-base
# 作ったばかりで未着手
git branch fresh
# PR の head コミットが手元に無く照合できない
branch_with unverifiable v1
add_pr 7 MERGED unverifiable 0123456789abcdef0123456789abcdef01234567
# entire.io の監査用ブランチ(マージ済み PR があるように見せても保護されること)
git switch -q --orphan entire/checkpoints/v1 && commit checkpoint && git switch -q main
git push -q origin entire/checkpoints/v1
add_pr 8 MERGED entire/checkpoints/v1 "$(git rev-parse entire/checkpoints/v1)"
git branch entire/abc1234-e3b0c4 main
git push -q origin main

# --- worktree -------------------------------------------------------------
wt() { # name
  branch_with "$1" "$1-c"
  add_pr "$2" MERGED "$1" "$(git rev-parse "$1")"
  git worktree add -q "$root/wt/$1" "$1"
}
wt wt-merged 10
echo secret >"$root/wt/wt-merged/.env.local"
wt wt-dirty 11
echo change >>"$root/wt/wt-dirty/wt-dirty-c.txt"
wt wt-untracked 12
echo new >"$root/wt/wt-untracked/new.txt"
wt wt-locked 13
git worktree lock "$root/wt/wt-locked"
wt wt-gone 14
rm -rf "$root/wt/wt-gone"
wt wt-busy 15
(cd "$root/wt/wt-busy/" && exec sleep 120) &
busy_pid=$!
git worktree add -q --detach "$root/wt/wt-detached" main

printf '%s\n' "$prs" >"$root/prs.json"
export HOUSEKEEPING_PR_JSON="$root/prs.json"

# --- scan -----------------------------------------------------------------
"$scripts/scan.sh" >"$root/scan.tsv"
[ -n "${VERBOSE:-}" ] && column -t -s $'\t' "$root/scan.tsv"

expect() { # action kind name [reason-substring]
  local got
  got=$(awk -F'\t' -v k="$2" -v n="$3" '$2 == k && $3 == n { print $1 "\t" $6 }' "$root/scan.tsv")
  if [ "${got%%$'\t'*}" = "$1" ] && [[ "$got" == *"${4:-}"* ]]; then
    pass "scan: $2 $3 → $1"
  else
    fail "scan: $2 $3 → 期待 $1${4:+ ($4)} / 実際 ${got:-(出力なし)}"
  fi
}
absent() { # kind name
  if awk -F'\t' -v k="$1" -v n="$2" '$2 == k && $3 == n { f = 1 } END { exit !f }' "$root/scan.tsv"; then
    fail "scan: $1 $2 は出力されないはず"
  else
    pass "scan: $1 $2 は候補に出ない"
  fi
}

expect keep branch main
expect delete branch nopr-ff "コミットした記録"
expect delete branch nopr-merge "merge コミット"
expect delete branch squashed "PR #1"
expect keep branch more-after "追加コミット"
expect keep branch open-pr "オープン"
expect keep branch closed-pr "クローズ"
expect keep branch nopr-unmerged "未取り込み"
expect keep branch stack-base "ベースブランチ"
expect ask branch fresh "未着手"
expect ask branch unverifiable "照合できない"
expect keep branch entire/checkpoints/v1 "保護対象"
expect keep branch entire/abc1234-e3b0c4 "保護対象"
expect delete remote squashed
absent remote entire/checkpoints/v1
expect delete worktree wt-merged ".env.local"
expect delete branch wt-merged "worktree"
expect keep worktree wt-dirty "未コミット"
expect keep branch wt-dirty "使用中"
expect keep worktree wt-untracked "未コミットの変更・未追跡ファイル"
expect keep worktree wt-locked "ロック"
expect prune worktree wt-gone
expect delete branch wt-gone "PR #14"
expect keep worktree wt-busy "プロセス"
expect keep branch wt-busy "使用中"
expect delete worktree "(detached)" "detached"

# --- apply ----------------------------------------------------------------
# 走査後に作業が再開されたブランチ・保護対象を偽装した行は消さないこと
git switch -q nopr-merge && commit resumed && git switch -q main
{
  awk -F'\t' '$1 == "delete" || $1 == "prune"' "$root/scan.tsv"
  printf 'delete\tbranch\tentire/checkpoints/v1\t%s\t\tforged\n' "$(git rev-parse entire/checkpoints/v1)"
} >"$root/approved.tsv"
set +e
"$scripts/apply.sh" <"$root/approved.tsv" >"$root/apply.out"
apply_rc=$?
set -e
[ -n "${VERBOSE:-}" ] && cat "$root/apply.out"
[ "$apply_rc" = 1 ] && pass "apply: 飛ばした行があるので終了コード 1" || fail "apply: 終了コード $apply_rc"

gone_branch() { git rev-parse -q --verify "refs/heads/$1" >/dev/null && fail "apply: branch $1 が残っている" || pass "apply: branch $1 を削除"; }
kept_branch() { git rev-parse -q --verify "refs/heads/$1" >/dev/null && pass "apply: branch $1 は残す" || fail "apply: branch $1 が消えた"; }
for b in nopr-ff squashed wt-merged wt-gone; do gone_branch "$b"; done
for b in nopr-merge entire/checkpoints/v1 entire/abc1234-e3b0c4 fresh unverifiable more-after wt-dirty wt-busy main; do kept_branch "$b"; done
[ ! -e "$root/wt/wt-merged" ] && pass "apply: worktree wt-merged を削除" || fail "apply: worktree wt-merged が残っている"
[ ! -e "$root/wt/wt-detached" ] && pass "apply: detached worktree を削除" || fail "apply: detached worktree が残っている"
for w in wt-dirty wt-untracked wt-locked wt-busy; do
  [ -e "$root/wt/$w" ] && pass "apply: worktree $w は残す" || fail "apply: worktree $w が消えた"
done
git worktree list --porcelain | grep -q 'wt-gone' && fail "apply: wt-gone の管理情報が残っている" || pass "apply: wt-gone を prune"
git -C "$root/origin.git" rev-parse -q --verify refs/heads/squashed >/dev/null &&
  fail "apply: リモートの squashed が残っている" || pass "apply: リモートの squashed を削除"
git -C "$root/origin.git" rev-parse -q --verify refs/heads/entire/checkpoints/v1 >/dev/null &&
  pass "apply: リモートの entire/checkpoints/v1 は残す" || fail "apply: リモートの entire/checkpoints/v1 が消えた"
grep -q 'branch nopr-merge: 先端が走査時から変わっている' "$root/apply.out" &&
  pass "apply: 走査後に更新されたブランチを飛ばす" || fail "apply: 走査後の更新を検知していない"
grep -q 'branch entire/checkpoints/v1: 保護対象' "$root/apply.out" &&
  pass "apply: 偽装した保護対象の行を拒否" || fail "apply: 保護対象を拒否していない"

echo
if [ "$fails" = 0 ]; then echo "全件成功"; else echo "失敗 $fails 件"; exit 1; fi

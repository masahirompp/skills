#!/usr/bin/env bash
# sh-1 に埋め込んだ不具合(B1、B2)を、使い捨てのリポジトリで再現する。
#   answers/repro/sh-1.sh <題材のリポジトリ(差分を当てた状態)>
# 不具合があれば「REPRODUCED」、無ければ「not reproduced」を不具合ごとに出す。
set -uo pipefail
scripts=$(cd "$1/skills/housekeeping/scripts" && pwd)
root=$(cd "$(mktemp -d "${TMPDIR:-/tmp}/repro.XXXXXX")" && pwd -P)
trap 'rm -rf "$root"' EXIT
G() { git -c user.name=t -c user.email=t@example.com "$@"; }

git init -q --bare -b main "$root/origin.git"
git clone -q "$root/origin.git" "$root/repo" 2>/dev/null
cd "$root/repo"
echo a >a.txt && G add -A && G commit -qm init && git push -q -u origin main
git remote set-head origin main >/dev/null

# B2: PR がマージされたあとに、手元で追加のコミットを積んだブランチ
git switch -q -c more-after main
echo b >b.txt && G add -A && G commit -qm b
oid=$(git rev-parse HEAD)
echo c >c.txt && G add -A && G commit -qm c
git switch -q main
printf '[{"number":2,"state":"MERGED","headRefName":"more-after","headRefOid":"%s","baseRefName":"main","headRepositoryOwner":{"login":"test"}}]\n' "$oid" >"$root/prs.json"
got=$(HOUSEKEEPING_PR_JSON="$root/prs.json" "$scripts/scan.sh" 2>/dev/null | awk -F'\t' '$2 == "branch" && $3 == "more-after" { print $1 }')
[ "$got" = keep ] && echo "B2 not reproduced (more-after → keep)" || echo "B2 REPRODUCED: マージ後に追加コミットのあるブランチが ${got:-(出力なし)}"

# B1: ローカルの既定ブランチが無いリポジトリで、作ったばかりのブランチ
git clone -q "$root/origin.git" "$root/no-main" 2>/dev/null
cd "$root/no-main"
git switch -q --detach && git branch fresh && git branch -q -D main
echo '[]' >"$root/none.json"
out=$(HOUSEKEEPING_PR_JSON="$root/none.json" "$scripts/scan.sh" 2>&1)
got=$(printf '%s\n' "$out" | awk -F'\t' '$2 == "branch" && $3 == "fresh" { print $1 "\t" $6 }')
case $got in
  ask*) echo "B1 not reproduced (fresh → ask)" ;;
  *) echo "B1 REPRODUCED: 未着手のブランチが ${got:-(出力なし: $out)}" ;;
esac

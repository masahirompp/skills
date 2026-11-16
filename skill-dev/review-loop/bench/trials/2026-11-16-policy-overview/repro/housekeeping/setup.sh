#!/usr/bin/env bash
# usage: setup.sh <root>
set -euo pipefail
root=$1
git init -q --bare -b main "$root/origin.git"
git clone -q "$root/origin.git" "$root/repo" 2>/dev/null
cd "$root/repo"
git config user.name t; git config user.email t@example.com
c() { echo "$1" >"$1.txt"; git add -A; git commit -qm "$1"; }
printf '.env\n' >.gitignore
c init; git push -q -u origin main; git remote set-head origin main >/dev/null
# A: PR#1 squash マージ済み。ただしオープン PR#2 のベース(スタック)
git switch -q -c stack-base main; c sb1; git push -q origin stack-base; sb=$(git rev-parse HEAD); git switch -q main
git merge -q --squash stack-base >/dev/null && git commit -qm "squash #1"
# B: PR#3 マージ済みのブランチの worktree。bisect 進行中
git switch -q -c wt-bisect main; c wb1; wb=$(git rev-parse HEAD); git switch -q main
git merge -q --squash wt-bisect >/dev/null && git commit -qm "squash #3"
git worktree add -q "$root/wt-bisect" wt-bisect
git -C "$root/wt-bisect" bisect start >/dev/null
# C: PR#4 マージ済みのブランチの worktree。ignored の .env がある
git switch -q -c wt-env main; c we1; we=$(git rev-parse HEAD); git switch -q main
git merge -q --squash wt-env >/dev/null && git commit -qm "squash #4"
git worktree add -q "$root/wt-env" wt-env
echo SECRET=1 >"$root/wt-env/.env"
git push -q origin main
cat >"$root/prs.json" <<J
[{"number":1,"state":"MERGED","headRefName":"stack-base","headRefOid":"$sb","baseRefName":"main","headRepositoryOwner":{"login":"t"}},
 {"number":2,"state":"OPEN","headRefName":"stack-top","headRefOid":"0000000000000000000000000000000000000000","baseRefName":"stack-base","headRepositoryOwner":{"login":"t"}},
 {"number":3,"state":"MERGED","headRefName":"wt-bisect","headRefOid":"$wb","baseRefName":"main","headRepositoryOwner":{"login":"t"}},
 {"number":4,"state":"MERGED","headRefName":"wt-env","headRefOid":"$we","baseRefName":"main","headRepositoryOwner":{"login":"t"}}]
J

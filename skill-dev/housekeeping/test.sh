#!/usr/bin/env bash
# housekeeping の scan.sh / apply.sh を使い捨てリポジトリで検証する。
# origin はローカルの bare リポジトリ、PR 一覧は HOUSEKEEPING_PR_JSON の偽データを使うので GitHub には触れない。
#   skill-dev/housekeeping/test.sh        # 実行して後片付けする
#   KEEP=1 skill-dev/housekeeping/test.sh # 作業ディレクトリを残す
set -euo pipefail

scripts=$(cd "$(dirname "$0")/../../skills/housekeeping/scripts" && pwd)
root=$(cd "$(mktemp -d "${TMPDIR:-/tmp}/hk-test.XXXXXX")" && pwd -P)
busy_pid='' traced_pid='' tracer_pid=''
cleanup() {
  if [ -n "$busy_pid" ]; then kill "$busy_pid" 2>/dev/null; wait "$busy_pid" 2>/dev/null || true; fi
  if [ -n "$traced_pid" ]; then kill -KILL "$traced_pid" 2>/dev/null; fi
  if [ -n "$tracer_pid" ]; then kill "$tracer_pid" 2>/dev/null; wait "$tracer_pid" 2>/dev/null; fi
  if [ -n "${KEEP:-}" ]; then echo "作業ディレクトリ: $root"; else rm -rf "$root"; fi
}
trap cleanup EXIT

fails=0
pass() { printf 'ok    %s\n' "$*"; }
fail() {
  printf 'FAIL  %s\n' "$*"
  fails=$((fails + 1))
}
# unreadable <path>: chmod 000 にしたものが実際に読めないか。root で実行すると読めてしまい、読めないときの確認の前提が崩れる
unreadable() { [ "$(id -u)" != 0 ] && ! [ -r "$1" ]; }

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
expect keep branch wt-dirty "を残すため: 未コミット"
expect keep worktree wt-untracked "未コミットの変更・未追跡ファイル"
expect keep worktree wt-locked "ロック"
expect prune worktree wt-gone
expect delete branch wt-gone "PR #14"
expect keep worktree wt-busy "カレントディレクトリとして使用中(pid"
expect keep branch wt-busy "を残すため: プロセスがカレントディレクトリとして使用中"
expect delete worktree "(detached)" "detached"

# lsof でプロセスを見られないときは、どの worktree も残すこと(使用中かどうかを確かめられない)
mkdir "$root/fake-bin"
printf '#!/bin/sh\nexit 1\n' >"$root/fake-bin/lsof" && chmod +x "$root/fake-bin/lsof"
PATH="$root/fake-bin:$PATH" "$scripts/scan.sh" >"$root/scan-nolsof.tsv" 2>/dev/null || true
got=$(awk -F'\t' '$2 == "worktree" && $3 == "wt-merged" { print $1 "\t" $6 }' "$root/scan-nolsof.tsv")
[ "${got%%$'\t'*}" = keep ] && [[ "$got" == *"確かめられない"* ]] &&
  pass "scan: lsof でプロセスを見られなければ worktree を残す" || fail "scan: lsof が使えないと wt-merged → ${got:-(出力なし)}"
got=$(awk -F'\t' '$2 == "branch" && $3 == "wt-merged" { print $1 "\t" $6 }' "$root/scan-nolsof.tsv")
[ "${got%%$'\t'*}" = keep ] && [[ "$got" == *"を残すため: プロセスが使用中か確かめられない"* ]] &&
  pass "scan: 残した worktree のブランチも「確かめられない」で残す" || fail "scan: 残した worktree のブランチ → ${got:-(出力なし)}"

# --- 失敗の注入 -------------------------------------------------------------
# 対象のコマンドだけを失敗させる包みを PATH の先頭に置く。
# wrap <dir> <command> <引数に含まれたら失敗させる文字列>
wrap() {
  local real
  real=$(command -v "$2")
  mkdir -p "$1"
  printf '#!/bin/sh\ncase " $* " in *"%s"*) echo "injected failure" >&2; exit 128 ;; esac\nexec %s "$@"\n' "$3" "$real" >"$1/$2"
  chmod +x "$1/$2"
}
scan_with() { # <bin-dir> <out-name>: 包みを使って走査する。終了コードを scan_rc に入れる
  set +e
  PATH="$1:$PATH" "$scripts/scan.sh" >"$root/$2.tsv" 2>"$root/$2.err"
  scan_rc=$?
  set -e
}
row() { awk -F'\t' -v k="$2" -v n="$3" '$2 == k && $3 == n { print $1 "\t" $6 }' "$root/$1.tsv"; }

# lsof が特定のプロセスだけを見せない(自分は見える)ときも、使用中の worktree を delete にしないこと
real_lsof=$(command -v lsof)
mkdir "$root/partial-lsof"
printf '#!/bin/sh\n%s "$@" | awk -v drop="p%s" '"'"'/^p/ { skip = ($0 == drop) } !skip'"'"'\n' "$real_lsof" "$busy_pid" >"$root/partial-lsof/lsof"
chmod +x "$root/partial-lsof/lsof"
scan_with "$root/partial-lsof" scan-partial
got=$(row scan-partial worktree wt-busy)
[ "${got%%$'\t'*}" = keep ] && [[ "$got" == *"確かめられない(lsof に出ないプロセス"* ]] &&
  pass "scan: lsof に一部のプロセスしか出なければ worktree を残す" || fail "scan: lsof が一部しか見せないと wt-busy → ${got:-(出力なし)}"

# macOS でトレース中(ps の stat に X)の生きたプロセスも、lsof に出ているかの確認から外さないこと
if [ "$(uname)" = Darwin ] && command -v python3 >/dev/null 2>&1; then
  # PT_TRACE_ME でトレース中にする。macOS では、トレースしている親が終わるまで SIGKILL を送っても消えないので、
  # 親をこのテストとは別の subshell(cwd は worktree の外)にして、子を止めたら親も終わるようにする
  rm -f "$root/traced.pid"
  (
    (cd "$root/wt/wt-merged" && exec python3 -I -c 'import ctypes, time; ctypes.CDLL(None).ptrace(0, 0, None, 0); time.sleep(120)') &
    echo $! >"$root/traced.pid"
    wait
  ) &
  tracer_pid=$!
  traced_pid='' traced_stat=''
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    [ -n "$traced_pid" ] || traced_pid=$(cat "$root/traced.pid" 2>/dev/null) || true
    [ -n "$traced_pid" ] && traced_stat=$(ps -o stat= -p "$traced_pid" 2>/dev/null) || true
    [[ $traced_stat == *X* ]] && break
    sleep 0.2
  done
  mkdir -p "$root/traced-lsof"
  printf '#!/bin/sh\n%s "$@" | awk -v drop="p%s" '"'"'/^p/ { skip = ($0 == drop) } !skip'"'"'\n' "$real_lsof" "$traced_pid" >"$root/traced-lsof/lsof"
  chmod +x "$root/traced-lsof/lsof"
  scan_with "$root/traced-lsof" scan-traced
  if [ -n "$traced_pid" ]; then kill -KILL "$traced_pid" 2>/dev/null || true; else kill "$tracer_pid" 2>/dev/null || true; fi
  wait "$tracer_pid" 2>/dev/null || true
  traced_pid='' tracer_pid=
  got=$(row scan-traced worktree wt-merged)
  if [[ $traced_stat != *X* ]]; then
    pass "scan: (トレース中のプロセスを作れないので、stat X の確認は飛ばす)"
  else
    [ "${got%%$'\t'*}" = keep ] && [[ "$got" == *"確かめられない(lsof に出ないプロセス"* ]] &&
      pass "scan: トレース中のプロセスが lsof に出なければ worktree を残す" || fail "scan: トレース中のプロセスが lsof に出ないと wt-merged → ${got:-(出力なし)}"
  fi
else
  pass "scan: (macOS でないか python3 が無いので、トレース中のプロセスの確認は飛ばす)"
fi

# オープン PR のベースの一覧を読めなければ止まること(読めないと、スタックした PR のベースが delete になる)
wrap "$root/fail-jq" jq baseRefName
scan_with "$root/fail-jq" scan-jq
[ "$scan_rc" != 0 ] && grep -q 'ベースブランチを読めない' "$root/scan-jq.err" && ! grep -q '^delete' "$root/scan-jq.tsv" &&
  pass "scan: オープン PR のベースを読めなければ止まる" || fail "scan: オープン PR のベースを読めないのに止まらない(rc=$scan_rc)"

# 進行中の操作を確かめられなければ worktree を残すこと
wrap "$root/fail-gitpath" git --git-path
scan_with "$root/fail-gitpath" scan-gitpath
got=$(row scan-gitpath worktree wt-merged)
[ "${got%%$'\t'*}" = keep ] && [[ "$got" == *"進行中の操作"*"確かめられない"* ]] &&
  pass "scan: 進行中の操作を確かめられなければ worktree を残す" || fail "scan: git-path が失敗すると wt-merged → ${got:-(出力なし)}"
got=$(row scan-gitpath branch wt-merged)
[ "${got%%$'\t'*}" = keep ] && pass "scan: そのブランチも残す" || fail "scan: git-path が失敗すると branch wt-merged → ${got:-(出力なし)}"

# --path-format を知らない git(2.31 未満。知らないオプションを出力にそのまま返す)でも、進行中の操作を確かめずに進まないこと。
# 今の git が知らないオプションに置き換えて、同じ出力(2行)を作る
mkdir "$root/old-git"
printf '#!/usr/bin/env bash\nargs=()\nfor a in "$@"; do [ "$a" = --path-format=absolute ] && a=--hk-unknown-option=absolute; args+=("$a"); done\nexec %s "${args[@]}"\n' "$(command -v git)" >"$root/old-git/git"
chmod +x "$root/old-git/git"
scan_with "$root/old-git" scan-oldgit
got=$(row scan-oldgit worktree wt-merged)
[ "${got%%$'\t'*}" = keep ] && [[ "$got" == *"進行中の操作"*"確かめられない"* ]] &&
  pass "scan: --git-path の出力が1行の絶対パスでなければ worktree を残す" || fail "scan: --path-format を知らない git で wt-merged → ${got:-(出力なし)}"

# git status --ignored を読めなければ、ignored ファイルの警告を黙って落とさずに worktree を残すこと
wrap "$root/fail-ignored" git --ignored
scan_with "$root/fail-ignored" scan-ignored
got=$(row scan-ignored worktree wt-merged)
[ "${got%%$'\t'*}" = keep ] && [[ $got == *確かめられない* ]] &&
  pass "scan: git status --ignored を読めなければ worktree を「確かめられない」で残す" || fail "scan: status --ignored が失敗すると wt-merged → ${got:-(出力なし)}"
got=$(row scan-ignored branch wt-merged)
[ "${got%%$'\t'*}" = keep ] && [[ $got == *"を残すため: "*確かめられない* ]] &&
  pass "scan: そのブランチも「確かめられない」で残す" || fail "scan: status --ignored が失敗すると branch wt-merged → ${got:-(出力なし)}"

# 未コミットの変更を数えられないとき、first-parent 履歴や PR の状態を読めないときも、理由に「確かめられない」を出すこと
wrap "$root/fail-dirty" awk '!/^!! /'
scan_with "$root/fail-dirty" scan-dirty
got=$(row scan-dirty worktree wt-merged)
[ "${got%%$'\t'*}" = keep ] && [[ $got == *確かめられない* ]] &&
  pass "scan: git status の出力を読めなければ「確かめられない」で残す" || fail "scan: git status の出力を読めないと wt-merged → ${got:-(出力なし)}"
wrap "$root/fail-fp" grep '/first-parent'
scan_with "$root/fail-fp" scan-fp
got=$(row scan-fp branch nopr-merge)
[ "${got%%$'\t'*}" = keep ] && [[ $got == *確かめられない* ]] &&
  pass "scan: first-parent 履歴を読めなければ「確かめられない」で残す" || fail "scan: first-parent 履歴を読めないと nopr-merge → ${got:-(出力なし)}"
wrap "$root/fail-prinfo" jq 'max_by'
scan_with "$root/fail-prinfo" scan-prinfo
got=$(row scan-prinfo branch squashed)
[ "${got%%$'\t'*}" = keep ] && [[ $got == *確かめられない* ]] &&
  pass "scan: PR の状態を読めなければ「確かめられない」で残す" || fail "scan: PR の状態を読めないと squashed → ${got:-(出力なし)}"

# worktree 一覧を読めなければ止まること(読めないと、worktree で使用中のブランチが delete 候補になる)
wrap "$root/fail-wtlist" git 'worktree list'
scan_with "$root/fail-wtlist" scan-wtlist
[ "$scan_rc" != 0 ] && grep -q 'worktree list を読めない' "$root/scan-wtlist.err" && ! grep -q '^delete' "$root/scan-wtlist.tsv" &&
  pass "scan: worktree 一覧を読めなければ止まる" || fail "scan: worktree 一覧を読めないのに止まらない(rc=$scan_rc)"

# ブランチの一覧を読めなければ止まること(読めないと、ブランチの行が欠けたまま正常に終わる)
for refs in refs/heads/ refs/remotes/origin/; do
  wrap "$root/fail-refs-${refs//\//-}" git " $refs "
  scan_with "$root/fail-refs-${refs//\//-}" scan-refs
  [ "$scan_rc" != 0 ] && grep -q 'ブランチの一覧を読めない' "$root/scan-refs.err" &&
    pass "scan: $refs の一覧を読めなければ止まる" || fail "scan: $refs の一覧を読めないのに止まらない(rc=$scan_rc)"
done

# 存在するのに読めない worktree(git は prunable と出す)を、prune にも、そのブランチを delete にもしないこと
chmod 000 "$root/wt/wt-dirty"
if unreadable "$root/wt/wt-dirty"; then
  scan_with /nonexistent scan-noperm-wt
  chmod 755 "$root/wt/wt-dirty"
  got=$(row scan-noperm-wt worktree wt-dirty)
  [ "${got%%$'\t'*}" = keep ] && [[ "$got" == *"ディレクトリが無いと確かめられない"* ]] &&
    pass "scan: 読めない worktree は prune にしない" || fail "scan: 読めない worktree wt-dirty → ${got:-(出力なし)}"
  got=$(row scan-noperm-wt branch wt-dirty)
  [ "${got%%$'\t'*}" = keep ] && pass "scan: 読めない worktree のブランチを残す" || fail "scan: 読めない worktree のブランチ wt-dirty → ${got:-(出力なし)}"
else
  chmod 755 "$root/wt/wt-dirty"
  pass "scan: (chmod 000 でも読めてしまう(root など)ので、読めない worktree の確認は飛ばす)"
fi

# git リポジトリを読めないときは、git の出力を添えて止まること
set +e
(cd "$root" && GIT_CEILING_DIRECTORIES="$root" "$scripts/scan.sh" >/dev/null 2>"$root/scan-norepo.err")
norepo_rc=$?
set -e
[ "$norepo_rc" != 0 ] && grep -q 'git リポジトリとして読めない: .*not a git repository' "$root/scan-norepo.err" &&
  pass "scan: リポジトリの外では git の出力を添えて止まる" || fail "scan: リポジトリの外での止まり方が違う: $(cat "$root/scan-norepo.err")"

# 一時ディレクトリを作れないときは、空のパスのまま進まずに、fetch より前に止まること。
# fetch に進めば、存在しないリモートへの fetch で warn が出る。
# テンプレートを付けない mktemp は macOS では TMPDIR を見ないので、TMPDIR に従うことの確認にもなる。
set +e
TMPDIR="$root/no-such-dir" HOUSEKEEPING_REMOTE=no-such-remote "$scripts/scan.sh" >"$root/scan-notmp.out" 2>"$root/scan-notmp.err"
notmp_rc=$?
set -e
if [ "$notmp_rc" != 0 ] && [ ! -s "$root/scan-notmp.out" ] && grep -q '一時ディレクトリを作れない' "$root/scan-notmp.err" &&
  ! grep -q fetch "$root/scan-notmp.err"; then
  pass "scan: 一時ディレクトリを作れなければ fetch より前に止まる"
else
  fail "scan: 一時ディレクトリを作れないのに止まらない(rc=$notmp_rc): $(cat "$root/scan-notmp.err")"
fi

in_lib() { bash -c '. "$1/lib.sh" && shift && "$@"' _ "$scripts" "$@"; }
# 一時ディレクトリは TMPDIR の下に作ること(末尾の / があってもよい)
mkdir "$root/tmpdir"
made=$(TMPDIR="$root/tmpdir/" in_lib hk_mktemp_dir) || true
[ "${made%/*}" = "$root/tmpdir" ] && pass "lib: TMPDIR の下に作る" || fail "lib: TMPDIR を使わない($made)"
rm -rf "${root:?}/tmpdir"/*
# 終了時に消すこと(TMPDIR に従うことは上の「止まる」テストで確かめている)
if TMPDIR="$root/tmpdir" "$scripts/scan.sh" >/dev/null && [ -z "$(ls -A "$root/tmpdir")" ]; then
  pass "scan: 一時ディレクトリを片付ける"
else
  fail "scan: 失敗した、または一時ディレクトリが残っている"
fi

# 削除の可否を決めるスクリプトに、一時ファイルを使う書き方が無いこと(理由は lib.sh の冒頭)。
# 一時ファイルを作れない環境は作りにくいので、書き方で確かめる。mktemp は hk_mktemp_dir の中だけで使う。
temp_usage() { # file pattern: コメント行を除いて、pattern に当たる行を出す
  grep -nE "$2" "$1" | grep -vE '^[0-9]+:[[:space:]]*#'
}
# lib.sh の mktemp は、hk_mktemp_dir の本体(行頭の "}" まで)の中だけ
mktemp_outside() {
  awk '/^hk_mktemp_dir\(\) \{/ { inside = 1; next } inside && /^}/ { inside = 0; next }
    !inside && /mktemp/ && !/^[[:space:]]*#/ { print FILENAME ":" FNR ": " $0 }' "$scripts/lib.sh"
}
if temp_usage "$scripts/apply.sh" '<<|mktemp' || temp_usage "$scripts/lib.sh" '<<' || temp_usage "$scripts/scan.sh" '<<' ||
  temp_usage "$scripts/scan.sh" 'mktemp' | grep -v 'hk_mktemp_dir' || [ -n "$(mktemp_outside)" ]; then
  mktemp_outside
  fail "scan/apply/lib: 一時ファイルを使う書き方がある(上の行。lib.sh の mktemp は hk_mktemp_dir の中だけ)"
else
  pass "scan/apply/lib: ヒアドキュメントを使わず、mktemp は hk_mktemp_dir だけ"
fi

# 判定の結果が1行の「既知の action<TAB>理由」でなければ、残す側に倒すこと
parsed() { bash -c '. "$1/lib.sh"; hk_parse_action "$2"; printf "%s/%s" "$action" "$reason"' _ "$scripts" "$1"; }
for input in '' 'delete' $'delete\tx\ndelete\ty' $'remove\tx'; do
  r=$(parsed "$input") || true
  [ "${r%%/*}" = keep ] && [[ $r == *確かめられない* ]] && pass "lib: 判定 $(printf %q "$input") は keep に倒す" || fail "lib: 判定 $(printf %q "$input") → $r"
done
r=$(parsed $'delete\tx') || true
[ "$r" = delete/x ] && pass "lib: 判定を action と reason に分ける" || fail "lib: 判定の分け方が違う($r)"

# 保護パターンは、set -f が外れていてもファイル名に展開されないこと
mkdir -p "$root/globcwd/release" && : >"$root/globcwd/release/notes.md"
if (cd "$root/globcwd" && HOUSEKEEPING_PROTECT='release/*' bash -c '. "$1/lib.sh"; set +f; hk_load_protect main && hk_is_protected release/1.0' _ "$scripts"); then
  pass "lib: set +f でも保護パターンを展開しない"
else
  fail "lib: set +f で保護パターンが展開された"
fi

# ローカルの既定ブランチが無くても、first-parent の履歴を origin から読むこと
# (読めないと、作ったばかりのブランチが「merge コミットで取り込み済み」の delete になる)
git clone -q "$root/origin.git" "$root/no-local-main" 2>/dev/null
(
  cd "$root/no-local-main"
  git switch -q --detach && git branch fresh2 && git branch -q -D main
  "$scripts/scan.sh" >"$root/scan-nomain.tsv" 2>/dev/null
) || true
got=$(awk -F'\t' '$2 == "branch" && $3 == "fresh2" { print $1 }' "$root/scan-nomain.tsv")
[ "$got" = ask ] && pass "scan: ローカルの既定ブランチが無くても未着手のブランチは ask" || fail "scan: ローカルの既定ブランチが無いと fresh2 → ${got:-(出力なし)}"

# 読めない PR 一覧では止まること(jq が空を返すと、オープン PR の保護が外れる)
echo 'not json' >"$root/bad-prs.json"
set +e
HOUSEKEEPING_PR_JSON="$root/bad-prs.json" "$scripts/scan.sh" >"$root/scan-bad.out" 2>"$root/scan-bad.err"
bad_rc=$?
set -e
[ "$bad_rc" != 0 ] && grep -q 'JSON の配列として読めない' "$root/scan-bad.err" && ! grep -q '^delete' "$root/scan-bad.out" &&
  pass "scan: 読めない PR 一覧では止まる" || fail "scan: 読めない PR 一覧で止まらない(rc=$bad_rc)"
# PR 一覧の件数が上限に達していれば止まること(gh は上限で黙って切るので、古いオープン PR のベースが delete になりうる)
pr_total=$(jq length "$root/prs.json")
set +e
HOUSEKEEPING_PR_LIMIT=$pr_total "$scripts/scan.sh" >"$root/scan-limit.out" 2>"$root/scan-limit.err"
limit_rc=$?
HOUSEKEEPING_PR_LIMIT=$((pr_total + 1)) "$scripts/scan.sh" >/dev/null 2>"$root/scan-underlimit.err"
underlimit_rc=$?
set -e
[ "$limit_rc" != 0 ] && grep -q '上限(.*件)に達して' "$root/scan-limit.err" && ! grep -q '^delete' "$root/scan-limit.out" &&
  pass "scan: PR 一覧が上限に達していれば止まる" || fail "scan: PR 一覧が上限に達しているのに止まらない(rc=$limit_rc)"
[ "$underlimit_rc" = 0 ] && pass "scan: PR 一覧が上限未満なら止まらない" || fail "scan: PR 一覧が上限未満なのに止まった: $(cat "$root/scan-underlimit.err")"

# 保護パターン: 空白区切りの HOUSEKEEPING_PROTECT と git config の両方が効くこと
protected() { HOUSEKEEPING_PROTECT='release/* sandbox' bash -c '. "$1/lib.sh" && hk_load_protect main && hk_is_protected "$2"' _ "$scripts" "$1"; }
git config --add housekeeping.protect 'keep me/*'
for b in release/1.0 sandbox 'keep me/x' main entire/x; do
  protected "$b" && pass "lib: $b は保護対象" || fail "lib: $b が保護されない"
done
for b in releases feature/sandbox; do
  protected "$b" && fail "lib: $b が保護対象になった" || pass "lib: $b は保護対象でない"
done
git config --unset-all housekeeping.protect
# 保護パターンを読み込まずに照合したら、保護対象とみなすこと(呼び出し側の誤りで保護が外れない)
in_lib hk_is_protected feature/x && pass "lib: 保護パターンを読み込む前は保護対象とみなす" || fail "lib: 読み込む前に保護対象でないと答えた"
# git config を読めない(キーが無いのとは別の失敗)ときは、scan も apply も止まること。
#   壊れた設定: --get-all が rc=128 を返す
#   権限で読めない設定: --get-all はキーが無いときと同じ rc=1 を返す。--global の警告で見分ける
printf '[broken\n' >"$root/bad.gitconfig"
printf '[housekeeping]\n\tprotect = keep-me\n' >"$root/noperm.gitconfig" && chmod 000 "$root/noperm.gitconfig"
for cfg in bad noperm; do
  if [ "$cfg" = noperm ] && ! unreadable "$root/noperm.gitconfig"; then
    pass "scan/apply: (chmod 000 でも読めてしまう(root など)ので、権限で読めない設定の確認は飛ばす)"
    continue
  fi
  set +e
  GIT_CONFIG_GLOBAL="$root/$cfg.gitconfig" "$scripts/scan.sh" >"$root/scan-$cfg-cfg.out" 2>"$root/scan-$cfg-cfg.err"
  rc=$?
  printf 'delete\tbranch\tnopr-ff\t%s\t\tx\n' "$(git rev-parse nopr-ff)" |
    GIT_CONFIG_GLOBAL="$root/$cfg.gitconfig" "$scripts/apply.sh" >"$root/apply-$cfg-cfg.out" 2>"$root/apply-$cfg-cfg.err"
  arc=$?
  set -e
  [ "$rc" != 0 ] && grep -qE 'git config.*を読めない|bad config' "$root/scan-$cfg-cfg.err" && ! grep -q '^delete' "$root/scan-$cfg-cfg.out" &&
    pass "scan: git config を読めなければ止まる($cfg)" || fail "scan: git config を読めないのに止まらない($cfg, rc=$rc)"
  [ "$arc" != 0 ] && grep -qE 'git config.*を読めない|bad config' "$root/apply-$cfg-cfg.err" && git rev-parse -q --verify refs/heads/nopr-ff >/dev/null &&
    pass "apply: git config を読めなければ止まる($cfg)" || fail "apply: git config を読めないのに止まらない($cfg, rc=$arc)"
done
chmod 600 "$root/noperm.gitconfig"
# ~/.gitconfig があると、権限で読めない XDG の設定に git は警告を出さない(--global を明示しても)。それでも止まること
mkdir -p "$root/xdg-home" "$root/xdg/git"
printf '[user]\n\tname = test\n' >"$root/xdg-home/.gitconfig"
printf '[housekeeping]\n\tprotect = nopr-ff\n' >"$root/xdg/git/config" && chmod 000 "$root/xdg/git/config"
if unreadable "$root/xdg/git/config"; then
  set +e
  env -u GIT_CONFIG_GLOBAL HOME="$root/xdg-home" XDG_CONFIG_HOME="$root/xdg" "$scripts/scan.sh" >"$root/scan-xdg-cfg.out" 2>"$root/scan-xdg-cfg.err"
  rc=$?
  printf 'delete\tbranch\tnopr-ff\t%s\t\tx\n' "$(git rev-parse nopr-ff)" |
    env -u GIT_CONFIG_GLOBAL HOME="$root/xdg-home" XDG_CONFIG_HOME="$root/xdg" "$scripts/apply.sh" >"$root/apply-xdg-cfg.out" 2>"$root/apply-xdg-cfg.err"
  arc=$?
  set -e
  [ "$rc" != 0 ] && grep -q 'git config.*/xdg/git/config を読めない' "$root/scan-xdg-cfg.err" && ! grep -q '^delete' "$root/scan-xdg-cfg.out" &&
    pass "scan: 読めない XDG の設定があれば止まる" || fail "scan: 読めない XDG の設定があるのに止まらない(rc=$rc)"
  [ "$arc" != 0 ] && grep -q 'git config.*/xdg/git/config を読めない' "$root/apply-xdg-cfg.err" && git rev-parse -q --verify refs/heads/nopr-ff >/dev/null &&
    pass "apply: 読めない XDG の設定があれば止まる" || fail "apply: 読めない XDG の設定があるのに止まらない(rc=$arc)"
else
  pass "scan/apply: (chmod 000 でも読めてしまう(root など)ので、読めない XDG の設定の確認は飛ばす)"
fi
chmod 600 "$root/xdg/git/config"

# --- apply ----------------------------------------------------------------
# プロセスを確かめられなければ、worktree の行は消さずに「確かめられない」で飛ばすこと。
# 走査の後に作業を始めたプロセスが lsof に出ない場合を、wt-merged を見せない lsof で作る
(cd "$root/wt/wt-merged" && exec sleep 120) &
merged_pid=$!
printf '#!/bin/sh\n%s "$@" | awk -v drop="p%s" '"'"'/^p/ { skip = ($0 == drop) } !skip'"'"'\n' "$real_lsof" "$merged_pid" >"$root/partial-lsof/lsof"
set +e
awk -F'\t' '$2 == "worktree" && $3 == "wt-merged"' "$root/scan.tsv" | PATH="$root/partial-lsof:$PATH" "$scripts/apply.sh" >"$root/apply-partial.out"
set -e
grep -q 'worktree .*wt-merged: プロセスが使用中か確かめられない(lsof に出ないプロセス' "$root/apply-partial.out" && [ -e "$root/wt/wt-merged" ] &&
  pass "apply: プロセスを確かめられなければ worktree を消さない" || fail "apply: lsof が一部しか見せないのに worktree を処理した: $(cat "$root/apply-partial.out")"
# 使用中なら、確かめられないのとは別の理由で飛ばすこと
set +e
awk -F'\t' '$2 == "worktree" && $3 == "wt-merged"' "$root/scan.tsv" | "$scripts/apply.sh" >"$root/apply-busy.out"
set -e
grep -q "worktree .*wt-merged: プロセスがカレントディレクトリとして使用中(pid $merged_pid" "$root/apply-busy.out" && [ -e "$root/wt/wt-merged" ] &&
  pass "apply: 使用中の worktree は「使用中」として飛ばす" || fail "apply: 使用中の worktree の扱いが違う: $(cat "$root/apply-busy.out")"
kill "$merged_pid" 2>/dev/null; wait "$merged_pid" 2>/dev/null || true

# prune の行を受けても、存在するのに読めないだけの worktree(prunable に含まれる)があれば、git worktree prune をしないこと
# (prune は承認した行に関係なく、prunable なものを全て消す)
chmod 000 "$root/wt/wt-dirty"
if unreadable "$root/wt/wt-dirty"; then
  set +e
  awk -F'\t' '$1 == "prune"' "$root/scan.tsv" | "$scripts/apply.sh" >"$root/apply-noperm.out"
  set -e
  noperm_listed=$(git worktree list --porcelain | grep -c '/wt/wt-dirty$' || true)
  chmod 755 "$root/wt/wt-dirty"
  [ "$noperm_listed" = 1 ] && grep -q 'worktree prune: .*wt-dirty は prunable だが、ディレクトリが無いと確かめられない' "$root/apply-noperm.out" &&
    pass "apply: 読めない worktree があれば prune しない" || fail "apply: 読めない worktree の管理情報を prune した: $(cat "$root/apply-noperm.out")"
else
  chmod 755 "$root/wt/wt-dirty"
  pass "apply: (chmod 000 でも読めてしまう(root など)ので、読めない worktree の確認は飛ばす)"
fi

# 判定の関数が出さない行(branch の prune、未知の action)は消さずに知らせること
set +e
printf 'prune\tbranch\tnopr-ff\t%s\t\tx\nremove\tbranch\tnopr-ff\t%s\t\tx\n' "$(git rev-parse nopr-ff)" "$(git rev-parse nopr-ff)" |
  "$scripts/apply.sh" >"$root/apply-unknown.out"
unknown_rc=$?
set -e
[ "$unknown_rc" = 1 ] && [ "$(grep -c '未知の行' "$root/apply-unknown.out")" = 2 ] && git rev-parse -q --verify refs/heads/nopr-ff >/dev/null &&
  pass "apply: 未知の行は消さずに知らせる" || fail "apply: 未知の行の扱いが違う(rc=$unknown_rc): $(cat "$root/apply-unknown.out")"

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

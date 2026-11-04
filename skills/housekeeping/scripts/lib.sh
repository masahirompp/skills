# scan.sh と apply.sh の共通部分。source して使う。
#
# 環境変数:
#   HOUSEKEEPING_REMOTE   対象リモート(既定 origin)
#   HOUSEKEEPING_PROTECT  追加の保護パターン(空白区切りの glob。例 "release/* sandbox")
# git config:
#   housekeeping.protect  追加の保護パターン(複数指定可。git config --add で足す)
#
# 削除の可否を決める判定(lib.sh、scan.sh と apply.sh の判定の経路)は、ヒアドキュメントとヒアストリングを使わない。
# bash はこれらを一時ファイルで渡すことがあり、作れないと入力が空になって「保護対象でない」「使用中でない」と
# 判定してしまう。test.sh が書き方を確かめている。プロセス置換(< <(...))は /dev/fd を使うので対象にしない。
# 判定の結果が空になったときは、残す側に倒す(hk_parse_action)。

set -f # 保護パターンの glob をファイル名に展開させない

hk_remote=${HOUSEKEEPING_REMOTE:-origin}

# hk_mktemp_dir: 一時ディレクトリを作り、そのパスを返す。作れなければ理由を stderr に出して失敗を返す。
# $(...) の中では exit しても呼び出し元は止まらないので、呼び出し側は必ず `|| exit 1` で止まる。
# macOS の mktemp はテンプレートを付けないと TMPDIR を見ずに /var/folders/... を使う。
# サンドボックスではそこに書けないことがあるので、場所をテンプレートで明示する。
hk_mktemp_dir() {
  local base=${TMPDIR:-/tmp} d
  if d=$(mktemp -d "${base%/}/housekeeping.XXXXXX") && [ -n "$d" ] && [ -d "$d" ]; then
    printf '%s\n' "$d"
    return 0
  fi
  echo "error: 一時ディレクトリを作れない($base)。TMPDIR=<書き込める場所> で実行し直すか、サンドボックスの外で実行する" >&2
  return 1
}

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
  local p IFS=$' \t\n'
  set -f # 呼び出し元の設定に頼らず、HOUSEKEEPING_PROTECT の glob を展開させない($(...) の中で呼ぶので外には漏れない)
  printf '%s\n' 'entire/*' main master develop gh-pages "$1"
  git config --get-all housekeeping.protect 2>/dev/null
  for p in ${HOUSEKEEPING_PROTECT:-}; do printf '%s\n' "$p"; done
}

# hk_is_protected <branch> <default-branch>
# パターンは1行ずつ切り出して case で照合する。単語分割を使わないので、glob がファイル名に展開されることもない。
hk_is_protected() {
  local p rest
  # 一覧を取れなければ(組み込みのパターンは必ず出るので、空は取得の失敗)保護対象とみなす
  rest=$(hk_protect_patterns "$2") && [ -n "$rest" ] || return 0
  while [ -n "$rest" ]; do
    p=${rest%%$'\n'*}
    case $rest in *$'\n'*) rest=${rest#*$'\n'} ;; *) rest='' ;; esac
    [ -n "$p" ] || continue
    case "$1" in $p) return 0 ;; esac
  done
  return 1
}

# hk_parse_action <"action<TAB>reason">: 判定の結果をグローバル変数 action と reason に分ける。
# 1行の「既知の action<TAB>理由」でなければ(空、タブが無い、複数行、未知の action)、残す側に倒す
hk_parse_action() {
  case $1 in
    *$'\n'* | '') action='' ;;
    *$'\t'*) action=${1%%$'\t'*} reason=${1#*$'\t'} ;;
    *) action='' ;;
  esac
  case $action in
    delete | ask | keep | prune) ;;
    *) action=keep reason="判定できなかった" ;;
  esac
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
  printf '%s\n' "$2" | awk -F'\t' -v p="$1" -v self="$$" '
    !found && $1 != self && ($3 == p || index($3, p "/") == 1) { print $1 " " $2; found = 1 }'
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

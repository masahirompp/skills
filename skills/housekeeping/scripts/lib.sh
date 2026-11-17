# scan.sh と apply.sh の共通部分。source して使う。
#
# 環境変数:
#   HOUSEKEEPING_REMOTE   対象リモート(既定 origin)
#   HOUSEKEEPING_PROTECT  追加の保護パターン(空白区切りの glob。例 "release/* sandbox")
# git config:
#   housekeeping.protect  追加の保護パターン(複数指定可。git config --add で足す)
#
# 判定の入力の扱い:
#   - 判定の入力(PR 一覧、既定ブランチの履歴、保護パターン、worktree 一覧、ブランチの一覧)は、scan.sh・apply.sh の冒頭で一度だけ集める。
#     どれかを読めなければ、何を読めなかったかを error に出して止まる
#   - プロセスの一覧(hk_process_cwds)と worktree ごとの状態は、読めなければ止まらずに「確かめられない」として残す。
#     「使用中」とは別の理由として出す
#   - 判定の結果が空になったときは、残す側に倒す(hk_parse_action)
#
# 削除の可否を決める判定(lib.sh、scan.sh と apply.sh の判定の経路)は、ヒアドキュメントとヒアストリングを使わない。
# bash はこれらを一時ファイルで渡すことがあり、作れないと入力が空になって「保護対象でない」「使用中でない」と
# 判定してしまう。skill-dev/housekeeping/test.sh(リポジトリ側)が書き方を確かめている。プロセス置換(< <(...))は /dev/fd を使うので対象にしない。

set -f # 保護パターンの glob をファイル名に展開させない

hk_remote=${HOUSEKEEPING_REMOTE:-origin}

# hk_mktemp_dir: 一時ディレクトリを作り、そのパスを返す。作れなければ理由を stderr に出して失敗を返す。
# $(...) の中では exit しても呼び出し元は止まらないので、呼び出し側は必ず `|| exit 1` で止まる。
# macOS の mktemp はテンプレートを付けないと TMPDIR を見ずに /var/folders/... を使う。
# サンドボックスではそこに書けないことがあるので、場所をテンプレートで明示する。
# TMPDIR が設定されていればそこだけを使う。未設定なら /tmp、次に mktemp の既定の場所を試す。
hk_mktemp_dir() {
  local d=''
  if [ -n "${TMPDIR:-}" ]; then
    d=$(mktemp -d "${TMPDIR%/}/housekeeping.XXXXXX" 2>/dev/null)
  else
    d=$(mktemp -d /tmp/housekeeping.XXXXXX 2>/dev/null) || d=$(mktemp -d -t housekeeping 2>/dev/null)
  fi
  if [ -n "$d" ] && [ -d "$d" ]; then
    printf '%s\n' "$d"
    return 0
  fi
  echo "error: 一時ディレクトリを作れない(${TMPDIR:-/tmp と mktemp の既定の場所})。TMPDIR=<書き込める場所> で実行し直すか、サンドボックスの外で実行する" >&2
  return 1
}

# hk_check_repo: git リポジトリとして読めるかを確かめる。読めなければ、git の出力を添えて error を出す
# (リポジトリの外で実行したのか、権限などで読めないのかを、利用者が見分けられるように)
hk_check_repo() {
  local err
  err=$(git rev-parse --git-dir 2>&1 >/dev/null) && return 0
  echo "error: git リポジトリとして読めない: ${err:-(git の出力なし)}" >&2
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
#
# hk_load_protect <default-branch>: 保護パターンを一度だけ読み、改行区切りでグローバル変数 hk_protect に入れる。
# 設定を読めなければ、何を読めなかったかを stderr に出して失敗を返す(呼び出し側は止まる)。
#   - git config --get-all の終了コード 1 は「キーが無い」。それ以外は失敗
#   - 権限で読めない ~/.gitconfig は、--get-all ではキーが無いときと同じ rc=1 になり、見分けられない。
#     --global / --system を明示すると警告を stderr に出すので、それを失敗として扱う
hk_load_protect() {
  local p cfg rc err scope IFS=$' \t\n'
  set -f # 呼び出し元の設定に頼らず、HOUSEKEEPING_PROTECT の glob を展開させない
  cfg=$(git config --get-all housekeeping.protect 2>&1)
  rc=$?
  if [ "$rc" -gt 1 ]; then
    echo "error: git config を読めない(保護パターンを確かめられない): $cfg" >&2
    return 1
  fi
  [ "$rc" = 0 ] || cfg=''
  for scope in --system --global; do
    err=$(git config "$scope" --get-all housekeeping.protect 2>&1 >/dev/null)
    if [ -n "$err" ]; then
      echo "error: git config $scope を読めない(保護パターンを確かめられない): $err" >&2
      return 1
    fi
  done
  hk_protect=$(
    printf '%s\n' 'entire/*' main master develop gh-pages "$1"
    [ -z "$cfg" ] || printf '%s\n' "$cfg"
    for p in ${HOUSEKEEPING_PROTECT:-}; do printf '%s\n' "$p"; done
  )
}

# hk_is_protected <branch>: hk_load_protect で読んだパターンと照合する。
# パターンは1行ずつ切り出して case で照合する。単語分割を使わないので、glob がファイル名に展開されることもない。
hk_is_protected() {
  local p rest=${hk_protect:-}
  # 読み込んでいなければ(呼び出し側の誤り)、保護対象とみなす
  [ -n "$rest" ] || return 0
  while [ -n "$rest" ]; do
    p=${rest%%$'\n'*}
    case $rest in *$'\n'*) rest=${rest#*$'\n'} ;; *) rest='' ;; esac
    [ -n "$p" ] || continue
    case "$1" in $p) return 0 ;; esac
  done
  return 1
}

# hk_unsure <何を確かめるか> [詳細]: 読めずに残すときの理由を "<何を確かめるか>確かめられない(<詳細>)" の形で返す。
# 読めずに残す理由はすべてこれで作り、「確かめられない」の語で、状態が分かって残したもの(使用中・作業中)と
# 見分けられるようにする(SKILL.md の手順2は、この語で分けて伝える)
hk_unsure() { printf '%s確かめられない%s' "$1" "${2:+($2)}"; }

# hk_parse_action <"action<TAB>reason">: 判定の結果をグローバル変数 action と reason に分ける。
# 1行の「既知の action<TAB>理由」でなければ(空、タブが無い、複数行、未知の action)、残す側に倒す
hk_parse_action() {
  case $1 in
    *$'\n'* | '') action='' ;;
    *$'\t'*) action=${1%%$'\t'*} reason=${1#*$'\t'} ;;
    *) action='' ;;
  esac
  case $action in
    delete | ask | keep) ;;
    *) action=keep reason=$(hk_unsure "削除してよいか" "判定の結果を読めない") ;;
  esac
}

# hk_process_cwds: 実行中プロセスのカレントディレクトリ一覧("pid<TAB>command<TAB>cwd")を返す。
# 一覧がそろっていると確かめられなければ、理由を1行返して失敗を返す(呼び出し側は「使用中か確かめられない」として残す)。
#
# lsof の結果に自分($$)が出るだけでは「ほかも見える」の根拠にならない。sandbox-exec で他プロセスの
# process-info を禁じると、lsof は自分の系統のプロセスだけを返す。そこで、ps で見える自分のユーザーのプロセス
# (終了中・ゾンビを除く)が、すべて lsof に cwd 付きで出ているかを確かめる。lsof の前後で ps を取り、両方に出たものだけを
# 比べる(その間に始まった・終わったプロセスで誤判定しない)。
#   - cwd が分かったとみなすのは、lsof の n 行が "/" で始まり、末尾に " (...)" の付記が無いときだけ。
#     Linux の lsof は cwd を読めないプロセス(dumpable でない gpg-agent など)も "/proc/<pid>/cwd (readlink: ...)" の形で出す
#   - 除くのは終了中のプロセスだけ。stat の Z(ゾンビ)と E(macOS の終了中)、Linux では X(終了済み)も。
#     macOS の X はトレース中(デバッガの下)で、生きているので除かない
#   - PID 名前空間の中では、ps も lsof も同じ絞られた一覧を見る。その中の pid 1 は init ではないので、
#     pid 1 が launchd / systemd / init でなければ、一覧が絞られているとみなす。ps が pid 1 を見られないときも同じ
# hk_ps_self の終了コード: 1 ps で pid 1 を見られない / 2 pid 1 が init でない
hk_ps_self() {
  local ex='[ZE]'
  [ "$(uname -s 2>/dev/null)" = Darwin ] || ex='[ZEX]'
  ps -A -o pid= -o uid= -o stat= -o comm= 2>/dev/null | awk -v u="$(id -u)" -v ex="$ex" '
    $1 == 1 {
      one = 1
      c = $0
      sub(/^[[:space:]]*[0-9]+[[:space:]]+[0-9]+[[:space:]]+[^[:space:]]+[[:space:]]+/, "", c)
      sub(/.*\//, "", c)
      if (c == "launchd" || c == "systemd" || c == "init") init = 1
    }
    $2 == u && $3 !~ ex { print $1 }
    END { if (!one) exit 1; if (!init) exit 2 }'
}
hk_process_cwds() {
  local before after raw counts rc
  command -v lsof >/dev/null 2>&1 || { printf '%s\n' "lsof が無い"; return 1; }
  before=$(hk_ps_self)
  rc=$?
  case $rc in
    0) ;;
    2) printf '%s\n' "pid 1 が init でない。PID 名前空間の中などで、一部のプロセスしか見えていない"; return 1 ;;
    *) printf '%s\n' "ps でプロセス一覧を読めない"; return 1 ;;
  esac
  # cwd が分かった行は "pid<TAB>command<TAB>cwd"、分からなかった行は "?<TAB>pid"
  raw=$(lsof -w -a -d cwd -Fpcn 2>/dev/null | awk '
    /^p/ { pid = substr($0, 2) }
    /^c/ { cmd = substr($0, 2) }
    /^n/ {
      n = substr($0, 2)
      if (n ~ /^\// && n !~ / \([^()]*\)$/) printf "%s\t%s\t%s\n", pid, cmd, n
      else printf "?\t%s\n", pid
    }')
  after=$(hk_ps_self) || { printf '%s\n' "ps でプロセス一覧を読めない"; return 1; }
  # before と after の両方にあり、lsof に cwd 付きで出ていない pid を数える("lsof に出ない 件数<TAB>cwd を読めない 件数")。
  # 3つの一覧は "--" の行で区切って1本の入力にする
  counts=$({
    printf '%s\n' "$before" --
    printf '%s\n' "$after" --
    printf '%s\n' "$raw"
  } | awk -F'\t' '
    $0 == "--" { part++; next }
    part == 0 { b[$1] = 1; next }
    part == 1 { if ($1 in b) both[$1] = 1; next }
    $1 == "?" { bad[$2] = 1; next }
    { seen[$1] = 1 }
    END {
      m = 0; u = 0
      for (p in both) if (!(p in seen)) { if (p in bad) u++; else m++ }
      print m "\t" u
    }')
  case $counts in
    0$'\t'0) ;;
    *$'\t'0) printf '%s\n' "lsof に出ないプロセスが ${counts%%$'\t'*} 件ある。サンドボックスなどで一部しか見えていない"; return 1 ;;
    0$'\t'*) printf '%s\n' "lsof が cwd を読めないプロセスが ${counts#*$'\t'} 件ある"; return 1 ;;
    *$'\t'*) printf '%s\n' "lsof に出ないプロセスが ${counts%%$'\t'*} 件、cwd を読めないプロセスが ${counts#*$'\t'} 件ある。一部しか見えていない"; return 1 ;;
    *) printf '%s\n' "lsof の出力と ps の一覧を突き合わせられない"; return 1 ;;
  esac
  # 失敗を空の一覧(どれも使用中でない)として返さない
  raw=$(printf '%s\n' "$raw" | awk -F'\t' '$1 != "?"') || { printf '%s\n' "lsof の出力を読めない"; return 1; }
  printf '%s\n' "$raw"
}

# hk_path_in_use <path> <process-cwds>: path 以下をカレントにしているプロセスを1つ、"pid <pid> <command>" の形で返す。
# process-cwds は hk_process_cwds が成功したときの一覧。失敗したときの扱いは呼び出し側が決める。
hk_path_in_use() {
  # 入力を最後まで読む(途中で exit するとパイプの書き手が SIGPIPE で失敗し、pipefail で結果ごと失われる)
  printf '%s\n' "$2" | awk -F'\t' -v p="$1" -v self="$$" '
    !found && $1 != self && ($3 == p || index($3, p "/") == 1) { print "pid " $1 " " $2; found = 1 }'
}

# hk_path_absent <path>: path が存在しないと確かめられたときだけ成功を返す。
# [ -e ] は、親を辿れない(権限など)ときも偽になるので、それだけでは「存在しない」の根拠にならない。
# 存在する最も近い祖先を探し、それが辿れるディレクトリのときだけ、その下に path は無いとみなす。
hk_path_absent() {
  local p=$1
  if [ -e "$p" ] || [ -L "$p" ]; then return 1; fi
  case $p in /*) ;; *) return 1 ;; esac
  while [ "$p" != / ]; do
    p=${p%/*}
    [ -n "$p" ] || p=/
    if [ -e "$p" ]; then
      [ -d "$p" ] && [ -x "$p" ]
      return
    fi
  done
  return 1
}

# hk_in_progress_op <worktree-path>: 進行中の rebase / merge / cherry-pick / revert / bisect を返す。
# 何も無ければ空を返す。git が場所を1行の絶対パスで返さなければ(確かめられない)、失敗を返す。
hk_in_progress_op() {
  local f p
  for f in rebase-merge rebase-apply MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD BISECT_LOG; do
    p=$(git -C "$1" rev-parse --path-format=absolute --git-path "$f" 2>/dev/null) || return 1
    # 1行の絶対パスでなければ確かめられない。--path-format を知らない git(2.31 未満)は、
    # 知らないオプションを出力にそのまま返すので、2行になる
    case $p in /*) ;; *) return 1 ;; esac
    case $p in *$'\n'*) return 1 ;; esac
    if [ -e "$p" ]; then
      printf '%s\n' "$f"
      return 0
    fi
  done
}

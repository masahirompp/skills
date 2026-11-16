PR #1(`housekeeping-mktemp`、`main...HEAD`)のレビュー結果です。`skill-dev/housekeeping/test.sh` を手元の bash 3.2.57 で実行し、全件成功しました。リポジトリ内に CLAUDE.md は無く、ユーザー側の CLAUDE.md にもコードに関する規約が無いため、規約の観点からの指摘はありません。

```json
[
  {
    "file": "skills/housekeeping/scripts/lib.sh",
    "line": 96,
    "summary": "hk_process_cwds は自分自身($$)が lsof の一覧に出れば「プロセスを確かめられた」とみなすが、自分が見えても他のプロセスまで見えている保証にはならない。",
    "failure_scenario": "サンドボックスが同じサンドボックス内のプロセスの情報だけを許す場合(seatbelt の process-info* target same-sandbox など)や、Linux で他ユーザーの /proc/<pid>/cwd を読めない場合を考える。lsof の出力に $$ は含まれるので自己チェックは通る。しかしサンドボックスの外にあるユーザーの端末やエディタは一覧に出ない。結果として hk_path_in_use は空を返し、使用中の worktree が scan で delete と判定され、apply.sh でも skip されずに git worktree remove で消える。この PR が残す側に倒そうとしている状況そのものを取りこぼしている。"
  },
  {
    "file": "skills/housekeeping/SKILL.md",
    "line": 69,
    "summary": "apply.sh を `!` で外から実行し直す条件が「Operation not permitted」と lsof の場合しか挙がっていない。サンドボックスのネットワーク制限で push が失敗したときに、エージェントがそれと気づけない。",
    "failure_scenario": "サンドボックスの中で apply.sh を実行し、リモートブランチを `git push :refs/heads/x` で消そうとする。ネットワークが遮断されていると、エラーは 'Could not resolve host' やプロキシのエラーになり 'Operation not permitted' にはならない。その行は skipped で終わる。エージェントは手順5に従って「状態が変わったもの」と報告し、外での実行を案内しない。"
  },
  {
    "file": "skills/housekeeping/SKILL.md",
    "line": 72,
    "summary": "「何も渡さないと、何も消さずに終わる」とあるが、標準入力が端末のままだと apply.sh の `input=$(grep -v '^action	')` は入力待ちで止まり、終わらない。",
    "failure_scenario": "ユーザーが `! <skill-dir>/scripts/apply.sh` をパイプ無しで実行し、stdin が端末に繋がっていたとする。grep は EOF を待ち続け、コマンドが固まる。エージェントは結果を読めず、文書の説明とも食い違う。`[ -t 0 ]` のときにエラーで止めるなどの対処が無い。"
  },
  {
    "file": "skills/housekeeping/SKILL.md",
    "line": 20,
    "summary": "TMPDIR が未設定のときの既定値 `/tmp` に、決まった名前の housekeeping-scan.tsv を書き出し、手順4でそこから読み戻している。共有の /tmp では衝突したり、他人に中身を差し替えられたりする。",
    "failure_scenario": "TMPDIR が無い Linux で、同じホストの別セッションや別ユーザーが同じパスを先に作っていたとする(symlink、または書き込みを許したファイル)。走査の結果が上書きされるか、他人のファイルに書き込まれる。手順4の awk はその内容を apply.sh に渡すので、承認したつもりの無い delete 行が混ざりうる。修正前は TMPDIR が未設定だと `/housekeeping-scan.tsv` への書き込みで失敗していたので、この経路はこの PR で新しく開いた。"
  },
  {
    "file": "skills/housekeeping/scripts/lib.sh",
    "line": 62,
    "summary": "hk_is_protected が呼ばれるたびに、hk_protect_patterns のサブシェルと `git config --get-all` を起動している。保護パターンは実行中に変わらないので、起動時に一度だけ求めれば足りる。",
    "failure_scenario": "ローカルとリモートのブランチが数百本あるリポジトリでは、scan.sh と apply.sh の両方でブランチごとに git プロセスとサブシェルが増え、走査がその分遅くなる。起動時に一度だけ求め、失敗したら exit 1 で止める形にすれば、失敗時に保護対象とみなす分岐もここ1か所で済む。"
  },
  {
    "file": "skills/housekeeping/scripts/scan.sh",
    "line": 123,
    "summary": "`on_fp -gt 1`(first-parent 履歴を読めない)の分岐には実際には到達しない。86行目で `[ -s \"$tmp/first-parent\" ]` を確かめ、空なら exit しているため。",
    "failure_scenario": "first-parent のファイルは中身があることを確認済みなので、grep -qxF が 2 を返すのはその後にファイルが消された場合くらいしかない。保守する人は on_fp の三値分岐と理由の文言を読み解く手間を払うが、効果はほぼ無い。`if grep -qxF ...` の二値で済む。"
  },
  {
    "file": "skills/housekeeping/scripts/apply.sh",
    "line": 37,
    "summary": "入力に worktree の行が無くても、hk_process_cwds がシステム全体を対象に lsof を実行する。この PR で、その出力を awk で2回なめるようにもなった。",
    "failure_scenario": "ブランチやリモートの行だけを渡して apply.sh を実行しても、プロセスの多いマシンでは lsof に数秒かかる。`rows worktree` が空でないときだけ cwds を求めれば、この待ち時間は無くなる。"
  },
  {
    "file": "skills/housekeeping/scripts/lib.sh",
    "line": 94,
    "summary": "lsof が無い環境では、worktree を消す手段が無くなった。lsof を入れる以外に回避できず、Linux なら使える /proc/*/cwd への代替も無い。",
    "failure_scenario": "lsof を含まない最小構成の Linux コンテナや CI では、どの worktree も scan で keep、apply で skipped になり、apply.sh は毎回終了コード 1 を返す。SKILL.md は外で実行するよう案内するが、外にも lsof が無ければ解決しない。"
  },
  {
    "file": "skills/housekeeping/scripts/lib.sh",
    "line": 9,
    "summary": "根本の原因(bash 5.1 未満ではヒアドキュメントが TMPDIR の一時ファイルを使う)に対して、ヒアドキュメントを使わないという規約と、test.sh で `<<` を grep する検査で対処している。この方式は壊れやすい。",
    "failure_scenario": "将来の変更で判定の経路に一時ファイルを使う書き方が入っても、`<<` という文字列を含まない形なら grep の検査をすり抜ける。scan.sh なら、hk_mktemp_dir で作れることを確認した $tmp を `export TMPDIR=\"$tmp\"` しておけば、bash のヒアドキュメントもそこに書ける。規約と grep の検査を、仕組みの側で不要にできる。"
  },
  {
    "file": "skills/housekeeping/scripts/lib.sh",
    "line": 24,
    "summary": "hk_mktemp_dir の `[ -n \"$d\" ] && [ -d \"$d\" ]` は重複している(`[ -d \"\" ]` は必ず偽)。hk_parse_action でも、`''` の場合と `*)` の場合が同じく `action=''` で、分岐が冗長になっている。",
    "failure_scenario": "動作は変わらないが、読む人が「空のパスを別に扱う理由」や「分岐を分けた意図」を探すことになる。`[ -d \"$d\" ]` だけにし、case を1つにまとめれば同じ動作になる。"
  }
]
```

最も重いのは1件目です。サンドボックスの外でユーザーが使っている worktree を、使用中と見抜けずに消すおそれがあります。ただしこれは、そのサンドボックスが自分と同じサンドボックス内のプロセスだけを見せる設定かどうかに左右され、この環境では確かめていません。SKILL.md には、外で走査して中で apply.sh を実行すると「確かめられない」で skipped になる、と書かれています。これは中の lsof に自分自身すら見えないことを前提にした記述と読めます。中で lsof を実行し、外のプロセス(ユーザーの端末など)の cwd が見えるかを一度試せば、この指摘が当たるかどうかを切り分けられます。

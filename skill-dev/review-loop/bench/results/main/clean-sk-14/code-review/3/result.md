結論として、明確なクラッシュや誤削除が確定するバグは見つかりませんでした。ただし、安全側に倒すという修正の狙いが一部で効いていない可能性が1件あります(1件目)。手元の bash 3.2.57 で `skill-dev/housekeeping/test.sh` を実行し、全件成功しています。リポジトリ直下や変更ファイルの上位ディレクトリに CLAUDE.md は無く、~/.claude/CLAUDE.md には対話の方針しか書かれていないため、規約違反の指摘はありません。

8 findings, most severe first:

1. `skills/housekeeping/scripts/lib.sh:96`: 「プロセスを見られない」の判定が、自分自身($$)が一覧に出るかどうかだけで決まる。自分は見えるが他のプロセスは見えない、という部分的な見え方を検出できない。

   Failure scenario: サンドボックスの中で lsof に見えるのが同じサンドボックス内の scan.sh・lsof・awk だけで、別の Claude セッションやエディタがカレントにしている worktree は見えない場合。この判定は通り、cwds には自分のプロセスだけが入る。hk_path_in_use は空を返し、使用中の worktree が delete と判定され、apply.sh でも同じ理由で削除される。PR が防ぎたかった状況(SKILL.md 70行目の「サンドボックスの中では、ほかのプロセスを見られないことがある」)をそのまま見逃す。

2. `skills/housekeeping/scripts/lib.sh:91`: lsof が無い環境では、どの worktree も keep になり、apply.sh でも必ず skipped になる。この挙動を外す設定は無い。

   Failure scenario: 最小構成の Linux コンテナや CI など lsof が入っていない環境では、マージ済みの worktree を一つも片付けられない。以前は消せていたので、挙動が後退している。SKILL.md には「外で実行し直す」案内しかなく、lsof が無いという原因はサンドボックスの外で実行しても解消しない。

3. `skills/housekeeping/scripts/scan.sh:165`: 使用中と確定した場合と、確かめられなかった場合が、同じ「使用中か、確かめられない」という理由文にまとめられている。

   Failure scenario: lsof で pid 123 の vim が使用中と確定していても、理由は「使用中か、確かめられない(pid 123 vim)」になる。エージェントやユーザーは、SKILL.md の「確かめられないなら外で実行し直す」案内を誤って当てはめうる。apply.sh の43行目も同じ。hk_path_in_use が未確認を表す文字列を返して呼び出し側が非空かどうかで判定するのをやめ、cwds が空かどうかを呼び出し側で一度だけ判定して、二つの理由文を分けるほうが単純になる。

4. `skills/housekeeping/SKILL.md:72`: 「何も渡さないと、何も消さずに終わる」とあるが、apply.sh の `input=$(grep -v '^action	')` は標準入力が端末だと入力を待って止まる。

   Failure scenario: ユーザーが手元の端末で、パイプを付けずに `<skill-dir>/scripts/apply.sh` を実行すると、grep が tty からの入力を待ち続け、すぐには終わらない。文書の主張と実際の挙動が合わない。[ -t 0 ] で端末かどうかを確かめて止める処理を入れるか、文書の記述を直す。

5. `skill-dev/housekeeping/test.sh:204`: ヒアドキュメントの禁止を、grep による書き方の検査で強制している。危険の本体は「空の入力で安全でない側に倒れる」ことで、それは hk_parse_action・hk_is_protected・parse_pr_info の fail-closed 化で直っており、この検査は根本対策ではない。

   Failure scenario: 算術シフトの `$((x << 1))` を足すと誤検知で失敗する。`<<` を使わずに一時ファイルを作る書き方(`>(...)` の外部コマンドや、他のスクリプトからの呼び出し)は素通りする。新しい判定経路を足す人は、fail-closed にする点ではなく、grep を通す書き方に注意が向く。

6. `skills/housekeeping/scripts/lib.sh:62`: hk_is_protected が、パターン一覧を手書きの文字列操作で1行ずつ切り出している。lib.sh 冒頭で許可しているプロセス置換を使えば、普通の read ループで同じことができる。

   Failure scenario: `${rest%%$'\n'*}` と case の組み合わせは読みにくく、行を進める処理を continue より前に置く必要がある。順序を誤ると無限ループになる。`rest=$(...) || return 0` の後に `while IFS= read -r p; do ...; done < <(printf '%s\n' "$rest")` と書けば、失敗の検出も一時ファイルを使わないことも保ったまま、短く書ける。

7. `skills/housekeeping/scripts/apply.sh:37`: worktree の行が一つも無くても、hk_process_cwds(全プロセスを走査する lsof)を必ず実行している。

   Failure scenario: ブランチやリモートの行だけを承認して apply.sh を実行した場合でも、macOS では lsof に数秒かかる。`rows worktree | awk '$1 != "prune"'` が空でないときだけ cwds を求めれば、この待ち時間は無くなる。

8. `skills/housekeeping/scripts/scan.sh:119`: NONE の経路で、first-parent への grep を merged_into_default より前に毎回実行しているが、未取り込みのブランチではその結果を使わない。

   Failure scenario: PR の無い未取り込みブランチが多いリポジトリでは、使わない grep をブランチごとに1回実行する。merged_into_default が真になった後の elif の中で grep の終了コードを受け取る形にすれば、無駄な処理は無くなり、判定の流れも読みやすくなる。

8 findings, most severe first:

1. `skills/housekeeping/scripts/lib.sh:96`: lsof でほかのプロセスを見られるかどうかを「自分自身($$)が一覧に出るか」で判定しているが、同じサンドボックスの中のプロセスだけが見える環境では、この判定を通ってしまう。

   Failure scenario: サンドボックスが同じサンドボックス内のプロセスの情報だけを許すとき、scan.sh 自身は一覧に出るので cwds は空にならない。ところが、ユーザーの端末やエディタ(サンドボックスの外)が wt-X をカレントにしていても一覧に出ない。そのため hk_path_in_use は空を返し、wt-X は delete と判定される。apply.sh も同じ理由で確かめ直しを素通りし、使用中の worktree を消す。判定には、自分の子孫ではないプロセス(別セッションのプロセスなど)が見えることを使う必要がある。あるいは ps -A の件数と比べる。

2. `skills/housekeeping/scripts/scan.sh:208`: worktree を「lsof でプロセスを確かめられない」理由で残したときも、そのブランチの行の理由は「worktree X で使用中」になり、確かめられなかっただけだと伝わらない。

   Failure scenario: サンドボックスで lsof が使えない状態で走査すると、マージ済みのブランチ wt-merged の branch 行が keep「worktree … で使用中」になる。SKILL.md は外で走査し直す手順を worktree の行についてしか書いていない。そのため、エージェントはブランチが実際に使用中だと報告してしまい、外で走査し直せば消せたことに気づかない。

3. `skills/housekeeping/scripts/scan.sh:86`: 既定ブランチの first-parent 履歴を読めないと走査全体を error で止める。履歴を使うのは PR なし(NONE)のブランチの判定だけなのに、worktree・PR 済みブランチ・リモートの判定までまとめて失われる。

   Failure scenario: origin/HEAD が未設定のときは、hk_default_branch が gh から既定ブランチ名を得る。そのブランチの ref が手元にもリモート追跡にも無い場合(fetch 失敗、ローカルで別名にしている)、以前は走査が進み、NONE のブランチは merged_into_default の失敗で keep になっていた。今は「履歴を読めない」で exit 1 になる。classify_branch には on_fp>1 で keep にする分岐がすでにあるので、走査を止めずにそちらで残せる。

4. `skills/housekeeping/scripts/scan.sh:212`: worktree で使っているブランチでは、handle_wt で一度 classify_branch を呼んだあと、ローカルブランチの段で同じ sha について classify_branch をもう一度呼ぶ。jq 2回と、場合によってはネットワーク fetch(refs/pull/N/head)が二重に走る。

   Failure scenario: PR の head コミットが手元に無い worktree ブランチでは、verify_pr_merged の `git fetch refs/pull/N/head` がブランチごとに2回走り、走査がその分遅くなる。wt-branches に action と reason も書いておき、head と sha が同じなら判定結果を使い回せばよい。

5. `skills/housekeeping/scripts/scan.sh:119`: on_fp を得る grep を merged_into_default より前に無条件で実行しているので、未取り込みのブランチでは結果を使わない grep が毎回走る。

   Failure scenario: PR なしで未取り込みのブランチが多いリポジトリでは、ブランチごとに first-parent ファイル全体(既定ブランチの全履歴)を grep するが、その結果を捨てている。grep を `! merged_into_default` の分岐の後に回し、elif の中で終了コードを見る形にすれば済む。

6. `skills/housekeeping/scripts/lib.sh:63`: hk_is_protected が、パターンの一覧を ${rest%%$'\n'*} と case で1行ずつ切り出す手書きのループになっている。lib.sh 自身がプロセス置換は使ってよいとしているので、もっと単純に書ける。

   Failure scenario: `while IFS= read -r p; do ...; done < <(printf '%s\n' "$rest")` と書けば、glob に展開されない性質は同じまま、文字列を切り出す処理(continue の前に rest を進める順序に依存する)が無くなり、保守しやすくなる。scan.sh の parse_pr_info も、`read -r st num oid < <(pr_info ...)` に置き換えられる。

7. `skills/housekeeping/scripts/apply.sh:37`: 承認された行に worktree が無くても hk_process_cwds を呼ぶので、全プロセスを対象にした lsof が毎回走る。

   Failure scenario: ブランチやリモートの行だけを渡したときも、lsof -w -a -d cwd が全プロセス(この環境では1000件超)を走査するので、数秒かかることがある。`[ -n "$(rows worktree)" ]` のときだけ呼べば、この待ち時間は無くなる。

8. `skill-dev/housekeeping/test.sh:62`: ヒアドキュメントを使っていないことを、`<<` と `mktemp` を文字列で grep して確かめている。行頭のコメントしか除外しないので、検査として脆い。

   Failure scenario: 算術シフト `$((x << 1))` や、行末のコメントにある `<<` でも誤って FAIL になる。逆に、lib.sh を source する新しいヘルパーファイルにヒアドキュメントを足しても、検査の対象外なので見逃す。根本の対策(判定結果が空なら残す側に倒す)は hk_parse_action などで入っているので、構文の検査ではなく、TMPDIR を書けない状態で判定が keep になることを動作で確かめるほうが確実。

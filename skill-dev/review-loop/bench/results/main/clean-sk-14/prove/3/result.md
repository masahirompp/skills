証明できた指摘は1件です。同梱のテスト(`skill-dev/housekeeping/test.sh`)は「全件成功」で通ります。

## 指摘1: Claude Code のサンドボックスと同じ条件では、別のプロセスが使用中の worktree が `delete` と判定され、apply.sh で実際に消える

**仕組み**
- コミットの意図は、lsof でプロセスを見られないときに worktree を「確かめられない」として残すことです。
- 実装 `lib.sh` の `hk_process_cwds` は、`$$`(自分自身)が一覧に出るかどうかで、プロセスを見られるかを判定しています。
- Claude Code の sandbox プロファイルは `(allow process-info* (target same-sandbox))` と `(allow process-info-listpids)` を含みます。手元の Claude Code 2.1.325 のバイナリで、`strings` を使って確認しました。
- この設定では、自分と同じサンドボックスのプロセスだけが見えます。そのため自己確認は通りますが、サンドボックスの外にあるユーザーのシェルやエディタは見えません。結果として「使用中でない」と判定され、fail-open になります。
- `sandbox-exec` で同じ規則を当てて再現しました。外の環境に影響を与えないよう、`(allow default)` を土台にして、プロセス情報の規則だけを変えています。

**実行したコマンド**
```
cd .../skills/scratch && ./repro-lsof.sh 2>&1
```
`scratch/repro-lsof.sh` の内容は次のとおりです。
1. `lsof-repo/` に bare の origin、作業用の clone、`feat` ブランチを作る。`feat` は main に ff で取り込み済みで、worktree は `wt-feat`。PR 一覧は `[]`
2. サンドボックスの外で `(cd wt-feat && exec sleep 60) &` を起動する
3. scan.sh を、サンドボックスの外と、`sandbox-exec -p '(version 1)(allow default)(deny process-info*)(allow process-info-listpids)(allow process-info* (target same-sandbox))'` の中でそれぞれ実行する
4. サンドボックスの中の scan.sh の結果を、同じサンドボックスの中の apply.sh に流す

**出力**(1回目の実行です。パスは途中を省略しています。最後の行は、生存確認を `ps` に直して再実行したときのもので、sha と pid はその回の値です)
```
--- サンドボックスの外で scan.sh(pid 28163 が wt-feat を使用中)
keep	worktree	feat	e20732ee…	…/lsof-repo/wt-feat	プロセスがカレントディレクトリとして使用中か、確かめられない(pid 28163 sleep)
keep	branch	feat	e20732ee…		worktree …/lsof-repo/wt-feat で使用中
--- サンドボックスの中で scan.sh
delete	worktree	feat	e20732ee…	…/lsof-repo/wt-feat	PR なし・main に取り込み済み(このブランチでコミットした記録がある)
delete	branch	feat	e20732ee…		worktree …/lsof-repo/wt-feat と一緒に消す。PR なし・main に取り込み済み(このブランチでコミットした記録がある)
--- サンドボックスの中で apply.sh
done	worktree …/lsof-repo/wt-feat
done	branch feat (e20732ee…)
--- 後: wt-feat の存在 / sleep の生存
ls: …/lsof-repo/wt-feat: No such file or directory
29564 sleep        ← 再実行時。sleep は生きたまま、カレントディレクトリだけが消えている
```

**出るべきだった出力**
サンドボックスの中でも、外と同じく `keep	worktree	feat	…	プロセスがカレントディレクトリとして使用中か、確かめられない(…)` と `keep	branch	feat	…` になるべきでした。apply.sh は `skipped	worktree …: プロセスが使用中か、確かめられない(lsof でプロセスを確かめられない)` で止まり、`wt-feat` は残るべきでした。

**補足**
- 自分自身が見えても、外のプロセスまで見えるとは限りません。自己確認の目印を、たとえばサンドボックスの外で動いているプロセス(launchd の pid 1 など)が見えるかどうかに変えるのが一案です。ただし、どの環境でも確実に効く方法かどうかは確かめていません。
- 再現に使ったのは実際の Claude Code ではなく、その設定のうちプロセス情報の規則だけを写した `sandbox-exec` です。

ほかにも、`hk_parse_action`、`parse_pr_info`、first-parent の ref の組み立て、apply.sh の変数化、保護パターンの照合を読みました。証明できた不具合はありません。

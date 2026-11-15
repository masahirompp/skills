実行で証明できた指摘は1件です。既存のテスト(`skill-dev/housekeeping/test.sh`)は、bash 3.2(macOS の `/bin/bash`)で全件通りました。

## 指摘1: サンドボックスがほかのプロセスだけを隠すと、使用中の worktree が「使用中でない」と判定され、apply.sh に消される

**どういう問題か**
`hk_process_cwds` が lsof を「見られない」とみなすのは、自分自身(`$$`)すら一覧に出ないときだけです。サンドボックスが自分のプロセスツリーを見せたまま、ほかのセッションのプロセスだけを隠す場合、この判定を通り抜けます。その結果、ほかのプロセスが使っている worktree が「使用中でない」とされ、scan.sh は delete と判定し、apply.sh は実際に消します。

SKILL.md はこの状況を想定しています。「サンドボックスの中では、ほかのプロセスを見られないことがある」と書き、そのときは「lsof でプロセスを確かめられない」で skipped になる前提で案内しています。実装はその前提を満たしていません。

**再現の条件**
Seatbelt のプロファイル `(deny process-info* (target others))` で、プロセスが見えない状態を作りました。この中の lsof には、自分と同じセッションのプロセスだけが見え、`setsid` した別セッションのプロセスは見えません。これを先に確かめたコマンドと出力は次のとおりです(13670 は別セッションで worktree を使っている sleep)。

```
$ ... ps -o pid,ppid,sess,comm -p $b; sandbox-exec -p '(version 1)(allow default)(deny process-info* (target others))' bash -c 'echo self=$$; lsof -w -a -d cwd -Fpcn 2>/dev/null | grep "^p" | paste -sd" " -'
  PID  PPID   SESS COMM
13670     1      0 sleep
self=13692
p13651 p13692 p13693 p13694 p13695
```

自分(13692)は一覧に出て、13670 は出ていません。なお、Claude Code の実際のサンドボックスがこのプロファイルと同じ見え方をするかどうかは確かめていません。

**再現の内容**
再現スクリプトは `scratch/repro-lsof.sh` です。マージ済みのブランチ `feat` の worktree を作り、別セッションのプロセスにその worktree をカレントディレクトリとして使わせます。そのうえで、scan.sh をサンドボックスの外と中で1回ずつ実行し、apply.sh をサンドボックスの中で実行します。

**実行したコマンド**
```
cd /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-v3u49r_y/w/355d7f2fff/skills/scratch && sed -i '' 's|os.setsid(); os.chdir(sys.argv\[1\]); os.execvp|fd=os.open("/dev/null",os.O_RDWR); [os.dup2(fd,i) for i in (0,1,2)]; os.setsid(); os.chdir(sys.argv[1]); os.execvp|' repro-lsof.sh && grep -n setsid repro-lsof.sh && ./repro-lsof.sh
```
(最初の実行は無効なので除いています。`$(...)` が sleep の終了を待ってしまい、走査の時点で使用中のプロセスが無くなっていたためです。上の `sed` で子プロセスの出力を `/dev/null` に切り離して、実行し直しました。)

**出力**
```
20:    fd=os.open("/dev/null",os.O_RDWR); [os.dup2(fd,i) for i in (0,1,2)]; os.setsid(); os.chdir(sys.argv[1]); os.execvp("sleep",["sleep","120"])
--- 外で scan.sh (pid 10800 が wt-feat を使用中)
keep	worktree	プロセスがカレントディレクトリとして使用中か、確かめられない(pid 10800 sleep)
keep	branch	worktree /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-v3u49r_y/w/355d7f2fff/skills/scratch/lsof-fixture/wt-feat で使用中
--- サンドボックスの中で scan.sh
delete	worktree	PR なし・main に取り込み済み(このブランチでコミットした記録がある)
delete	branch	worktree /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-v3u49r_y/w/355d7f2fff/skills/scratch/lsof-fixture/wt-feat と一緒に消す。PR なし・main に取り込み済み(このブランチでコミットした記録がある)
--- サンドボックスの中で apply.sh (worktree の delete 行を渡す)
done	worktree /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-v3u49r_y/w/355d7f2fff/skills/scratch/lsof-fixture/wt-feat
apply rc=0
--- 結果
pid 10800 はまだ動いている
ls: /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-v3u49r_y/w/355d7f2fff/skills/scratch/lsof-fixture/wt-feat: No such file or directory
```

**出るべきだった出力**
この変更の意図は、プロセスを見られないときは「確かめられない」として残すことです。そのため、サンドボックスの中でも次のようになるべきでした。
- scan.sh: worktree は `keep`(理由は「…確かめられない(lsof でプロセスを確かめられない)」)、ブランチは `keep`(「worktree … で使用中」)
- apply.sh: `skipped	worktree …: プロセスが使用中か、確かめられない(lsof でプロセスを確かめられない)`、終了コード 1、worktree は残る

実際には、外では keep になった worktree が中では delete になり、プロセス 10800 が使っている最中に apply.sh が消しました(`done`)。

## 試したが、指摘にならなかったもの
次は実行したうえで問題が出なかったので、指摘に入れていません。
- `TMPDIR` が無いときに fetch より前に止まること、一時ディレクトリを片付けること
- 保護パターンの照合と `git config` が壊れているときの扱い
- 判定の結果が壊れているときに keep に倒すこと
- 読めない PR 一覧で止まること
- ローカルの既定ブランチが無いときの first-parent の扱い

検証で作ったファイルは `scratch/` に残っています(`scratch/bin`、`scratch/repro-lsof.sh`、`scratch/lsof-fixture`)。

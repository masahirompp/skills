実行で証明できた指摘は1件です。既存のテスト `skill-dev/housekeeping/test.sh` はすべて通ります(「全件成功」)。そのため、テストが置いていない前提を突いて壊しました。

## 指摘1: lsof に自分のプロセスだけが見えるサンドボックスでは、使用中の worktree を delete と判定し、apply.sh で実際に消してしまう

この PR は、`hk_process_cwds`(`skills/housekeeping/scripts/lib.sh`)に次の判定を入れています。「自分自身(`$$`)が lsof の一覧に出れば、プロセスは見えている」。一覧に出なければ「確かめられない」として worktree を残します。

しかし、macOS の sandbox(seatbelt)では、同じサンドボックスの中のプロセスにだけ情報の取得を許すことができます。この設定では、自分は一覧に出て判定を通ります。一方、サンドボックスの外にあるプロセスは一覧に出ません。たとえば、その worktree を開いているシェルやエディタです。そのため「使用中でない」と判定します。SKILL.md は「サンドボックスの中では、ほかのプロセスを見られないことがある」を前提にしており、まさにその状況で保護が外れます。

再現には `sandbox-exec` を使い、次のプロファイルを渡しました。
```
(version 1)
(allow default)
(deny process-info*)
(allow process-info-listpids)
(allow process-info* (target same-sandbox))
```
fx の中には次のものを用意しました。
- `main` に取り込み済みのブランチ `feat` と、その worktree `wt-feat`
- サンドボックスの外で起動し、`wt-feat` をカレントにした `sleep`

### 1-a. scan.sh

**実行したコマンド**
```
cd /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-pn2pr0k5/w/958ed47dcf/skills/scratch && cat > repro-sandbox-lsof.sh <<'EOF'
…(scratch/repro-sandbox-lsof.sh の内容)…
EOF
chmod +x repro-sandbox-lsof.sh && ./repro-sandbox-lsof.sh
```
スクリプトの中で scan.sh を呼んでいる行は次のとおりです。
```
HOUSEKEEPING_PR_JSON="$r/prs.json" sandbox-exec -f "$here/sb.sb" "$scripts/scan.sh" | grep -E 'worktree|feat'
```

**出力**
```
busy pid=87395 (cwd=/private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-pn2pr0k5/w/958ed47dcf/skills/scratch/fx/wt-feat)
--- サンドボックスの外で lsof に見えるか
n/private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-pn2pr0k5/w/958ed47dcf/skills/scratch/fx/wt-feat
--- サンドボックスの中で scan.sh
delete	worktree	feat	4c8c8043031fc9070381b964df43a19cb8d72195	/private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-pn2pr0k5/w/958ed47dcf/skills/scratch/fx/wt-feat	PR なし・main に取り込み済み(このブランチでコミットした記録がある)
delete	branch	feat	4c8c8043031fc9070381b964df43a19cb8d72195		worktree /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-pn2pr0k5/w/958ed47dcf/skills/scratch/fx/wt-feat と一緒に消す。PR なし・main に取り込み済み(このブランチでコミットした記録がある)
keep	branch	main	4c8c8043031fc9070381b964df43a19cb8d72195		worktree /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-pn2pr0k5/w/958ed47dcf/skills/scratch/fx/repo で使用中
```

### 1-b. 外の scan.sh(対照)と、中の apply.sh

**実行したコマンド**
```
cd /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-pn2pr0k5/w/958ed47dcf/skills/scratch && cat > repro-sandbox-apply.sh <<'EOF'
…(scratch/repro-sandbox-apply.sh の内容)…
EOF
chmod +x repro-sandbox-apply.sh && ./repro-sandbox-apply.sh
```

**出力**
```
--- 対照: サンドボックスの外で scan.sh
keep	worktree	プロセスがカレントディレクトリとして使用中か、確かめられない(pid 89458 sleep)
keep	branch	worktree /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-pn2pr0k5/w/958ed47dcf/skills/scratch/fx/wt-feat で使用中
--- 同じ行(worktree と branch の delete)を、サンドボックスの中の apply.sh に渡す
done	worktree /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-pn2pr0k5/w/958ed47dcf/skills/scratch/fx/wt-feat
done	branch feat (0f0bf654071c802acb97c1888a2b4dcb6ef8a8f4)
exit=0
--- 後: busy プロセスは生きているか / worktree は残っているか
pid 89458 alive
ls: /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-pn2pr0k5/w/958ed47dcf/skills/scratch/fx/wt-feat: No such file or directory
```
最後の `ls` が失敗したので、スクリプト全体の終了コードは 1 でした。

サンドボックスの外では、正しく `keep` になります(対照)。中の apply.sh は、生きているプロセスのカレントディレクトリを `done` で消しました。

### 出るべきだった出力
この変更の意図は「プロセスを見られないときは、どの worktree も確かめられないとして残す」ことです。それに照らすと、次のようになるべきでした。
- scan.sh: `keep	worktree	feat	…	プロセスがカレントディレクトリとして使用中か、確かめられない(lsof でプロセスを確かめられない)`。branch `feat` も `keep`
- apply.sh: `skipped	worktree …: プロセスが使用中か、確かめられない(lsof でプロセスを確かめられない)` で、終了コード 1。worktree は残る

### 補足(判断の材料)
- この再現では、自分でサンドボックスのプロファイルを書きました。Claude Code の実際のサンドボックスがこの権限の組み合わせかどうかは、確かめていません。ただ、自分が見えるかどうかで他のプロセスも見えるとみなす推論は、少なくとも macOS の seatbelt で成り立たないことを実行で示せました。
- 確かめる対象を自分から、サンドボックスの外にいる親プロセス(`$PPID` や祖先)に変えると、この再現には効きそうです。ただし、どの祖先がサンドボックスの外にいるかは環境によって変わるので、確実な判定にはなりません。

---

ほかにも、次の点を実行して確かめましたが、壊れる挙動は見つかりませんでした。
- ヒアドキュメントが残っていないか
- 一時ディレクトリを作れないときに止まるか
- PR 一覧の JSON が不正なときに、残す側に倒れるか

再現に使ったファイルは `scratch/` に置いてあります。中身は再現スクリプト2本、`sb.sb`、使い捨てリポジトリ `fx/` です。

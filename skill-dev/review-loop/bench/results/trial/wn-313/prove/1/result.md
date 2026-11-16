証明できた指摘は2件です。1件目は main からの後退で、2件目は文書に書かれたとおりの動きですが、文書に書かれた理由とは合っていません。

## 指摘1: 案内のセッションで分割したシェルが `exit` で閉じず、`@wn_guide_died` も上書きされる

`pane-died` の `wbguide)` の分岐は、案内のプログラムのペインかどうかを見ていません。案内の画面で `ctrl+q %` で分割したシェルも「起動し直す」対象になります。

**実行したコマンド**

```
npx vitest run --dir scratch --no-file-parallelism --testTimeout 120000 --reporter verbose --silent=false
```

`scratch/break.test.ts` の A です。作業台の画面を開き、`C-q` `%` で分割し、`exit` を打ち、3.5 秒後のペインを見ます。

**出力(このブランチ。A の部分)**

```
A panes after split:
%1 dead=0 cmd=node respawned=
%2 dead=0 cmd=zsh respawned=

A panes 3.5s after exit:
%1 dead=0 cmd=node respawned=
%2 dead=0 cmd=zsh respawned=1
A @wn_guide_died: 2026-11-15 00:14:05 status=0 signal= ~ ❯ exit Pane is dead (status 0, Sun Nov 15 00:1 

A wb screen:
No workbench for alpha yet.             │
Enter: open a shell in /tmp             │~
                                        │❯
```

**出るべきだった出力**

main の版(`git archive main` を `scratch/main` に展開してビルド)で同じ手順を実行した結果と同じになるはずです。

```
(cd scratch/main && npx vitest run --root . --dir scratch --no-file-parallelism --testTimeout 120000 --reporter verbose --silent=false)
```

```
A panes 3.5s after exit:
%1 dead=0 cmd=node respawned=
A @wn_guide_died: 
A wb screen:
No workbench for alpha yet.
Enter: open a shell in /tmp
```

意図は「案内のプログラムが終わったら起動し直す」なので、利用者が開いたシェルは `exit` で閉じるはずです。このブランチでは、ペインの上限が5回なので、閉じるまでに `exit` が6回要る計算です(6回打つところまでは実行していません)。

`@wn_guide_died` は案内のプログラムが落ちた手がかりを残すためのものですが、シェルの正常終了(`status=0`)で上書きされ、本物の手がかりが消えます。

## 指摘2: 案内のプログラムが間を置いて6回終わると、作業台の画面が理由を出さずに閉じる

`@wn_respawned` は増えるだけで戻りません。「起動してすぐ終わる」場合と、長く動いたあとに終わる場合を区別しません。

**実行したコマンド**

指摘1と同じコマンドの B です。案内が描き直されたのを確かめてから、5 秒以上あけて案内のプログラムを `SIGKILL` し、これを6回繰り返します。

**出力(B の部分)**

```
B kill 1: respawned, sessions=list,wbguide wb=wbguide
B kill 2: respawned, sessions=list,wbguide wb=wbguide
B kill 3: respawned, sessions=list,wbguide wb=wbguide
B kill 4: respawned, sessions=list,wbguide wb=wbguide
B kill 5: respawned, sessions=list,wbguide wb=wbguide
B kill 6: NOT respawned, sessions=list wb=undefined
B wb screen:
[exit 0]
```

**出るべきだった出力**

6回目も `respawned, sessions=list,wbguide wb=wbguide` となり、作業台の画面が残るはずです。

- **文書との関係**: 「ペインごとに5回まで、超えたら畳む」は DESIGN.md と `docs/lib/tmux.md` に書かれていて、動きは文面どおりです。ただし理由は「起動してすぐ終わるときに回り続けないため」で、5 秒以上動いた案内はこれに当たりません。
- **起きうる場面**: 終わる原因は「まだ分かっていない」とあるので、whatnext を長く動かすと6回目に達しえます。
- **閉じ方**: 一覧が動いたまま、作業台の画面が終了コード 0 で、標準エラーに何も出さずに閉じます。直そうとした症状と同じ見え方で、「つなげなかったときは理由を出す」の経路も通りません。
- **回復**: `whatnext workbench` をもう一度起動すれば開く経路は、差分にある e2e テスト(案内のセッションを消してから開く)で通っています。6回目のあとに開き直すところは実行していません。

## 壊せなかったもの

次は実行して、意図どおりでした。

- ユニットテスト 114 件、`npm run check`、作業台の e2e 15 件(差分で足した2件を含む)は通りました。
- 作業台がある行を選んだまま案内のセッションを消して `whatnext workbench` を開くと、案内が作り直され、画面は `sh-a0000000` に切り替わりました。
- `WHATNEXT_WORKBENCH_SPLIT=1` で whatnext が動いていないときは `Press any key to close.` で待ち、キーを押すと 1 で終わりました。
- 同じく分割からつないだあと whatnext を `q` で終えると、キーを待たずに 0 で終わりました。
- attach が失敗したとき(stdin が端末でない)は、tmux のメッセージと理由が出て 1 で終わりました。

再現スクリプトは `scratch/break.test.ts` と `scratch/d.test.ts`、main の版は `scratch/main/` に残しています。commit はしていません。

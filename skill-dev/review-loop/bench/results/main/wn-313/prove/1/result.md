実行で証明できた指摘は1件です。案内のプログラムが落ち続けると、作業台の画面は今も何も出さずに閉じます。直したはずの症状が、終了コード 0 で戻ってきます。

ほかに試したものは、すべて変更の意図どおりに動きました。

---

## 指摘1: 案内が6回落ちると、作業台の画面が何も出さずに閉じる(終了コードは 0)

案内のプログラムを `SIGKILL` で6回落としました。落とすたびに、案内が描き終わってから5秒おいています。案内が終わるたびに、`whatnext workbench` の様子と、案内のセッションが残っているかを記録しました。`WHATNEXT_WORKBENCH_SPLIT=1` で、Ghostty の分割から起動した場合と同じ条件にしています。

**実行したコマンド**(テストは `scratch/spaced.test.ts`。e2e の Harness を使う)
```
rm -f /tmp/wn-spaced.log; npx vitest run scratch/spaced.test.ts --testTimeout 120000 2>&1 | tail -3; cat /tmp/wn-spaced.log
```

**出力**
```
   Start at  07:35:51
   Duration  42.26s (tests 100%)

2026-11-14T22:35:59.058Z crash 1: respawned=1 sessions=list,wbguide
2026-11-14T22:36:05.887Z crash 2: respawned=2 sessions=list,wbguide
2026-11-14T22:36:12.726Z crash 3: respawned=3 sessions=list,wbguide
2026-11-14T22:36:19.550Z crash 4: respawned=4 sessions=list,wbguide
2026-11-14T22:36:26.382Z crash 5: respawned=5 sessions=list,wbguide
2026-11-14T22:36:33.213Z crash 6: respawned= sessions=list
wb screen:
[status 0]
[exit 0]
```
(`[status 0]` は、テストで `whatnext workbench` のあとに付けた `echo "[status $?]"` の出力です。)

**変更の意図に照らして、出るべきだった出力**

このコミットの目的は「作業台の画面が開いた直後に閉じる」を直すことです。その方針として、つなげなかったときは行を消さずに理由を標準エラーに出し、Ghostty の分割ではキーを待つ、と書いています。上限の6回目のあとは、案内のセッションが畳まれ、画面が閉じても次のように出るべきでした。
- `[status 0]` の前に、理由が標準エラーに出る(例: `whatnext: the workbench guide stopped ...`)。
- 終了コードは 0 以外になる。
- `Press any key to close.` を出してキーを待つ。

実際には、何も出さずに 0 で終わり、Ghostty の分割はそのまま閉じます。tmux はセッションが消えて離れたときも 0 で終わるので(scratch で確かめました)、今の `res.status !== 0 && 一覧がある` という判定ではこの場合を捕まえられません。

上限に届く条件も、想定より広いです。DESIGN.md は上限の理由を「起動してすぐ終わるときに回り続けないため」と書いています。しかし `@wn_respawned` の回数は戻されないので、上の出力のように、5秒以上動いてから落ちた場合も数えられます。ペインが生きているかぎり、落ちた回数は通算で積み上がります。

この判断には、利用者が決める余地があります。DESIGN.md は「超えたら畳む」までしか書いておらず、そのとき作業台の画面をどうするかは決めていません。次の二択です。
- 挙動 A: 上限に達したら、作業台の画面は理由を出してキーを待つ。
- 挙動 B: 上限に達したら、何も出さずに閉じる(今の挙動)。

---

## 試したが、壊れなかったもの(実行済み)

- **一覧が動いていないとき(分割から起動)**: `whatnext is not running. Start whatnext first.` と `Press any key to close.` が出て、キーを押すと `[exit 1]` で終わりました。
- **分割から起動して、whatnext を `q` で終えたとき**: `[exit 0]` で、キーを待たずに終わりました。サーバごと閉じた場合を、つなげなかった場合と取り違えていません。
- **案内が終わったときの記録(`@wn_guide_died`)**: 時刻、`signal=kill`、案内の画面の末尾(`Enter: open a shell in /tmp`)が残りました。
- **単体テストと e2e テスト**: `npm test` は 114件、`test/e2e/workbench.test.ts` は 15件で、すべて通りました。

対象外にしたものが1件あります。作業台があるセッションにカーソルを置いたまま `whatnext workbench` を開き直すと、作業台ではなく案内(`No workbench for alpha yet.`)が出ます。これは main をビルドしても同じように再現したので、今回の差分によるものではありません。

確かめに使ったテストは `scratch/` に残してあります(`break.test.ts`、`spaced.test.ts`、`died.test.ts`、`reopen.test.ts`)。main との比較に使った worktree は削除しました。コミットはしていません。

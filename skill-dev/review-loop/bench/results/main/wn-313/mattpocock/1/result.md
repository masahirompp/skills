## Standards

**(a) 文書化された標準に反する箇所(hard になりうるもの)**

1. **src が、契約に書かれていない lib の振る舞いに頼っている**(`src/cli/env.ts` の `workbenchCommand`、`src/ops/ports.ts`)
   - `docs/lib/README.md` には「契約に書いていない振る舞いに頼らない」とあります。
   - 今回の修正は「`exec` は `splitWorkbench` が付ける」ことを前提に、src の側から `exec` を外しています。
   - ところが `docs/lib/tmux.md:43` の契約は「`command` を打ち込む」と書くだけで、先頭に `exec` を付けることには触れていません(差分と突き合わせて確認しました)。
   - 今回の不具合の原因そのものなので、契約に書き足すべきです。
2. **lib の振る舞いを守るテストが、消える層にある**(`test/unit/cli.test.ts`)
   - 「`exec` が1つだけ付く」ことを確かめるテストが `test/unit/` にあります。
   - ADR-0021 と `docs/lib/README.md` は、lib のテストを `lib/<部品>/*.test.ts` に置くと決めています。
   - このままでは cycle-end で、lib の側の保証もテストと一緒に消えます。
3. **契約の「名前の約束」が欠けている**(`docs/lib/tmux.md`)
   - `:10` は頼みごとの形を `key`・`focus`・`agentview` と列挙していますが、新しく足した `guide` がありません。
   - ペインのオプション `@wn_respawned` の名前が、docs のどこにもありません。
4. **学びの捕捉**(CLAUDE.md「学びの捕捉」)
   - DESIGN.md に「案内のプログラムがなぜ終わったかは、まだ分かっていない」と書かれています。これは `bug` か `learning` の issue にする観察です。
   - exec の重複(zsh では動き、bash では失敗する)も同じです。
   - 起票済みかどうかは、gh の認証が切れていたため確かめられていません。

lib を変えるときの順序(docs → テスト → コード)は守られています。

**(b) smell(どれも判断の範囲)**

- **Duplicated Code 候補**(`src/cli/list.ts`):`ensureGuide` のすぐあとに `tmux.workbenchOptions(GUIDE, '')` を呼んでいます。サブエージェントによると、セッションを作った場合は `ensureGuide` の中でも呼ぶので2回になります。私は `guide.ts` の中までは確かめていません。
- **Feature Envy**(`src/cli/workbench.ts` の `askListToRefreshGuide`):頼みごとの送り方(`@wn_req_<秒>_<pid>` に書いてから SIGUSR2 を送る)を src の側で組み直しています。受け取る側は `takeRequests` として lib にあるので、送る側も `Tmux` にまとめるほうが自然です。
- **Primitive Obsession**:`'@wn_pid'` や `'agentview'` を素の文字列で書いています。同じ場所で `GUIDE_REFRESH` は定数を使っており、そろっていません。
- **Mysterious Name**:`GUIDE_REFRESH` の値が `'guide'` だけで、「入れ直す」という意味が値から読めません。
- **一貫性**:`fail()` は `process.env.WHATNEXT_WORKBENCH_SPLIT` を直接読んでいます。ほかの環境変数は `readEnv`/`Env` を通しています。
- **壊れやすいテスト**:`lib/tmux/tmux.test.ts` は、sh の本文を `indexOf`/`lastIndexOf` で切り出して、部分文字列を比べています。

## Spec

issue の参照はなかったため、`docs/PRODUCT.md`・`docs/DESIGN.md`・`docs/lib/tmux.md` を仕様として見ました。不具合の中心(案内のセッションの消失と exec の重複)の直し方は docs と合っています。DESIGN.md と tmux.md の追記も実装と一致しています。

**(b) PRODUCT.md にない観測できる挙動(層2)**

1. **新しい英語の文言3つと「キーを待つ」挙動が、PRODUCT.md になく DESIGN.md にだけ書かれている**
   - 文言は `could not create the workbench guide`、`could not open the workbench screen`、`Press any key to close.` の3つです。
   - PRODUCT.md は `whatnext workbench` の失敗を文言ごと決めています(490行の `whatnext is not running. Start whatnext first.`、シナリオ59)。
   - 「失敗した分割はすぐ閉じる/キーを押すまで残る」は二択で聞けるので、層1として扱う理由がありません。利用者の判断を得てから、PRODUCT.md に足す必要があります。
2. **起動し直しと作り直しは、要件の回復として妥当**
   - 5回の上限と `@wn_guide_died` は内部の作りなので、層1で構いません。
   - ただし `decision-log` の issue が見当たりませんでした。

**(c) 実装の誤りが疑われる点**

3. **5回の数え方が、目的とずれている**
   - 契約は「起動してすぐ終わるときに回り続けないため」と書いています。ところが `@wn_respawned` は増えるだけで戻らず、経過時間も見ていません。何時間もかけて5回落ちた場合でも畳みます。
   - 畳んだ時点で作業台の画面が案内を映していると、作業台の画面は何も示さずに離れます。新しく足したキー待ちも、この経路では効きません。
4. **頼みごと `guide` は、一覧が作業台の画面を知るまで効かない**:`doFollow` の `if (!wb) return` で抜けるため、作り直した直後は名前が空で出る可能性があります。e2e が通るなら、実害は小さいと見ています。
5. **attach の失敗判定(`status !== 0 && hasSession(LIST)`)が実測されていない**:`detach-client` で譲るときや、`kill-server` との順序の競合で、tmux がどの終了コードを返すかは確かめられていません。

**(a) 欠けているもの**

6. 次の3つにテストがありません。サイクル9は本番品質なので、足りないと考えます。
   - attach の失敗の経路
   - `fail()` のキー待ち
   - 5回を超えたら畳む挙動(今は文字列が含まれるかを見ているだけ)

---

指摘の数は Standards が10件(hard 4件、smell 6件)、Spec が6件です。Standards で最も重いのは、src が契約にない `splitWorkbench` の `exec` 付与に頼っていることで、今回の不具合と同じ形がまた起きうる穴です。Spec で最も重いのは、新しい文言とキー待ちを利用者の判断なしに入れ、PRODUCT.md にも書いていないことです(層2)。

両軸とも、テストは実行していません。

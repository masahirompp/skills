Standards 軸と Spec 軸の2つのレビューを並行して走らせています。両方の結果が届いたら、軸ごとにまとめて報告します。

Standards 軸のレビューが終わりました。契約 docs の記述が足りないという指摘は、手元で確かめて正しいと分かりました(`docs/lib/tmux.md:10` の頼みごとの形の一覧に、新しい `guide` がありません)。Spec 軸のレビューはまだ終わっていません。届いたら、2つを並べて報告します。

差分 `git diff main...HEAD`(コミット d212b82 の1件、13ファイル、追加177行・削除15行)を、2つの軸に分けてレビューしました。コミットに issue の参照がないため、仕様には `docs/PRODUCT.md`、`docs/DESIGN.md`、`docs/lib/tmux.md` とコミットメッセージを使いました。

## Standards

**文書化された規約との食い違い**

1. **利用者から見える挙動の変更が PRODUCT.md に書かれていない**(CLAUDE.md の「要件と設計の2ファイル」と、自律判断の層2)
   - 次の3つは、`DESIGN.md:227-229` にしか書かれていません。
     - 新しい文言 `could not open the workbench screen` と `could not create the workbench guide`(`src/cli/workbench.ts:25,34`)
     - `Press any key to close.`(`src/cli/workbench.ts:57`)
     - 案内のプログラムが終わったときに5回まで起動し直すこと
   - `PRODUCT.md:490` と受け入れシナリオ59(`:771`)は、失敗したときの文言と終了コードを要件として決めています。新しい失敗の場合も、そこに並べる必要があります。
   - 利用者に二択で確認したかどうかは、コミットからは読めません。
2. **契約 docs の更新漏れ**(CLAUDE.md の「昇格済みモジュール」)
   - `docs/lib/tmux.md:10` は、頼みごとの形を `key`、`focus`、`agentview` の3つに限っています。新しい `guide`(`src/ops/names.ts:12`)が入っていません。これは私も手元で確かめました。
3. **decision-log の issue があるか確かめられていない**
   - `ensureGuide` を一覧の側ではなく、つなぐ側に置いた判断は、層1の decision-log に当たります。`gh` が失敗したため、issue があるかは確かめられていません。

**smell(どれも判断事項)**

- **Duplicated Code / Shotgun Surgery**: `src/cli/workbench.ts:43-51` の `askListToRefreshGuide` は、lib にある頼みごとの約束を src の側で書き直しています。
  - 約束とは「`@wn_req_<秒>_<pid>` に書いてから SIGUSR2 を送る」ことで、lib では `lib/tmux/tmux.ts:26-30` と `signalGuide`(`:399-405`)にあります。
  - このままでは約束が lib と src の2箇所に分かれます。`Tmux.request(line)` のような口を lib に置き、契約に書くのが自然です。
- **Repeated Switches / Primitive Obsession**: `src/ops/app.ts:1156-1173` では、`GUIDE_REFRESH` だけが定数で、`'agentview'`、`'focus'`、`'key'` は文字列のまま比べています。
- **Duplicated Code(軽微)**: `src/cli/list.ts:66-67` は、`ensureGuide` の直後に `workbenchOptions(GUIDE, '')` を呼んでいます。案内を作り直したときは、`ensureGuide` の中(`guide.ts:22`)でも呼ぶので2回になります。
- **Mysterious Name**: `src/cli/workbench.ts:52` の `fail()` は、Ghostty の分割から起動したときにキーを待つ処理ですが、名前からはそれが読めません。
- **テストの脆さ(参考)**: `lib/tmux/tmux.test.ts:76` は、`lastIndexOf('*)')` で sh の本文を字面で切り出しています。case の並びが変わると、何も言わずに中身がずれます。

**妥当な点**

- `exec` を付ける場所を `splitWorkbench` の1箇所に寄せたのは、筋が通っています。bash、zsh、sh で実際に走らせる単体テストもあります。
- lib を変えたときに、契約 docs とテストも一緒に更新しています。依存は src から lib への一方向を保っています。

## Spec

**(b) 求められていない挙動**

1. **案内のセッションの中のペインを、どれも起動し直してしまう**
   - `lib/tmux/tmux.ts:50-61` の `${GUIDE})` の分岐は、ペインを区別せずに `respawn-pane` します。私もコードを見て確かめました。
   - 案内のセッションには prefix `C-q` が入っています(`lib/tmux/tmux.ts:126`)。そのため、作業台の画面に案内が出ているときに `ctrl+q c` を押すと、wbguide に新しいウィンドウができます。そこで `exit` しても、シェルが5回まで出直します。
   - これは `PRODUCT.md:486` の「`exit` で作業台を片付けたつもりなのに、新しいシェルが出直して閉じられなくなるのを避ける」に反します。前は kill-pane で閉じていたので、退行です。起動し直すのは、案内のプログラムのペインだけにする必要があります。
2. **新しい文言、キー待ち、自動で起動し直すことが PRODUCT.md にない**(Standards の1と同じ指摘です)
   - Ghostty の分割では、「not running」のときもキーを待つようになりました。`PRODUCT.md:490` に書かれた挙動も変わっています。
   - 新しい e2e テスト(`test/e2e/workbench.test.ts:230-256`)も、DESIGN.md の「確かめ方」の対応表に載っていません。

**(c) 実装が意図とずれていそうな点**

3. **起動し直した回数を戻す処理がない**
   - `@wn_respawned` を戻す処理がありません(`lib/tmux/tmux.ts:52-56`)。これも私が確かめました。
   - 目的は「起動してすぐ終わるときに回り続けないため」ですが、実装は「ペインが生きている間に通算5回」です。間をあけて5回落ちただけで、案内は畳まれます。
   - そのとき作業台の画面が wbguide を映していれば、`detach-on-destroy on` によって、エラーも出さずに閉じる見込みです(実機では確かめていません)。
4. **端末の分割を閉じたことと、つなげなかったことを見分けられない**
   - 判定は `res.status !== 0 && hasSession(LIST)` です(`src/cli/workbench.ts:33`)。
   - 利用者が端末の分割を閉じて tmux が0以外で終わった場合も、「つなげなかった」と扱い、もうない端末にエラーを書きます。実害はおそらく小さいです。

**(a) 欠けている要件**

- `ensureGuide` が作り直した案内は、workbench の側の環境と `node`/`cli` で起動します(`src/cli/guide.ts:20`)。そのため、一覧と版や環境が違う案内になりえます。このことは docs に書かれていません。
- exec の付け方と、ensureGuide を同時に作ろうとしたときの扱いは、正しいと判断しました。

---

指摘は Standards が8件(規約3件、smell 5件)、Spec が6件です。軸ごとに最も重いのは、次の2つです。
- **Standards**: 利用者から見える挙動の変更が PRODUCT.md に書かれず、利用者への確認も読み取れないこと。
- **Spec**: 案内のセッションの中のどのペインも起動し直すため、`ctrl+q c` で開いたシェルを `exit` で閉じられないこと。

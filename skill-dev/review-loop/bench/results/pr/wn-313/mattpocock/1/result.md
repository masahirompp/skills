2つのレビュー(規約の軸と仕様の軸)を並列で走らせています。終わり次第まとめます。

仕様の軸のレビューが届きました。規約の軸はまだ実行中なので、届いてからまとめて報告します。

PR #2 のレビューを、規約の軸と仕様の軸に分けて並べます。対象は `main...HEAD` の差分(コミット d212b82、13ファイル、+177/−15)で、仕様は issue #1 と PR の本文です。どちらのレビューも読むだけで、作業ツリーとブランチは変えていません。

## Standards(規約)

**文書化された規約への違反**

1. **`docs/lib/tmux.md` の「名前の約束」が古いまま**(根拠は `docs/lib/README.md`「振る舞いを変えるときは…この契約を直し」)
   - 頼みごとの形の一覧(`key` / `focus` / `agentview`)に、新しい `guide` が入っていません。
   - 新しいオプションも書かれていません。`@wn_guide_died` は serverConfig の項にしか出ず、`@wn_respawned` は契約のどこにもありません。
2. **観測できる挙動が PRODUCT.md に書かれていない**(根拠は CLAUDE.md の自律判断の層2と、PRODUCT/DESIGN の境界)
   - 「Press any key to close.」とキーを待つ動き、新しいエラー文言2つは DESIGN.md にしか書かれていません。
   - PRODUCT.md の490行とシナリオ59は「示して終了コード 1」のままです。Ghostty の分割から起動したときにキーを待つようになった今の挙動と合いません。
   - 利用者に二択で確かめた記録が見当たりません。
3. **学びの捕捉**(根拠は CLAUDE.md「学びの捕捉」)
   - DESIGN.md に「なぜ終わったかは、まだ分かっていない」とありますが、issue を参照していません。対応する issue #1 には、ラベルもマイルストーンも付いていません。
   - 実測で分かった罠が2つ、working-with-tmux スキルに足されていません。`exec exec` が bash で失敗することと、案内のペインが `*)` の分岐で `kill-pane` されることです。

**baseline の smell(すべて判断の問題)**

- **possible Duplicated Code**: `src/cli/workbench.ts` の `askListToRefreshGuide` は、`src/cli/guide.ts` 74〜80行と同じ手順です(`@wn_req_…` に書き、`@wn_pid` を読み、SIGUSR2 を送る)。lib の `@wn_req_sh` と同じ処理を TS で作り直してもいます。`@wn_pid` も文字列のまま3か所にあります。
- **possible Duplicated Code(小)**: `list.ts` は `ensureGuide` の直後に `workbenchOptions(GUIDE, '')` を呼びます。`ensureGuide` も作ったときに同じものを呼ぶので、作った場合は2回走ります。害はありませんが、どちらの受け持ちかが読み取れません。
- **possible Primitive Obsession / Repeated Switches**: 定数になったのは `GUIDE_REFRESH = 'guide'` だけです。ほかの頼みごとの種類は app.ts に文字列で直接書かれ、`parts[0] ===` の if がつながっています。DESIGN.md 214行が戒めている足し忘れ(サイクル6)がまた起きえます。
- **possible Feature Envy(軽)**: `fail()` は `process.env.WHATNEXT_WORKBENCH_SPLIT` を直接読んでいます。ほかの `WHATNEXT_*` は `env.ts` の `readEnv` を通ります。
- **テストの脆さ**: `lib/tmux/tmux.test.ts` は sh の本文を `indexOf` / `lastIndexOf('*)')` で切り出し、文字列の断片で確かめています。lib のテストは次のサイクルに持ち越すものなので、振る舞いは e2e に任せ、ここは `sh -n` の文法チェックに絞る手もあります。
- **possible Mysterious Name(軽)**: `test/unit/cli.test.ts` が確かめているのは `workbenchCommand` と `splitWorkbench` の組み合わせだけで、ファイル名のほうが中身より広いです。

**規約に合っている点**: `lib/` から `src/` への import はなく、依存は一方向のままです。`exec` を付ける側を1か所にした理由も、ports.ts と DESIGN.md の両方に書かれています。

## Spec(仕様)

**(a) 欠けている・部分的な要件**

1. **PRODUCT.md が更新されていない。** 利用者に見える新しい挙動が3つあります。
   - `whatnext: could not open the workbench screen ...` の表示
   - `Press any key to close.` の表示とキー待ち
   - 案内のセッションが落ちても残り、起動し直す

   PRODUCT.md は表示の文言まで要件に書く方針です(490行、78行)。文言とキー待ちは層2に当たりますが、利用者に確かめたかどうかは差分からは読めません。
2. Ghostty の分割から起動したときのキー待ちを確かめるテストがありません。e2e は `WHATNEXT_WORKBENCH_SPLIT` を渡していません。

**(b) 求められていない振る舞い**

3. `whatnext is not running` の経路も `fail()` を通るようになり、分割から起動したときはキーを待ちます。PR の本文がキー待ちの対象にしているのは「attach が失敗したとき」だけです。シナリオ59から見ると、キー待ちが増えた形です。
4. attach が0以外で終わり、一覧も消えていた場合(サーバごと閉じた場合)の終了コードが、`res.status` から 0 に変わりました。どの仕様にも書かれていません。

**(c) 実装が誤っていそうな点**

5. **`ensureGuide` は `whatnext workbench` を呼んだ側の環境で案内を作ります。** PATH、`CLAUDE_CONFIG_DIR`、`env.cli` などがそのまま入ります。一覧と違う版の whatnext や、違う設定のディレクトリから手で実行すると、案内のプログラムが一覧と別物になりえます。
6. **起動し直しの回数が戻りません。** `@wn_respawned` はペインのオプションで、`respawn-pane` の後も残ります。そのため「5回まで」は寿命全体の通算になり、長く動かすうちに散発的な異常終了が5回たまると畳まれます。DESIGN.md が挙げる理由(起動してすぐ終わるときに回り続けないため)に合わせるなら、時間で区切るほうが合います。
7. **attach 失敗の判定が誤りうる場面が2つあります(どちらも実測が必要)。**
   - 分割を閉じた SIGHUP で `res.status` が null になると、一覧があればエラーを出してキー待ちに入ります。
   - 案内が6回目に `kill-pane` され、つないでいたクライアントが離れると、tmux の終了コードによっては「could not open」と出ます。

**問題なしと確かめた点**

- `exec` の重複は解消しています。bash・zsh・sh の単体テストも通ります。
- 案内を同時に作ろうとしても壊れません(`new-session` が失敗した後に `hasSession` を確かめている)。
- sh のクォートは正しく、フックの `sleep 1` は `run-shell -b` の中なのでサーバを止めません。

---

**まとめ**: 規約の軸は違反3件と smell 6件で、最も重いのは lib の契約 docs(`docs/lib/tmux.md`)に新しい頼みごととオプションが反映されていないことです。仕様の軸は7件で、最も重いのは利用者に見える新しい挙動(文言とキー待ち)が PRODUCT.md になく、層2で利用者に確かめた形跡がないことです。

PRODUCT.md への反映は、両方の軸が別々に指摘しています。私の見立てでは、マージ前に PRODUCT.md を直すのが妥当です。この挙動はバグの修正ですが、利用者が目にする文言とキー待ちが新しく加わります。PRODUCT.md は文言まで要件として持つ方針なので、そこが古いままだと次のサイクルが docs から作り直すときにこの挙動が消えます。

判断が要るのは主に次の2つです。

- **起動し直しの回数(仕様の6)**: 「寿命全体で5回」と「短い時間に続けて落ちたら止める」のどちらが欲しいか。ここで決まれば層2の二択として片づきます。
- **`ensureGuide` が使う環境(仕様の5)**: 手で `whatnext workbench` を実行する場面が実際にどれくらいあるか。ほとんどなければ、注意書きだけで足ります。

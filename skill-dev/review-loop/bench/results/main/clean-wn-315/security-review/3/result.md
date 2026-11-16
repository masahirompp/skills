# セキュリティレビュー結果: `main...new-session-repo-first`

この差分には、確信度 8 以上で報告すべき脆弱性はありませんでした。候補が 0 件だったため、誤検知を除く手順(手順 2)は行っていません。

## 対象

- `src/ops/app.ts:853`: 一覧で `n` を押したとき、`openNew()` の代わりに `openNew(undefined, this.error ? undefined : sid)` を呼ぶ。
- `docs/PRODUCT.md` と `test/e2e/ops.test.ts` も変わっていますが、ドキュメントとテストは除外条件に当たるので対象外です。

## 該当なしとした根拠

1. **候補の値は増えず、並び順が変わるだけ**
   - `openNew` の中の `rootOfSid(sid)` は、`this.p.locations.get(r.cwd)?.root ?? r.cwd` を返します。
   - 変更前から、全行の同じ値が候補に入っていました。新しいパスが候補に加わるわけではありません。
2. **新しい経路ではない**
   - `ctrl+q ctrl+n` の処理(`src/ops/app.ts:1260`)は、変更前から同じ `openNew(undefined, sid)` を呼んでいます。
3. **パスはシェルを通らない**
   - 子プロセスは `lib/input/exec.ts` の `execFile(cmd, args[], {cwd})` で起動します。引数は配列で渡り、`shell` は使いません。
   - 選ばれたディレクトリは、`claude --bg` を起動するときの `cwd` オプションに入るだけです。コマンドの文字列には入りません。
4. **信頼の境界をまたがない**
   - パスの出どころは、利用者自身の環境にある `claude agents --json` と `git` です。
   - 使われるのは、利用者が候補を選んで `Enter` で確定したときだけです。そのため、コマンドインジェクションもパストラバーサルも成り立ちません。

# セキュリティレビューの結果: `main...HEAD`

信頼度 8 以上の脆弱性は見つかりませんでした。

## 確かめたこと

- **変更の中身**（`src/ops/app.ts:853`）: 一覧で `n` を押すと、`this.openNew(undefined, this.error ? undefined : sid)` を呼ぶようになった。
- **sid の使われ方**: `openNew` は `rootOfSid(sid)` を呼ぶ。`rootOfSid` は、`claude agents --json` から作ったメモリ上の `this.rows` で sid を引き、git の解決で計算済みの値（`locations.get(r.cwd)?.root ?? r.cwd`）を返すだけである。新しい git の呼び出しや子プロセスの起動は増えていない。
- **候補に入る値**: 同じ値は、変更前から全行のループで候補の一覧に入っていた。今回の変更は、その1つを先頭に移すだけである。
- **選んだパスの渡し方**: `startSession` は `this.p.run('claude', ['--bg', ...], {cwd: dir})` のように、パスを `cwd` オプションで渡す。引数（argv）には入れないので、`-` で始まるパスがフラグとして読まれることはない。`run` は、シェルを通さず引数の配列で起動する形である。
- **経路は前からあった**: main でも `ctrl+q ctrl+n` が `this.openNew(undefined, sid)` を呼んでおり、この経路は今回の差分より前から使われていた。
- **対象外**: `docs/PRODUCT.md` はドキュメント、`test/e2e/ops.test.ts` はテストのみのファイルなので、除外の基準に従って見ていない。

この差分で入りうる問題の信頼度は 2/10 未満と見積もりました。報告の基準（8 以上）に届かないので、報告する指摘はありません。

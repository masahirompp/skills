**証明できた指摘はありません。**

差分の中身は `src/ops/app.ts:853` の1行です。一覧で `n` を押すと `openNew(undefined, this.error ? undefined : sid)` を呼びます。これに加えて PRODUCT.md の文言と e2e テストが1件あります。壊れそうな場面を3つ選び、実際に動かして確かめました。3つとも、出るべき出力のとおりでした。

## 実際に動かした場面

使ったのは `scratch/n-head.test.ts` です。既存の `test/e2e/harness.ts`(外側の tmux と偽の claude)を使い、次のコマンドで走らせました。

```
npx vitest run --root . scratch/n-head.test.ts --no-file-parallelism --testTimeout 60000
```
```
 Test Files  1 passed (1)
      Tests  3 passed (3)
```

| 場面 | 出るべき出力(変更の意図) | 結果 |
|---|---|---|
| カーソルが worktree(`lib/.claude/worktrees/fix`)の行にある | 候補の先頭は元のリポジトリの `> lib` | 一致 |
| カーソルが git でない場所にある `(tty)` の行にある | 候補の先頭はその場所の `> elsewhere` | 一致 |
| `--json` の読み込みエラーのあと、`r` で読めるようになってから `n` を押す | エラーが消えたので、先頭はまたカーソルの行のリポジトリ `> lib` | 一致 |

既存のチェックもすべて通りました。
- `npm test`: 119 件すべて通過
- `test/e2e/ops.test.ts`: 14 件すべて通過(追加された「8: 一覧の n では…」を含む)
- `npm run check`: 通過

## コードを読んで、実行せずに除いた候補

- **行が一覧から消えて、カーソルが勝手に移った直後の `n`**: 2秒間の守りは `Ctrl+X` だけにかかり、`n` にはかかりません。ただ `n` は候補を出すだけで、何かを壊す操作ではありません。仕様にも反していません。
- **カーソルの行が全部消えたとき**: `followCursor` は選べる行がなければ `undefined` を返します。`rootOfSid` も、行が見つからなければ `undefined` を返します。どちらの場合も、起動したディレクトリが先頭になります。
- **`refreshGuidePath` の中のずれ**: 行の `cwd` を書き換えてから `locations.refresh` を待つまでの間に `n` を押すと、worktree のパスが先頭になりうるとコードからは読めます。ただ、この窓は git の応答の間だけと短く、再現できていません。

途中で作った `scratch/` は消しました。残すと `npm run check` が書式のエラーで落ちるためです。作業ツリーは元のとおり clean です。

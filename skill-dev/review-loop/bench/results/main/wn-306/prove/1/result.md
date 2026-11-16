証明できた指摘は2件です。どちらも `src/screen/screen.ts` の `render` に、今回加わった「選んだ行と一緒に窓に入れる範囲(cursorBlock)を (sub) の行まで広げる」処理が原因です。同じスクリプトを main の `screen.ts` で走らせると、2件とも通ります。つまり、この変更で入った後退です。

再現スクリプトは `scratch/break.test.ts` です。main 版との比較用に `scratch/break-main.test.ts` と、main から取り出した `scratch/mainsrc/` も置いてあります。

---

## 1. メモの入力欄と選んだ行が、下に続く (sub) の行に押し出されて窓から消える

**状況:** 選べる行 `p` の下に、入れ子の (sub) の行が12行続きます。端末の高さは12行です。`p` で `e` を押し、メモの入力欄を開いています(`inline`)。

**原因:** cursorBlock の終わりが、最後の (sub) の行まで伸びます。そこへ既存の「入力欄は最後の行まで窓に入れる」(`start = b1 - avail`)が効き、窓が (sub) の行の末尾に合わさります。

**実行したコマンド**
```
npx vitest run scratch/break.test.ts
```

**出力(テスト A の部分)**
```
stdout | scratch/break.test.ts > A: メモの入力欄が、下に続く (sub) の行に押し出されて窓から消える
  SESSION      STATUS  WHERE  CTX      AGE
  ├ w3 (sub)   Review           -        -
  ├ w4 (sub)   Review           -        -
  ├ w5 (sub)   Review           -        -
  ├ w6 (sub)   Review           -        -
  ├ w7 (sub)   Review           -        -
  ├ w8 (sub)   Review           -        -
  ├ w9 (sub)   Review           -        -
  ├ w10 (sub)  Review           -        -
  └ w11 (sub)  Review           -        -
6/6
k
...
   × A: メモの入力欄が、下に続く (sub) の行に押し出されて窓から消える 15ms
AssertionError: expected false to be true // Object.is equality
 ❯ scratch/break.test.ts:19:48
     19|   expect(lines.some(l => l.startsWith('> p'))).toBe(true);
```

**出るべきだった出力:** 選んだ行 `> p` と、入力中のメモの行 `note: INPUT▏` が窓に入ること。PRODUCT.md シナリオ 24 では「選んだ行が見えるように一覧がスクロール」し、下に続く (sub) の行は「選んだ行と一緒に見える」ものです。(sub) の行を見せるために、選んだ行や入力欄を窓の外へ出すことは求めていません。main の `screen.ts` では、このテストは通ります。

---

## 2. 最初の選べる行より上に (sub) の行が多いと、選んだ行が窓に入らない

**状況:** 先頭の区切り `aaa` には、起動元が一覧に出ていないトップレベルの (sub) の行が12行だけ並びます。次の区切り `bbb` の `s0` を選んでいます。端末の高さは10行です。

**原因:** `rowIndex.length === 1 ? 0 : start` により、cursorBlock が一覧の先頭(0)から始まります。cursorBlock の長さが窓の高さを超えると、窓は `start = b0 = 0` に固定され、`s0` まで届きません。

**実行したコマンド**
```
npx vitest run scratch/break.test.ts
```

**出力(テスト B の部分)**
```
stdout | scratch/break.test.ts > B: 最初の選べる行の上に (sub) の行が多いと、選んだ行が窓に入らない
  SESSION    STATUS  WHERE  CTX      AGE
── aaa ─────────────────────────────────────────────────────
  w0 (sub)   Review           -        -
  w1 (sub)   Review           -        -
  w2 (sub)   Review           -        -
  w3 (sub)   Review           -        -
  w4 (sub)   Review           -        -
  w5 (sub)   Review           -        -
1/2
k
...
   × B: 最初の選べる行の上に (sub) の行が多いと、選んだ行が窓に入らない 0ms
AssertionError: expected false to be true // Object.is equality
 ❯ scratch/break.test.ts:30:49
     30|   expect(lines.some(l => l.startsWith('> s0'))).toBe(true);
```

**出るべきだった出力:** `> s0` を含む窓(`1/2` を伴う)。`1/2` と出ているのにその行が見えず、`↑` で上に戻ることもできません(`s0` は最初の選べる行)。この状態では、`s0` を窓に入れる手段がありません。PRODUCT.md の「最初の選べる行を選んでいるときは、一覧の先頭から見せる」は、選べない行を見落とさないための規則です。選んだ行を窓の外に出すことまでは求めていないと読めます。

---

**main との比較(2件が後退であることの確認)**

**実行したコマンド**
```
npx vitest run scratch/break-main.test.ts
```

**出力**
```
 Test Files  1 passed (1)
      Tests  2 passed (2)
```

### 確かめていないこと
- 2件とも `render` に直接入力を渡した再現です。実際の `claude agents --json` から、この並び(全部が (sub) の区切りが先頭に来る、など)が出るかは、tmux の実機では確かめていません。ただし、このブランチが足した単体テストも、最初の選べる行の上に (sub) の行を置いており、作者はこの並びがありうると見ています。
- 1件目は、(sub) の行の数(12)が窓の高さより多いときの再現です。オーケストレーションで `claude -p` を日に何本も起動する使い方では、ありうる数です。

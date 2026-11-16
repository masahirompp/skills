対象は `git diff main...HEAD`(コミット d212b82 の1件、13ファイル)です。コミットに issue の番号がないので、Spec 軸の仕様はコミットメッセージの4つの箇条と `docs/PRODUCT.md`、`docs/DESIGN.md`、`docs/lib/tmux.md` にしました。

2つの軸とも読み取りだけで、テスト、biome、tmux の実機は動かしていません。Spec 1・2・7 と Standards 1 は、私も差分を読んで確かめました。

## Standards

**文書にある規約への違反**

1. **観測できる挙動が変わったのに `docs/PRODUCT.md` が未更新(硬い違反寄り)** — `src/cli/workbench.ts:23-36, 56-64`
   - 標準エラーの文言が3つ増え、キー待ちが加わり、終了コードも変わっています。
   - `CLAUDE.md` は PRODUCT.md を「観測できる振る舞い」の置き場所とし、層2の変更に人間へのエスカレーションを求めています。
   - 書かれているのは DESIGN.md だけです。エスカレーションがあったかは、コミットメッセージからは分かりません。
2. **`docs/lib/tmux.md:10` の頼みごとの列挙に `guide` がない(判断)**
   - 列挙は `key`/`focus`/`agentview` のままで、新しい形は `src/ops/names.ts:12` と DESIGN.md にだけあります。
   - 列挙の主語は「キーとフック」なので、契約の外とも読めます。
   - ペインのオプション `@wn_respawned`(`lib/tmux/tmux.ts:52`)も契約に名前がありません(軽微)。
3. **`lib/tmux/tmux.test.ts:77-81` が sh の本文を `toContain` で照合している(判断)**
   - `docs/DESIGN.md:260` の「テストは外から観測できる振る舞いだけを対象にする」に沿いません。
   - 「5回で畳む」を守っているのは、この文字列の照合だけです。
   - ADR-0021 が tmux について受け入れた費用の範囲内とも言えます。

**匂い(すべて判断)**

- **Duplicated Code**: `src/cli/workbench.ts:43-50` の `askListToRefreshGuide` は、`src/cli/guide.ts:74-80` と同じ形です(`@wn_req_<秒>_<pid>` を書き、`@wn_pid` を読み、SIGUSR2 を送る)。「一覧に頼む」を1つの関数にまとめられます。
- **Duplicated Code**: `src/cli/list.ts:66-67` は、`ensureGuide` が作ったときに済ませた `workbenchOptions(GUIDE, '')` を直後にもう一度呼びます。
- **Primitive Obsession**: `'WHATNEXT_WORKBENCH_SPLIT'` が `src/ops/app.ts:1444` と `src/cli/workbench.ts:57` に生の文字列で2か所あります。共有する名前の置き場所は `src/ops/names.ts` です(`docs/DESIGN.md:43`)。
- **Mysterious Name**: `fail()`(`src/cli/workbench.ts:56`)は、キーを待つ副作用が名前に出ていません。
- **Shotgun Surgery の可能性**: `ensureGuide` が案内のプログラムのファイル `src/cli/guide.ts:17` にあり、`list.ts` と `workbench.ts` が案内の描画ごと import します。

**妥当な点**

- 依存方向は守られています(`lib/` から `src/` への import はありません)。
- lib の挙動の変更に、契約、DESIGN.md、lib 横のテストが同じコミットで付いています。
- `exec` を `splitWorkbench` の1か所に寄せ、bash/zsh/sh で実際に動かすテストがあります。

## Spec

**正しく実装されている箇条**

- **箇条2(ensureGuide)**: `src/cli/guide.ts:17-24`、`src/cli/workbench.ts:21-27`。同時に作ったときは `hasSession` の再確認で `exists` に落ちます。e2e は名前が入り直すところまで確かめています。
- **箇条4(exec)**: 付けるのは `lib/tmux/ghostty.ts:41` だけで、呼び出しも `src/ops/app.ts:1440` の1か所です。
- **箇条3の条件**: 終了コード 1 で、キー待ちは `WHATNEXT_WORKBENCH_SPLIT=1` かつ TTY のときだけです。DESIGN.md の記述どおりです。
- `sh-*` と、案内以外のセッションの `pane-died` は変わっていません。

**(c) 実装が怪しい**

1. **案内のセッションに足したペインも起動し直される** — `lib/tmux/tmux.ts:49-60`
   - 分岐はセッション名 `wbguide` だけで決まり、案内のプログラムのペインかどうかは見ていません。
   - 案内にも `ctrl+q` の prefix が入るので、そこで分割して作ったシェルを `exit` すると、閉じずに5回出直し、`@wn_guide_died` も上書きするはずです。0.20.2 では `kill-pane` でした。
   - DESIGN.md は「案内のセッションのペインが終わったとき（案内のプログラムが落ちたとき）」と書いています。実機では確かめていません。
2. **5回の数え方が、書いてある理由と合わない** — `lib/tmux/tmux.ts:52-56`
   - `@wn_respawned` は増えるだけで戻りません。
   - `docs/lib/tmux.md` の理由は「起動してすぐ終わるときに回り続けないため」ですが、実装は何日あいても通算6回目で畳みます。
   - そのとき作業台の画面が案内を映していれば、画面ごと閉じます。次の `whatnext workbench` で作り直せるので、塞がりはしません。

**(a) 不足・部分的**

3. **箇条3と上限にテストがない**
   - attach 失敗時の文言、行を消さないこと、キー待ちを確かめるテストがありません。
   - 上限は、文字列 `-lt 5` を含むかを見るだけです。

**(b) PRODUCT.md にない観測可能な挙動**

4. 標準エラーの新しい文言が3つあります(`src/cli/workbench.ts:24,34,58`)。
   - `whatnext: could not open the workbench screen …`
   - `whatnext: could not create the workbench guide …`
   - `Press any key to close.`
5. PRODUCT.md 490行の「`whatnext is not running. Start whatnext first.` と示して終了する（終了コード 1）」に、Ghostty の分割ではキー待ちが挟まります(`src/cli/workbench.ts:14`)。
6. **終了コードが変わった** — `src/cli/workbench.ts:40`
   - 以前は `res.status` をそのまま返していましたが、今は whatnext の終了でサーバごと閉じたときに 0 を返します。コミットメッセージにも docs にもありません。
   - このとき tmux が 0 以外で終わるという DESIGN.md の前提は、実機で確かめていません。
7. **`docs/lib/tmux.md:43` の `splitWorkbench` が「`command` を打ち込む」のまま**
   - 先頭に ` exec ` を付けることは DESIGN.md にしか書かれていません。
   - 実装セッションは契約 docs だけを読む決まりなので、今回直した exec の重複が同じ経路で再発しえます。

## まとめ

Standards は違反3件と匂い5件で、最も重いのは PRODUCT.md を更新せずに観測できる挙動(文言、キー待ち、終了コード)を変えた点です。Spec は7件で、最も重いのは `pane-died` の分岐がセッション名だけで決まり、案内のプログラム以外のペインまで起動し直す点です。

マージ前に決めることが2つあります。

- **層2の扱い**: 文言、キー待ち、終了コードの変更を PRODUCT.md に書くかどうかは、利用者の判断です。不具合修正に伴うエラー表示なので挙動は妥当だと考えますが、決まりの上では事後でも確認が要ります。
- **5回の上限**: 「通算5回」のままにするか、「短い間に続けて5回」にするか。後者なら回数を戻す仕掛け(時刻を持つなど)が要ります。案内のプログラムが終わる原因はまだ分かっていないので、通算のままだと長く動かすうちに上限に届きます。

Spec 7 は1行の追記で済み、再発を防ぐ効果が大きいので、先に直すことを勧めます。

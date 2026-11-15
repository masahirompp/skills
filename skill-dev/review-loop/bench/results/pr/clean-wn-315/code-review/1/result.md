`git diff main...HEAD` で 1 コミット(0e0a6a8)、3 ファイルを見ました。指摘は 5 件です。重いバグは見つかっていません。正しさに関わるのは 1 件目だけで、残りはテストの抜け、整理、docs の確認です。検証の段は回していないので、どれも「ありうる」の水準です。

5 findings, most severe first:

1. `src/ops/app.ts:853`: カーソルのある行の cwd がもう無いと(worktree を消したあとの停止済みの行など)、無いパスが候補の先頭に入って選ばれた状態になる。`Enter` 2回でそのまま `claude --bg` を無い cwd で起動しようとする。

   Failure scenario: 停止したセッション X の worktree を git worktree remove で消す。locate は realpath も git も失敗し、root=cwd(無いパス)を返す(Locations は前回の値を1回だけ使い、そのあとこの値に替わる)。一覧で X にカーソルを置いて n → Enter → Enter と押すと、startSession(無いパス) が spawn の ENOENT で失敗し、'claude --bg did not start a session' の画面になる。変更前は必ずある起動ディレクトリが先頭だったので、既定の手順では起きなかった。rootOfSid の結果を statSync で確かめ、無ければ pref にしないとよい。

2. `docs/PRODUCT.md:513`: 「ctrl+q ctrl+n は --json を読めずにエラーを出している間も、いたセッションのリポジトリを先頭にする」という仕様を新しく書いたが、確かめるテストがない。

   Failure scenario: test/e2e/ops.test.ts の 54・55 のテストはエラーでない場合しか見ていない。あとで listKey と同じように attachKey にも this.error の判定を足すと、文書と違う挙動になっても e2e が通ってしまう。agentsFail の状態で C-q C-n を押し、先頭がいたセッションのリポジトリになることを確かめる段をテストに足すべき。

3. `src/ops/app.ts:951`: openNew のループで、this.p.locations.get(r.cwd)?.root ?? r.cwd を手で書いている。同じことをする rootOfSid がすぐ下にあり、463 行目にも同じ式がある。

   Failure scenario: リポジトリへの寄せ方(submodule、git でない場所の扱いなど)を変えるとき、3か所を揃えて直す必要がある。候補の先頭(rootOfSid)と2番目以降(ループ)で寄せ方がずれると、同じリポジトリが重複して残る。ループを rootOfSid か共通の関数に寄せるとよい。

4. `src/ops/app.ts:943`: openNew(waitFor?, preferredFrom?) は2つの引数を pref = waitFor ?? preferredFrom にまとめるだけで、今回の変更で preferredFrom を渡す呼び出しが増えた。

   Failure scenario: どの呼び出しも『先頭にするセッション』を1つ渡しているだけなのに、呼ぶ側は openNew(undefined, sid) のように undefined を並べている。waitFor と preferredFrom を両方渡すと preferredFrom は黙って無視される。'先頭にする sid' と '待ち先の関係を結ぶか' を {from, link} のように1つの引数にまとめれば、取り違えが起きない。

5. `docs/PRODUCT.md:591`: 決定の日付が「2026-11-02、利用者の判断」になっているが、コミット日(2026-11-15)と合わない。2026-11-02 は直前の別の作業(#313)の日付で、それを写した可能性がある。

   Failure scenario: PRODUCT.md は永続層で、日付は経緯をたどる手がかりになる。日付が違っていると、11-02 の作業台の案内の修正と同じ流れで決めたように読め、判断の経緯を追い違える。実際に決めた日を利用者に確かめて直すべき(正しい日なら問題はない)。

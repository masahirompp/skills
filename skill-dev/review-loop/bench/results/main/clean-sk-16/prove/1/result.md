テストの完了を待っています。終わると通知が届きます。

## 結果: 証明できた指摘なし

この差分で実際に動くコードは2か所だけです。判定役に渡す `JUDGE_PROMPT` に2段落と2つの欄(範囲・再現)を足したことと、偽の claude が返す判定に同じ2行を足したことです。残りは `SKILL.md` の文章です。動くコードについて、次の3つを実行して確かめましたが、壊れる箇所は見つかりませんでした。

1. **プロンプトの組み立てが壊れていないか**: 足した文に `{` や `}` が入っていると、`JUDGE_PROMPT.format(pr=...)` が例外を出すか、文が欠けます。
   ```
   cd skills/review-loop/scripts && python3 -I -c "
   import importlib.util,sys
   s=importlib.util.spec_from_file_location('rl','review_loop.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
   t=m.JUDGE_PROMPT.format(pr=7);print('ok',len(t),'{' in t,'}' in t)
   import re;print([l for l in t.splitlines() if l.startswith('## ')])
   "
   ```
   ```
   ok 2322 False False
   ['## 指摘', '## 競合']
   ```
   展開は成功し、中括弧も残っていません。スクリプトは判定の抽出で行頭の `## 指摘` と `## 競合` を探します(`VERDICT_SECTIONS`、`review_loop.py:839`)。足した文はこの2つの見出しを増やしていないので、抽出の結果も変わりません。

2. **既存のテスト一式**: `python3 skill-dev/review-loop/test.py` は最後に `全て成功` を出し、終了コード 0 でした。

3. **抽出の処理(`review_loop.py:940-963`)**: 読んだ範囲では、新しい欄の中身で挙動が変わる経路は見当たりませんでした。ただ、これを実行で崩す入力は組めていません。たとえば「再現」の欄の手順の中に、行頭が `## 競合` の行が入る場合です。組めていないので指摘には入れていません。

`SKILL.md` に足した運用の規則(再現を採用の条件にする、差分の外を分ける、再レビューの条件を絞る)は、どれも親の振る舞いを決める文章です。実行では正しさも誤りも示せないので、今回の条件に従って指摘から外しています。コミットメッセージの「確かめていないこと」にある2点、つまり反復が実際に減るかと、判定役が範囲を正しく見分けられるかも同じです。どちらも実際の PR でループを回さないと確かめられず、今回は確かめていません。

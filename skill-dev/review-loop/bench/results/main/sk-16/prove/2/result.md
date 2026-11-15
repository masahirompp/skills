**証明できた指摘はありません。**

## 差分で実行できるところ

差分は3ファイルです。
- `skills/review-loop/SKILL.md`:手順の文書なので、実行では確かめられません。
- `skills/review-loop/scripts/review_loop.py`:判定役に渡すプロンプト `JUDGE_PROMPT` に文を足しています。
- `skill-dev/review-loop/fakes/claude`:テスト用の偽の claude で、返す判定に「範囲」「再現」の欄を足しています。

スクリプトが判定の中身で確かめるのは、`VERDICT_SECTIONS = ("## 指摘", "## 競合")` の2つの見出しだけです(`review_loop.py:839`)。新しい欄を読むコードは無いので、挙動が変わりうるのは次の2点だけです。

1. `JUDGE_PROMPT.format(pr=...)` が、足した文の中の波括弧で壊れないか
2. 偽の判定の形を変えたことで、既存のテストが壊れないか

## 実行したこと

**1. format の結果**
```
python3 -I -c "
import sys; sys.dont_write_bytecode=True; sys.path.insert(0,'skills/review-loop/scripts')
import review_loop as r
s=r.JUDGE_PROMPT.format(pr=42)
print('{' in s, '}' in s, s.count('範囲'), s.count('再現'))
"
```
```
False False 6 2
```
例外は出ず、波括弧も残っていません。足した欄はプロンプトに入っています。

**2. 既存のテスト**
```
cd skill-dev/review-loop && timeout 600 python3 test.py 2>&1 | tail -15
```
```
...
ok    観点の指定の誤りは状態に記録しない

全て成功
```

## 実行では確かめられない範囲

この変更の中身は、ほぼ LLM への指示の文です。判定役が「範囲」や「再現」を正しく書くか、親が再現の手順を守るか、`gh issue create` を尋ねずに実行しないかは、実際の LLM で動かさないと分かりません。「実行で証明したものだけ」という条件に合わないので、この範囲の指摘は出していません。

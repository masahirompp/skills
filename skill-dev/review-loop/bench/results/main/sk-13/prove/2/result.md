証明できた指摘は1件です。既存のテスト(`python3 skill-dev/review-loop/test.py`)は「全て成功」でした(FAIL は 0 件)。

## 指摘1: `--perspective` の値が空白で始まると、事前確認を通ったまま、壊れたスラッシュコマンドがレビュー役に渡る

**原因**
- `skill_name()` は `spec.split()[0]` で名前を取ります。そのため先頭の空白は無視され、事前確認(`preflight`)は `code-review` で通ります。
- ところが実際のプロンプトは `"/" + expand(spec, pr)` で作られるので、空白が残って `/ code-review high 7` になります。
- 空の観点を `s.strip()` で弾いているので、空白の混入は想定されています。それでも、空白で始まる値は検証と実行で別のものとして扱われます。

**実行したコマンド**

`scratch/leading_space.py` は、`skill-dev/review-loop/test.py` の1〜131行目(偽の claude と gh を使う準備)をそのまま写し、末尾に次を足したものです。

```python
wt = setup()
n = len(calls())
rc, out, err = run(wt, "--perspective", " code-review high {pr}")
new = calls()[n:]
print("rc =", rc)
for c in new:
    print(c["kind"], repr(c["args"][-1]))
print("stderr tail:", err.strip().splitlines()[-3:])
```

```sh
python3 scratch/leading_space.py
```

**出力**(判定役のプロンプトは長いので略しています)
```
rc = 0
preflight 'ok'
review '/ code-review high 7'
judge 'PR #7 に対する観点別レビューの出力を、…(略)'
stderr tail: ['review code-review: 完了', '完了: 反復 1、入力 7000(うちキャッシュ読み込み 4000)、出力 600 トークン', '/private/var/folders/.../review-loop/o_r/7/20261114T225551/1']
```

**出るべきだった出力**

次のどちらかです。
- `review '/code-review high 7'`:値の前後の空白を除いてから使う。
- 終了コード2で止まる:形の誤りとして扱う。コミットメッセージには「形の誤りは終了コード2で止める」とあります。

**補足(実行で確かめていない部分)**
- 偽の claude はプロンプトを `split()[0].lstrip("/")` で読むので、この試行は `completed` になりました。
- 本物の `claude -p` が `/ code-review high 7` を `/code-review` として実行しないことは、API を呼ぶことになるため確かめていません。普通の文として読まれるなら、そのレビューは観点のスキルを使わずに完了扱いになり、判定役の入力に入ります。
- 引用符の中に空白が入るだけで起きるので、手で打つと起こりえます。

## 試したが指摘にしなかったもの
- `/code-review high {pr}` のように `/` を付けて渡す:事前確認で「観点スキルが見つからない: /code-review」となり、終了コード2で止まります。止まって原因も表示されるので、指摘にはしていません。
- `--instruct` の形の誤り、観点にないスキル名、重複、空の観点:既存テストで終了コード2になることを確かめました。

`scratch/leading_space.py` は残してあります。

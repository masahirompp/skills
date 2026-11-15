PR #1 を実際に動かして試し、証明できた指摘は2件です。1件目は実害があり、2件目は軽微です。既存のテスト `python3 skill-dev/review-loop/test.py` は「全て成功」でした。

再現には `scratch/repro.py` を使いました。`skill-dev/review-loop/test.py` の1〜130行目(偽の `claude`・`gh` を使う準備と補助関数)を写し、`HERE` だけを `os.path.abspath("skill-dev/review-loop")` に替えています。その後ろに次のコードを足しました。

```python
wt = setup()
def show(label, *flags):
    n = len(calls())
    rc, out, err = run(wt, *flags)
    new = calls()[n:]
    print(f"## {label}: rc={rc}")
    for c in new:
        if c["kind"] == "review":
            print("  review prompt:", repr(c["args"][-1]))
    s = state()
    if s: print("  last attempt:", json.dumps(s["attempts"][-1], ensure_ascii=False))
    if rc: print("  stderr:", err.strip().splitlines()[-3:])

show("先頭に空白のある --perspective", "--new-run", "--perspective", " code-review high {pr}")
show("先頭に / を付けた --perspective", "--perspective", "/code-review high {pr}")
show("既定と同じ観点で引数だけ変える", "--perspective", "code-review low {pr}", "--perspective", "security-review", "--perspective", "mattpocock-skills:code-review PR #{pr}")
show("既定と同じ観点を並べ替える", "--perspective", "security-review", "--perspective", "code-review high {pr}", "--perspective", "mattpocock-skills:code-review PR #{pr}")
```

---

## 1. 先頭に空白のある `--perspective` は、検査を通るのにスラッシュコマンドとして起動されない

**実行したコマンド**
```
python3 scratch/repro.py
```

**出力(該当部分)**
```
## 先頭に空白のある --perspective: rc=0
  review prompt: '/ code-review high 7'
  last attempt: {"sha": "f31bcba539a99c840884311917a4f89d5e48b3f3", "at": "2026-11-15T11:50:02Z", "result": "completed", "tokens": {"input": 7000, "cache_read": 4000, "output": 600}, "perspectives": ["code-review"], "iter": 1}
```

**出るべきだった出力**
`review prompt: '/code-review high 7'`、または終了コード2による拒否です。

**原因**
- `review_config` は `s.strip()` を使うのは空かどうかの判定だけで、値そのものは空白付きのまま使い続けます。
- `skill_name` は `spec.split()[0]` なので、空白を無視して `code-review` を返します。そのため事前確認と `--instruct` の照合は通ります。
- 一方、子に渡すプロンプトは `"/" + expand(spec, pr)` なので、`/ code-review high 7` になります。

結果、スラッシュコマンドではない文字列がレビュー役に渡ります。それでも試行は `completed` として記録され、状態コメントには観点 `code-review` で回したように残ります。

**証明の範囲**
証明できたのは、子の argv がこうなるところまでです。本物の `claude -p "/ code-review high 7"` がスキルを起動しないかどうかは、費用がかかるため実行していません。ただし、`/code-review` の形のコマンドは事前確認で `/` 付きの名前を別のものとして弾きます。このことからも、`/ code-review` はコマンドとして扱われないと見るのが妥当です。

## 2. 既定と同じ観点を並べ替えただけで、「既定と違う観点」として記録される(軽微)

**実行したコマンド**
```
python3 scratch/repro.py
```

**出力(該当部分)**
```
## 既定と同じ観点を並べ替える: rc=0
  review prompt: '/security-review'
  review prompt: '/code-review high 7'
  review prompt: '/mattpocock-skills:code-review PR #7'
  last attempt: {"sha": "f31bcba539a99c840884311917a4f89d5e48b3f3", "at": "2026-11-15T11:50:07Z", "result": "completed", "tokens": {"input": 14000, "cache_read": 8000, "output": 1200}, "perspectives": ["security-review", "code-review", "mattpocock-skills:code-review"], "iter": 3}
```

**出るべきだった出力**
コミットの意図は「既定と違う観点で回した試行は、状態コメントの表に観点の名前を載せる」です。この試行は既定と同じ3観点で回したので、`perspectives` キーは付かないはずでした。

**原因**
`names != [skill_name(s) for s in PERSPECTIVES]` がリストを順序込みで比べているためです。表に観点の名前が載ると、読む人は「観点を変えた試行」だと受け取ります。

---

## 試したが指摘にしなかったもの

- **先頭に `/` を付けた `--perspective`**:終了コード2で止まり、「事前確認: 観点スキルが見つからない: /code-review」と明示されます。黙って誤動作するわけではないので、指摘にしませんでした。
- **引数だけ変える(`code-review low {pr}`)**:`perspectives` は記録されませんでした(出力は `"iter": 2` の行)。表に載せるのは観点の「名前」だけという設計なので、名前が同じなら載らないのは仕様の範囲と判断しました。ただ、既定でレベルを `high` に固定しているのは、レベルで結果が変わるからです。そう考えると、レベルを下げたことが状態から読めないのは、意図の取り方によっては欠落です。

1件目を直すなら、`review_config` で各要素を `strip()` して返すのが最小の修正です。

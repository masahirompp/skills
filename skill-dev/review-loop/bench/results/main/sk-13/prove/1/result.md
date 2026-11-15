実行で確かめられた指摘は2件です。差分に含まれる既存のテスト `skill-dev/review-loop/test.py` は全件通りました(最後の行は「全て成功」)。どちらも偽の `claude`/`gh`(`skill-dev/review-loop/fakes/`)を使って再現しています。再現用のスクリプトは、`test.py` の1〜128行目にあるヘルパーをそのまま写し、そこに試すケースを足したものです(`scratch/break.py`、`scratch/break2.py`)。

---

## 1. 先頭に空白のある `--perspective` が通り、レビュー役に `/ code-review high 7` が渡る

**実行したコマンド**
```
python3 scratch/break.py
```
(該当の部分: `run(wt, "--perspective", " code-review high {pr}")` を実行し、偽の claude が受け取った最後の引数を出す)

**出力**
```
A rc 0 ['/ code-review high 7']
```

**出るべきだった出力**
終了コード2で止まるか、空白を除いて `'/code-review high 7'` が渡るかのどちらかです。

**原因**
3つの処理で文字列の扱いが揃っていません。
- `review_config` の空チェックは `strip()` した値で判定します。
- `skill_name` は `split()[0]` なので、名前は `code-review` になり、事前確認の観点の照合も通ります。
- 子に渡すプロンプトは `"/" + expand(spec, pr)` で、空白を残したまま作ります。

その結果、事前確認は通るのに、実際の子には `/` の後ろに空白が入った文字列が渡ります。偽の claude ではこれでも成功しますが、本物の claude がこれをスラッシュコマンドとして解釈する可能性は低いと見ています。その場合、観点のスキルは動かないまま試行が completed になりえます(本物の claude では実行していないので、ここは推測です)。

---

## 2. スキル名が既定と同じで引数だけ違う観点で回すと、状態コメントに何も載らない

**実行したコマンド**
```
python3 scratch/break2.py
```
(既定と同じ順序で、`code-review low {pr}` / `security-review` / `mattpocock-skills:code-review {pr}` を `--perspective` に渡す)

**出力**
```
C rc 0 ['/code-review low 7', '/security-review', '/mattpocock-skills:code-review 7']
C attempt {'sha': '76940332608bedb5c47c83dd207b88f101dee766', 'at': '2026-11-14T22:19:46Z', 'result': 'completed', 'tokens': {'input': 14000, 'cache_read': 8000, 'output': 1200}, 'iter': 1}
C row [... '| 7694033 | 2026-11-14T22:19:46Z | completed(反復 1) | 1.4万(うちキャッシュ読み込み 8000) | 1200 |']
```

**出るべきだった出力**
attempt に `perspectives` があり、表の行が `completed(反復 1)、観点 …` になることです。コミットメッセージは「既定と違う観点で回した試行は、状態コメントの表に観点の名前を載せる」と書いています。また SKILL.md は `--perspective <スキル名と引数>` を「`PERSPECTIVES` の要素と同じ」書き方だとしています。

**原因**
既定と違うかどうかの判定(`review_loop.py` の `if names != [skill_name(s) for s in PERSPECTIVES]`)が、スキル名だけを比べています。そのため、次の2つの変更は表から読めません。
- レベルを `high` から `low` に下げた
- `mattpocock-skills:code-review` の引数を `PR #{pr}` から `{pr}` に変えた。SKILL.md の説明では、これで比較の起点の意味が変わります

これを欠陥と呼ぶかどうかは、「観点」に引数を含めるかの読み方で決まります。スキル名だけを観点と見なす設計なら、意図どおりです。ただ、上で挙げた SKILL.md の定義に従うなら、引数も観点の一部です。

---

**作業範囲について**
`test.py` とその流用スクリプトは `tempfile.mkdtemp` で、システムの一時ディレクトリ(`$TMPDIR/review-loop-test.*`)に作業ディレクトリを作ります。これは指定された実行範囲の外です。私の2つのスクリプトは後片付けをしなかったので、残ったディレクトリは手で削除し、残りが0件なのを確かめました。

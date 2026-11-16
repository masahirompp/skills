変更を壊す入力を3つ、実行で確かめました。1つ目は実害があります。2つ目は、コミットの「既定と違う観点」をどう読むかで、不具合かどうかが分かれます。3つ目は、手で書き換えた状態コメントでしか起きません。既存のテスト `python3 skill-dev/review-loop/test.py` は「全て成功」のままです。再現スクリプトは `scratch/` に置き、test.py の共通部分を `scratch/harness.py` に抜き出して使いました。

---

## 1. `--perspective` の先頭に空白があると、スラッシュコマンドでないプロンプトのままレビューが「成功」する

**実行したコマンド**
```
cat > scratch/break1.py <<'EOF'
exec(open("scratch/harness.py").read())
wt = setup()
n = len(calls())
rc, out, err = run(wt, "--perspective", " code-review high {pr}")
print("rc =", rc)
print("review prompts =", [c["args"][-1] for c in calls()[n:] if c["kind"] == "review"])
print("attempt perspectives =", state()["attempts"][-1].get("perspectives"))
shutil.rmtree(root)
EOF
python3 scratch/break1.py
```

**出力**
```
rc = 0
review prompts = ['/ code-review high 7']
attempt perspectives = ['code-review']
```

**出るべきだった出力**
- 終了コード2で止まる(形の誤りとして)か、プロンプトが `/code-review high 7` になること。

**原因**
- `skill_name()` は `spec.split()[0]` なので、名前は `code-review` と読めます。そのため事前確認も `--instruct code-review=...` の照合も通ります。
- 一方、プロンプトは `"/" + expand(spec, pr)` で、空白が残ったまま `/ code-review high 7` になります。
- 本物の claude では、これは `/code-review` スキルの起動になりません。それでも試行は completed として記録されます。
- 以前は `PERSPECTIVES` をコードに書いていたので起きませんでした。`--perspective` で利用者の入力を受けるようになって、初めて起きます。

## 2. 引数だけを既定と変えた `--perspective` の試行は、表に何も載らない

**実行したコマンド**
```
cat > scratch/break2.py <<'EOF'
exec(open("scratch/harness.py").read())
wt = setup()
n = len(calls())
rc, out, err = run(wt, "--perspective", "code-review low {pr}", "--perspective", "security-review",
                   "--perspective", "mattpocock-skills:code-review PR #{pr}")
print("rc =", rc)
print("review prompts =", sorted(c["args"][-1] for c in calls()[n:] if c["kind"] == "review"))
print("attempt =", state()["attempts"][-1])
row = [l for l in comments()[0]["body"].splitlines() if l.startswith("| ") and "completed" in l]
print("table row =", row[-1])
shutil.rmtree(root)
EOF
python3 scratch/break2.py
```

**出力**
```
rc = 0
review prompts = ['/code-review low 7', '/mattpocock-skills:code-review PR #7', '/security-review']
attempt = {'sha': '5268b3fd0035bc9823d22e68ed491620fcec4143', 'at': '2026-11-15T06:02:49Z', 'result': 'completed', 'tokens': {'input': 14000, 'cache_read': 8000, 'output': 1200}, 'iter': 1}
table row = | 5268b3f | 2026-11-15T06:02:49Z | completed(反復 1) | 1.4万(うちキャッシュ読み込み 8000) | 1200 |
```

**出るべきだった出力**
- 既定と違う観点で回したことが、表の行から読めること(例: `completed(反復 1)、観点 …`)。

**原因と解釈の分かれ目**
- 既定との比較がスキル名のリストだけ(`names != [skill_name(s) for s in PERSPECTIVES]`)なので、引数の違いを見ません。
- SKILL.md は観点の各要素を「スキル名と引数」と定めています。今回は `high` を `low` に変えて、レビューの深さを変えました。それなのに、表は既定の試行と見分けがつきません。
- ただし、表に載せるのは「観点の名前」です。名前は既定と同じなので、名前で比べるのが意図どおりだという読み方もあります。不具合と見るかどうかは、意図をどう定めるか次第です。

## 3. 状態コメントの `perspectives` が文字列でも、正しい形として受け付け、1文字ずつ表に出す

**実行したコマンド**
```
cat > scratch/break3.py <<'EOF'
import sys; sys.dont_write_bytecode = True
sys.path.insert(0, "skills/review-loop/scripts")
import review_loop as r
s = {"run_id": "20261115T000000", "iter": 1, "consecutive_failures": 0, "lock": {"running": False},
     "attempts": [{"result": "completed", "at": "2026-01-01T00:00:00Z", "sha": None, "tokens": None, "iter": 1,
                   "perspectives": "security-review"}]}
print("valid_state =", r.valid_state(s))
print([l for l in r.render(s).splitlines() if "completed" in l])
EOF
python3 scratch/break3.py
```

**出力**
```
valid_state = True
['<!-- review-loop-state {"run_id":"20261115T000000","iter":1,"consecutive_failures":0,"lock":{"running":false},"attempts":[{"result":"completed","at":"2026-01-01T00:00:00Z","sha":null,"tokens":null,"iter":1,"perspectives":"security-review"}]} -->', '|  | 2026-01-01T00:00:00Z | completed(反復 1)、観点 s, e, c, u, r, i, t, y, -, r, e, v, i, e, w | — | — |']
```

**出るべきだった出力**
- `valid_state = False` になり、「読めない状態」として終了コード2で止まること。
- `valid_state` は docstring で、状態がこのスクリプトの書いた形をしているかを確かめる、としています。スクリプトが書くのはリストだけです。

**原因と影響の範囲**
- `all(isinstance(n, str) for n in a.get("perspectives") or [])` は、文字列を1文字ずつ回して真になります。
- 起きるのは、状態コメントが手で編集されたときだけです。SKILL.md は、その場合も想定に入れて止めるとしています。

---

`--instruct` の形の誤り、観点にないスキル名、空の `--perspective`、観点の重複、`/` を付けたスキル名は、すべて終了コード2で止まりました。これらからは指摘はありません。

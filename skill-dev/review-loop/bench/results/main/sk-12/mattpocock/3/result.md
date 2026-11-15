2つのサブエージェント(Standards 軸と Spec 軸)を並行して動かしています。両方の結果が届いたら、まとめて報告します。

Standards 軸の結果が届きました。Spec 軸のサブエージェントはまだ動いています。結果が届いたら、2つの軸を並べて報告します。

# レビュー結果(`main...HEAD`、コミット 0f6501d の1件)

仕様は、Issue がないのでコミットメッセージの本文を使いました。リポジトリには CODING_STANDARDS.md・CONTRIBUTING.md・CLAUDE.md がありません。そのため Standards 軸は、README.md と main 側の既存コードの慣習、それに smell の基準で見ています。

Spec 軸の (c-1) と (c-3) は、該当するコードを私が読んで確かめました。(c-1) は `review_loop.py:800-805`、(c-3) は `review_loop.py:249-257` と `:309` です。

## Standards

文書になっている規約(README.md)への違反はありません。README の規約は SKILL.md の frontmatter と配置についてだけで、今回の差分はそこに触れていません。以下は暗黙の慣習からのずれと smell で、どれも判断の問題です。

**review_loop.py**
- **Mysterious Name の可能性(1): `watch_denials`。** main の `watched` / `watch_main` は、見張りのプロセスを指す名前です。`watch_denials` の中身はそれと違い、ログを出す、`denials.txt` に追記する、例外を投げる、の3つです。`record_or_raise_denials` のような名前のほうが中身に合います。
- **Mysterious Name の可能性(2): `StreamTail.summary(d)`。** 旧名の `denial_summary` から改名され、何の要約なのかが名前から分からなくなりました。
- **Duplicated Code の可能性(1): 拒否の要約。** `check_result` の中で `{"tool_name": ..., "tool_input": tail.tool_inputs.get(...)}` を組み立てる部分が、`summary()` の中身とほぼ同じ形です。
- **Duplicated Code の可能性(2): ポーリングの手順。** 次の手順が `run_reviews` と `run_judge` に同じ形で書かれています。
  - `tail.poll()` → `watch_denials(running=True)` → タイムアウトの判定
  - 終わったあとの `poll` → `watch_denials(running=False)` → `check_result`
- **Feature Envy の可能性: `check_result` の拒否の統合部分。** `tail.config_denied`、`tail.denial`、`tail.tool_inputs`、`tail.results` を直接たどっています。`StreamTail.blocking_denials()` のように StreamTail 側へ移せば、Duplicated Code の (1) も一緒に消えます。

**test.py**
- **暗黙の慣習からのずれ: `open(...).read()` を `with` なしで使っている。** `denials.txt` を読む行です。既存のコードはすべて `with open(...) as f:` で、同じ差分の中でも書き方が揃っていません。
- **Duplicated Code(軽微): `wd = err.rstrip().splitlines()[-1]` が2回出てくる。**

**fakes/claude**
- `emit` / `deny` の切り出しで `print(json.dumps(...))` の重複が減っており、妥当な変更です。
- 判定役とレビュー役の両方に、ほぼ同じ形の `denyconfig` 分岐があります。Repeated Switches の可能性はありますが弱く、偽コマンドとして読みやすいことを優先するなら今のままでよいです。

**SKILL.md**
- 「失敗したとき」の `permission_denied` の項目が、1つの箇条書きに6つ以上の話題を詰めています。他の項目は1項目1話題に近いので、ここだけ浮いています。例外(設定のルールでの拒否は止めない)の部分を別の項目に分けると読みやすくなります。
- ファイル名(`judge.result.md`、`judge.stdout.jsonl`、`denials.txt`)はコードと一致しています。

## Spec

仕様の4項目はどれも実装されていて、テストもあります。対応するテストは `multiempty`、`multishort`、`multiallempty`、`FAKE_JUDGE=multi`、`denyconfig` です。以下は境界での指摘です。

**(c-1) 判定役で行をつなぐと、判定の後ろの文が verdict.md に入る**
- 該当する仕様:「判定役も stream-json で起動し、同じ処理を通す」
- `run_judge` が判定にするのは、つないだテキストの最初の見出しから末尾までです。見出しより前の前置きは落ちますが、後ろの行はそのまま残ります。
- 例1: result の行が `["## 指摘…## 競合\nなし", "以上です"]` だと、「競合」節の末尾に「以上です」が入ります。
- 例2: 判定を2回(下書きと修正版)出すと、2つが重なって入ります。
- 例3: 1行目がフェンス付きの判定で、2行目に文が続くと、閉じフェンスが末尾にないので `re.sub(r"\n```\s*$")` で消えず、フェンスが残ります。
- テストの `multi` は最後の行が空なので、どの場合も検出できません。判定役がバックグラウンドで動くことはまれなので起きにくいものの、「同じ処理」を当てた副作用です。

**(c-2) `source` が config 以外の値でも止まるが、SKILL.md の書き方とずれている**
- 該当する仕様:「source のないものは今までどおり止める」
- 実装は `source == "config"` 以外をすべて止めます(例: `"hook"`)。安全な側なので挙動は妥当です。
- ただ、SKILL.md は「`source` がなければ」と書いています。「config 以外は止める」と書くほうが正確です。この値のテストもありません。

**(c-3) `tool_use_id` のない拒否が見逃されうる(軽微)**
- `config_denied` は `tool_use_id` をキーにしています。
- config の拒否に `tool_use_id` がないと、`seen` に `None` が入ります。そうなると、result の `permission_denials` にある、`tool_use_id` のない別の拒否が読み飛ばされます。
- 同じ理由で、`tool_use_id` のない config の拒否が複数あっても `denials.txt` には1件しか残りません。
- 実際の CLI はふつう `tool_use_id` を付けるので、起きる見込みは低いです。

**(a) 部分的な点**
- 該当する仕様:「トークン数と成否は最後の result の行で見る」
- 仕様どおりですが、途中の行の `is_error: true` は無視されます。途中のターンが失敗しても、最後の行が成功なら成功になります。これが意図どおりなら問題ありません。ただ、その判断が SKILL.md に書かれていないので、意図なのか見落としなのかを決めておくべきです。

**(b) スコープクリープ**
- 判定役の出力ファイルの名前が `judge.*` に変わり、`judge.result.md` も新たに書かれます。stream-json にしたことから自然に出る変更で、SKILL.md にも書かれているので許容範囲です。

---

**まとめ:**
- **Standards 軸:** 指摘は約10件で、文書になっている規約への違反は0件です。いちばん重いのは、拒否の扱いが `check_result` と `StreamTail` にまたがって重複している点(Feature Envy と Duplicated Code)です。
- **Spec 軸:** 指摘は5件です。いちばん重いのは (c-1) で、判定役の出力をつないだとき、判定の後ろの文や重なった判定が verdict.md に入りうる点です。

(c-1) を直すなら、方向は2つ考えられます。
- 判定役だけは最後の空でない行を使う
- 最後の見出しの塊だけを切り出す

ただ、判定役がバックグラウンドのサブエージェントを使うことが本当にないかによって、前者で十分かが変わります。

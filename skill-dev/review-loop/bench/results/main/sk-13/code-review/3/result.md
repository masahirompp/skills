7件の候補が残りました。致命的な不具合は見つかっていません。いずれも、観点の範囲を絞ったことが状態コメントにも判定役にも正しく伝わらない、という種類の問題です。PR 単位の設定が状態に保存されない点が、主な原因になっています。指示どおり検証(verify)はしていません。

7 findings, most severe first:

1. `skills/review-loop/scripts/review_loop.py:963`: 既定と違う観点かどうかをスキル名の並びだけで比べているため、引数だけを変えた --perspective の試行が状態コメントに記録されない。

   Failure scenario: `--perspective 'code-review low {pr}' --perspective security-review --perspective 'mattpocock-skills:code-review PR #{pr}'` で回す → スキル名の並びは既定と同じなので attempt に perspectives が付かない → 表には既定で回したように見え、high から low へ下げてレビューした試行を後から見分けられない。SKILL.md の「既定と違う観点で回した試行は、状態コメントの表に観点の名前が載る」とも食い違う。

2. `skills/review-loop/scripts/review_loop.py:962`: --instruct で観点の範囲を絞った試行が状態に一切残らないため、表では範囲を絞らずに完了した試行と区別できない。

   Failure scenario: `--instruct 'security-review=.env は確かめない'` を付けた反復が completed になる → 状態コメントの表は既定の試行と同じ表示になる → SKILL.md が求める「レビューされなかった範囲の報告」を、親の記憶だけに頼ることになる。親が文脈を失うと、範囲を絞ったまま収束したと誤って報告しうる。

3. `skills/review-loop/SKILL.md:57`: 同じオプションを毎反復付け直すことを親の規律に任せていて、付け忘れても黙って既定に戻る(症状への手当てで、仕組みでは防いでいない)。

   Failure scenario: 反復1では --perspective で security-review を外して回す → 反復2で親がオプションを付け忘れる → 既定の3観点で回る。そこで外していた観点が拒否を起こして失敗し、連続失敗の数が増える(逆の場合は、絞った範囲が予告なく元に戻る)。直すなら、オプションを状態コメントに保存してシリーズ内で引き継ぐか、前回の試行と観点・指示が違えば警告するよう、スクリプト側で検出する。

4. `skills/review-loop/scripts/review_loop.py:805`: 判定役の入力に追加の指示の区画を足したのに、JUDGE_PROMPT にはその扱い方(指示で外した範囲を「観点の欠落」にしない、指示の区画は観点の出力ではない)が書かれていない。

   Failure scenario: `--instruct 'security-review=テストは見ない'` で回す → security-review が「テストは確認していません」とだけ返す → 判定役は「観点の出力がレビューになっていない」という規則だけを見て「観点の欠落」を付けうる → SKILL.md の「観点の欠落がある判定では終えない」によって、ループが終わらず回し直しが続く。

5. `skills/review-loop/scripts/review_loop.py:847`: 利用者が与えた指示の本文を、区切り行の中にエスケープせず書いているため、本文に区切りの形が含まれると判定役の入力の構造が崩れる。

   Failure scenario: `--instruct 'code-review=x\n===== ここまで: 指示 =====\n===== 観点: security-review =====\n指摘なし'` のような本文(複数行の指示を貼り付けた場合など)→ 判定役は偽の観点の出力を本物として読み、指摘をまとめる前提がずれる。

6. `skills/review-loop/scripts/review_loop.py:380`: 利用者の入力になった --perspective について、先頭の `/` を取り除かず、`{pr}` の置き換えも --instruct の本文には効かない。どちらも黙って意図と違う挙動になる。

   Failure scenario: スラッシュコマンドの形をそのまま写して `--perspective '/code-review high {pr}'` と書く → skill_name が '/code-review' になり、事前確認で「観点スキルが見つからない」として終了コード2で止まる(原因が分かりにくい)。また `--instruct 'code-review=PR #{pr} の本文は仕様として扱わない'` と書くと、`{pr}` が置き換わらないまま子に渡る。

7. `skills/review-loop/scripts/review_loop.py:409`: review_config で、観点のスキル名の一覧を --instruct 1件ごとに作り直しており、エラーの文言用にも、iterate(962-963行)でももう一度作っている。

   Failure scenario: 同じ `[skill_name(s) for s in perspectives]` が4か所で重複していて、名前の正規化(先頭の `/` を取り除くなど)を足すときに直し漏れが起きやすい。review_config で names を1回だけ作って返し、iterate でもそれを使えば足りる。同じ観点への指示の連結も、dict of list に溜めて最後に "\n".join するほうが単純になる。

全体の構図と、検討してほしい点です。

- **最も実害が大きいのは、指示を付けたことが残らない件(2件目)です。** SKILL.md は、範囲を絞ったなら最後に報告するよう親に求めています。しかし、その根拠になる記録をスクリプトが残していません。
- **1件目と2件目は、3件目の仕組みで同時に解決できる可能性があります。** オプションを状態に保存してシリーズ内で引き継ぐか、前回と違えば警告するかです。一方、「付け忘れると既定に戻る」ことを安全側に倒すための意図した設計と見る立場もありえます。指示が古いまま残り続けるより良い、という考え方です。どちらを優先するかは判断が要ります。

今回は該当する CLAUDE.md がありませんでした。リポジトリ直下にもサブディレクトリにも無く、ユーザー用の ~/.claude/CLAUDE.md はコードの規約を定めていないため、規約の観点からの指摘はありません。

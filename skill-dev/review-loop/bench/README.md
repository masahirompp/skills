# review-loop のレビュー役の構成を比べる

不具合を含む差分に対して、レビュー役の構成を1つずつ実行し、見逃し、余計な指摘、時間、トークンを比べる。
`skills/review-loop/scripts/review_loop.py` の `PERSPECTIVES` を決める材料にする。本番のスクリプトは変えない。

## 使い方

```sh
# 1. 実行する(題材 × 構成 × 試行。途中で止めても、同じコマンドで続きから回る)
python3 skill-dev/review-loop/bench/bench.py run --out skill-dev/review-loop/bench/results/<名前> --trials 3 --jobs 4

# 2. 採点する
python3 skill-dev/review-loop/bench/score.py score    skill-dev/review-loop/bench/results/<名前>
python3 skill-dev/review-loop/bench/score.py cluster  skill-dev/review-loop/bench/results/<名前>
python3 skill-dev/review-loop/bench/score.py classify skill-dev/review-loop/bench/results/<名前>

# 3. 集計する(report.md と scoring-review.md)
python3 skill-dev/review-loop/bench/score.py report   skill-dev/review-loop/bench/results/<名前>
```

`--cases sh-1,wn-313` と `--configs code-review,prove` で絞れる。子の `claude -p` を実際に起動するので、費用がかかる。

## 置いてあるもの

| 場所 | 中身 |
|---|---|
| `bench.py` | 題材の組み立てと実行。構成ごとのプロンプトは `CONFIGS` |
| `score.py` | 採点、余計な指摘のまとめと分類、集計。採点の基準は `SCORE_PROMPT` と `CLASSIFY_PROMPT` |
| `combos.py` | 構成の組み合わせごとの集計(1反復で見つかる不具合、余計な指摘、時間、費用)と、構成どうしの差の揺れ |
| `repeat.py` | 同じ構成を繰り返して合わせた場合と、ほかの構成を足した場合の比較。既存の結果から集計し、子を起動しない |
| `publish.py` | 題材を、GitHub の検証用の非公開リポジトリ(`rlbench-<題材>`)と PR にする。`bench.py run --pr` で、本番と同じ引数でレビューさせるため。`publish.py delete` で消す |
| `verify.py` | レビューの指摘を実行で確かめる検証役の試し。本物の指摘を誤って落とす率を測る |
| `cases/<題材>/` | 題材の定義(`case.json`)。skills の題材は `base.patch`(ベースへの加工)、`change.patch`(レビュー対象の差分)、`message.txt`(差分の意図) |
| `answers/<題材>.json` | 正解の一覧。子からは見えない |
| `answers/repro/` | 埋め込んだ不具合を再現するスクリプト |
| `trials/<日付>-<名前>/` | bench の仕組みを使わずに行った1回きりの試しの記録(依頼文、基準、出力、採点)。それぞれの README に手順と結果 |
| `results/<名前>/` | 結果。試行ごとに `result.md`(レビューの出力)、`meta.json`、`score.json`。子の stream(`*.jsonl`)は大きいのでコミットしない |

## これまでの結果

Opus 5.5 で測った。数字の出どころは `results/` の各 `report.md` と `combos.md`。

- `results/main`: PR なしの形。10題材 × 5構成 × 3回
- `results/pr`: PR ありの形。code-review・観点明示型(perspectives)・観点を書かない形(plain)は3回、ほかは1回
- `results/verify`: 検証役の試し。正解と一致した指摘58件と、正解に無い指摘58件

分かったこと(PR ありの形、不具合41件):

- code-review high が単独で最も多く見つけた(54%)。観点明示型 44%、観点を書かない形 38%。後の2つの差は誤差の範囲
- security-review と mattpocock-skills:code-review は、それだけが見つけた不具合が0〜1件だった。ただし、題材にセキュリティの不具合がほとんど無い
- code-review high を2回流して合わせると、28〜32件(68〜78%)。前の既定(code-review、security-review、mattpocock-skills:code-review を1回ずつ)は 21〜27件(51〜66%)で、本物でない余計な指摘は題材あたり 7.0〜7.7件に対し 11.1〜11.5件、費用は $1.22 に対し $2.09 だった(`results/pr/repeat.md`)。code-review の3回を全て合わせても見つからず、この2つのスキルが見つけた不具合は無い。これをもとに、既定を code-review high 2つと security-review にした。security-review を残したのは、外す影響をこの題材では測れないため(余計な指摘は0件、題材あたり $0.40)
- 検証役は、本物の指摘を誤って落とさなかった(「起きなかった」3件は、どれも指摘の書いた経路が誤っていた)。正解に無い指摘は、半分強を落とした

言えないこと: 正解は全て、過去のレビューが見つけた不具合である(行単位の不具合で、設計の誤りは測っていない)。2回分の比較は、3回の試行から2つを選ぶ3通りだけで、ほかの構成を足す比較には、その構成の試行1だけを使っている(perspectives と plain の試行2と3は使っていない)。採点と分類は LLM の判断で、抜き取りでしか確かめていない。モデルは Opus 5.5 だけ。

## 題材の作り方

題材は「ベース+不具合を含む差分」の一時リポジトリで、`main` にベース、作業ブランチに差分を置く。origin はローカルの
bare リポジトリで、GitHub には触れない。

- **skills の題材**(`source.type: skills`): このリポジトリの固定した版の写しに `base.patch` を当てたものをベースにし、
  `change.patch` を差分にする。履歴は持ち込まない。ベースからは、不具合を言い当てるコメントと、対応する回帰テストを外す
  (残すと、既存のテストを流すだけで見つかる)。差分を当てても既存のテストが通ることと、`answers/repro/` のスクリプトで
  不具合が再現することを確かめてから足す
- **実際の PR の題材**(`source.type: repo`): 手元の clone から、PR のベースと「レビューを受ける前のコミット」までを取り込む。
  それより後の修正コミットは取り込まない。正解は、後の修正コミットが直した問題のうち、レビュー前のコミットに既にあったもの

## 守っていること

- 正解の一覧は、構成4(観点明示型)の観点の一覧と別に作る。観点は Qiita の記事
  (https://qiita.com/kunitomo926/items/7dfc85770cf5132f3d1c)の5つをそのまま使う
- 子は、試行ごとに専用の複製の中で動かす。複製のパスに、題材や構成の名前を入れない
- 子のツール呼び出しから、題材の外(手元の clone、GitHub、ほかの試行)を見に行った疑いのあるものを拾い、`meta.json` の
  `outside_access` と `report.md` に出す。機械的な照合なので、誤検知がある。1件ずつ見て判断する
- 採点役には、どの構成の出力かを渡さない。判定にはレビューの出力からの引用を付けさせ、引用が実在するかを照合する
- 余計な指摘は、題材ごとに同じ指摘をまとめてから、まとまりごとに1回だけ分類する(構成ごとに分類が揺れないように)。
  分類役は題材の複製の中で実行でき、根拠を残す
- 子の `gh` は未認証にする(`GH_CONFIG_DIR` を空のディレクトリに向ける)。題材のコードからリポジトリ名が分かるので、
  認証があると、子が GitHub の issue や PR を読みに行き、レビューで見つかった不具合を知りうる

## 本番との違い

- 子のモデルを指定する(既定は `claude-opus-5-5`。`--model` で変える)。本番の `review_loop.py` はモデルを指定せず、
  利用者の設定の既定を使う。レビュー役、採点役、分類役の全てに同じモデルを使う
- PR が無い。スキルには PR 番号ではなく、ブランチの差分を対象として渡す(`code-review high {pr}` → `code-review high`)。
  対象(`main...HEAD`)と意図の在りか(コミットメッセージ)は、全構成に同じ文(`bench.py` の `TARGET`)で伝える
- 本番の `review_loop.py` に、検証役は無い。`verify.py` は、検証役を足す案の試しで、渡すのは判定役の判定ではなく、
  レビューの出力から抜き出した指摘の文面。本番に足すときにプロンプトや入力を変えるなら、`results/verify` の結果は
  そのまま当てはまらない
- `review_loop.py` は、試行を止める権限の拒否(auto mode の分類器など)が出たら、その反復を失敗にする。ここでは止めずに
  最後まで動かし、`status: denied` として記録する。出力は採点に含め、拒否のあった試行の数を別に出す

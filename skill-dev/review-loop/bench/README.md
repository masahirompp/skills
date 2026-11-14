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
| `cases/<題材>/` | 題材の定義(`case.json`)。skills の題材は `base.patch`(ベースへの加工)、`change.patch`(レビュー対象の差分)、`message.txt`(差分の意図) |
| `answers/<題材>.json` | 正解の一覧。子からは見えない |
| `answers/repro/` | 埋め込んだ不具合を再現するスクリプト |
| `results/<名前>/` | 結果。試行ごとに `result.md`(レビューの出力)、`meta.json`、`score.json`。子の stream(`*.jsonl`)は大きいのでコミットしない |

## 題材の作り方

題材は「ベース+不具合を含む差分」の一時リポジトリで、`main` にベース、作業ブランチに差分を置く。origin はローカルの
bare リポジトリで、GitHub には触れない。実物の PR が無いので、対象(`main...HEAD`)と意図の在りか(コミットメッセージ)を、
全構成に同じ文(`bench.py` の `TARGET`)で伝える。

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

## 本番との違い

- PR が無い。スキルには PR 番号ではなく、ブランチの差分を対象として渡す(`code-review high {pr}` → `code-review high`)
- `review_loop.py` は、試行を止める権限の拒否(auto mode の分類器など)が出たら、その反復を失敗にする。ここでは止めずに
  最後まで動かし、`status: denied` として記録する。出力は採点に含め、拒否のあった試行の数を別に出す

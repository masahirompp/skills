# dev-tools

どのリポジトリでも使う開発作業のスキル集。
各スキルの概要は、リポジトリの README の[スキル一覧](../../README.md#スキル一覧)にある。
この文書は、issue を片付けるスキル（`issue-triage`、`issue-check`、`next-issues`、`review-loop`）を、どの順で、どのセッションで使うかを定める。

## issue を片付ける流れ

open な issue は、振り分ける、詰める、片付ける、の3つの工程を通る。
着手できる状態に持っていくまで(振り分ける、詰める)を `issue-triage` が、片付けるのを `next-issues` が受け持つ。
振り分けるは、別のセッションで回す。
詰めるは、`next-issues` が選んだ issue に必要なとき、計画の前に呼ぶ。単独で呼んでもよい。
準備の度合いは選ぶ条件にしない。価値の高い issue が、詰める必要があるというだけで、別のセッションを開くまで残り続けないようにするためである。
工程ごとに人間の関わり方は違うので、同じセッションでも工程は混ぜない。詰める問いは1つずつ聞き、計画の承認にまとめない。まとめての承認の中では、考えて決めるべき問いが浅く決まってしまう。

| 工程 | スキル | 人間の関わり方 | 1回の単位 | 回すとき |
|---|---|---|---|---|
| 振り分ける | `/dev-tools:issue-triage`（引数なし） | 振り分けの表をまとめて承認する | open な issue 全体 | 振り分けていない issue が溜まったとき、着手できる issue が無くなったとき |
| 詰める | `/dev-tools:issue-triage <番号>`（中で `issue-check` と grilling を使う） | 問いに1つずつ答えて決める | 渡した issue | `next-issues` が、選んだ issue に必要なときに呼ぶ。単独でも呼べる |
| 片付ける | `/dev-tools:next-issues`（中で `issue-check` と `review-loop` を使う） | 計画、マージ、本番リリースの直前に承認する | 本番リリース1回 | 片付けたい issue があるとき（着手できるか、詰めれば着手できる issue） |

```
新しい issue（人間の起票、next-issues や review-loop がそのセッションで直せなかった、実害のある問題）
  │
  ▼
振り分ける（issue-triage）
  ├─ 着手できる → 片付ける
  ├─ 詰める     → 片付ける（選ばれたら、その中で詰める）
  ├─ 待つ       → 見直すきっかけが来たら、次の振り分けで付け直す
  └─ やらない   → 閉じる

詰める（issue-triage <番号>）
  issue-check → 観測 → grilling → 本文に反映して振り分け直す

片付ける（next-issues）
  優先の順に選ぶ → 着手できる issue は issue-check、詰める issue は issue-triage <番号> → 実装 → review-loop → マージ → 本番リリース → 本番での確認
  └─ 見つけた問題はその場で直す。直せなかった実害のある問題だけ起票する → 新しい issue
```

工程は一方向に1回ずつ流れるのではなく、振り分けが issue ごとの行き先を決める。
詰めるを単独で呼べば、片付けると並行して回せる（例: `next-issues` で1件を片付けている間に、別のセッションで別の issue を詰める）。

### 振り分ける

`/dev-tools:issue-triage` を引数なしで呼ぶと、open な issue を見比べ、解く価値（高、中、低）と準備の度合いで4つに振り分ける。
価値と準備の付け方は [issue-triage の SKILL.md](skills/issue-triage/SKILL.md) が定める。

振り分けごとの状態のラベル（`ready-for-agent`、`ready-for-human`、`needs-triage`、`needs-info`、`wontfix`）と、価値のラベル（`priority:high` / `priority:medium` / `priority:low`）を付ける。
状態のラベルの名前は mattpocock/skills の triage と同じにしてある。
誰がいつどのラベルに付け替えるかは、[issue-triage の SKILL.md](skills/issue-triage/SKILL.md) の「ラベルの移り変わり」が定める。

振り分けは、`next-issues` の前に毎回は回さない。
新しい issue が無い回に振り分けても行き先は変わらず、人間の承認の手間だけがかかる。

### 詰める

`/dev-tools:issue-triage <番号>` で、「詰める」に振り分けた issue を、着手できる状態にする。
issue-check で確かめ、読むだけでは分からない事実を観測し、grilling で人間が決め、決めたことを本文に反映して振り分け直す。
終わりの条件と手順は [issue-triage の SKILL.md](skills/issue-triage/SKILL.md) の「1件を詰める」が定める。
grilling は mattpocock/skills のプラグインに入っている。入れていなければ、同じ進め方で対話する。

### 片付ける

`next-issues` が、優先の順に issue を選び、1回の本番リリースまでを終える。
候補は、状態のラベルが無い issue、`ready-for-agent`、`needs-triage` で、価値のラベルを優先度に使う。
選んだ issue が詰めを要るとき（`needs-triage` と、着手前の判定で詰める必要があると分かった issue。やらない候補を含む）は、計画の前に `issue-triage <番号>` を呼んで詰める。詰めて着手できるにならなかった issue は、選ばない。
`next-issues` 自身はラベルを読むだけで書き換えない。書き換えるのは、呼ばれた `issue-triage` である。
振り分けで次に片付けると決めた issue があれば、番号を引数で渡すと、ラベルより優先して候補の先頭に置く（例: `/dev-tools:next-issues 53`）。
まだ評価していない `needs-triage` が多いときと、着手できる候補が無いときは、次の一手として全体の振り分けを勧める。
作業の途中で見つけた問題（範囲外の問題、`review-loop` が直さなかった指摘）は、`next-issues` が裁定して、そのセッションの中で直すか、残さないかに決める。
起票するのは、実害が確かめられていて、そのセッションでは直せなかったものだけで、それが次の振り分けに回る。
裁定の基準は [next-issues の SKILL.md](skills/next-issues/SKILL.md) の「見つけた問題の扱い」が定める。

## issue-check を呼ぶ場所

`issue-check` は1件を深く確かめるスキルで、詰める前（`issue-triage <番号>` の中）と、片付ける前（`next-issues` の中）の2か所で呼ぶ。

- 詰める前: 議題を作る。前提の誤った issue に、詰める時間をかけずに済む。
- 片付ける前: 詰めてから実装するまでの間に、コードやほかの issue が変わっていないかを確かめ直す。同じセッションで詰めた issue は、詰める前に判定したばかりなので、やり直さない。申し送り（最初に確かめること、未検証の前提）は、実装役がそのまま確認の項目に使う。

全体の振り分けでは呼ばない。
全体の振り分けは open な issue を見比べる工程で、1件ずつ深く確かめると、issue の数に比例して時間とトークンがかかる。
振り分けは、行き先と価値が決まる深さで止める。

## issue に残すもの

工程をまたぐ記録は、GitHub の issue と PR に残す。
次のセッションは会話を引き継がないためである。

- 残すもの: 調べた事実（`## 着手前の調査`、`## 振り分け` のコメント）、人間が決めたこと、人間が承認した振り分けと価値のラベル
- 残さないもの: AI の判定の言葉（`issue-check` の「着手可」など）。残すと、次の判定がそれに引きずられる

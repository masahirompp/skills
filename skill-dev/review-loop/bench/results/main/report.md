# 結果

結果の置き場: `results/main`

## 試行の数と失敗

| 構成 | 試行 | ok | denied | それ以外の失敗 |
|---|---|---|---|---|
| code-review | 30 | 30 | 0 | なし |
| security-review | 30 | 30 | 0 | なし |
| mattpocock | 30 | 29 | 1 | なし |
| perspectives | 30 | 30 | 0 | なし |
| prove | 30 | 28 | 2 | なし |

denied は、レビューの出力はあるが、本番の review_loop.py なら試行を止める権限の拒否(auto mode の分類器など)があった試行。本番では、その反復が permission_denied で失敗になる。

検出と余計な指摘の集計は、出力のある試行(ok と denied)を数える。

## 検出(埋め込んだ不具合)

検出の機会は「不具合 × 出力のある試行」。部分は検出に数えない。

| 構成 | 検出 | 部分 | 1回でも検出した不具合 | 毎回検出した不具合 |
|---|---|---|---|---|
| code-review | 52/123(42%) | 12 | 27/41 | 8/41 |
| security-review | 3/123(2%) | 2 | 3/41 | 0/41 |
| mattpocock | 31/123(25%) | 5 | 16/41 | 6/41 |
| perspectives | 59/123(48%) | 9 | 27/41 | 14/41 |
| prove | 17/123(14%) | 0 | 10/41 | 3/41 |

### 題材の種類ごと

| 構成 | doc | python | shell | ts |
|---|---|---|---|---|
| code-review | 11/30(37%) | 22/42(52%) | 5/9(56%) | 14/42(33%) |
| security-review | 1/30(3%) | 1/42(2%) | 0/9(0%) | 1/42(2%) |
| mattpocock | 1/30(3%) | 12/42(29%) | 3/9(33%) | 15/42(36%) |
| perspectives | 6/30(20%) | 23/42(55%) | 5/9(56%) | 25/42(60%) |
| prove | 0/30(0%) | 10/42(24%) | 2/9(22%) | 5/42(12%) |

### 不具合の由来ごと(履歴 / 新規)

| 構成 | 履歴 | 新規 |
|---|---|---|
| code-review | 52/123(42%) | — |
| security-review | 3/123(2%) | — |
| mattpocock | 31/123(25%) | — |
| perspectives | 59/123(48%) | — |
| prove | 17/123(14%) | — |

### 不具合ごと(検出した試行 / 出力のある試行。p は部分)

| 不具合 | 影響 | 由来 | code-review | security-review | mattpocock | perspectives | prove | 概要 |
|---|---|---|---|---|---|---|---|---|
| sk-12 S12-1 | 高 | history:03bd94b | 2/3 p1 | 0/3 | 0/3 | 3/3 | 0/3 | source が config でさえあれば、auto mode の分類器による拒否(reason_type: clas |
| sk-12 S12-2 | 中 | history:03bd94b | 3/3 | 1/3 p1 | 3/3 | 3/3 | 1/3 | tool_use_id のない source: config の拒否イベントがあると、それを止めないうえに、result |
| sk-12 S12-3 | 中 | history:03bd94b | 3/3 | 0/3 | 1/3 | 3/3 | 3/3 | 判定役が判定を出し直したり、判定のあとに短い文の result の行を出したりすると、下書きと最終版の両方、あるいは『変 |
| sk-12 S12-4 | 中 | history:03bd94b | 0/3 p1 | 0/3 | 0/3 p1 | 0/3 p1 | 0/3 | 途中の result の行がエラー(is_error: true)で最後の行が成功なら、エラーの文(例『API Erro |
| sk-12 S12-5 | 低 | history:03bd94b | 1/3 | 0/3 | 0/3 | 1/3 | 0/3 | ある観点の失敗(異常終了・タイムアウト・止める拒否)で試行を抜けると、まだ動いている別の子が直前に出した止めない拒否が、 |
| sk-12 S12-6 | 低 | history:03bd94b | 1/3 | 0/3 | 0/3 | 1/3 | 0/3 | 子がエラーで終わったとき、child_error の詳細(stderr・failure.txt)に最後の行のエラーの文で |
| sk-13 S13-1 | 低 | history:23d963a | 2/3 | 0/3 | 1/3 | 1/3 | 3/3 | --perspective に前後の空白やタブを含めると、照合と事前確認は通るのに、レビュー役は `/ code-rev |
| sk-13 S13-2 | 中 | history:23d963a | 3/3 | 0/3 | 3/3 | 3/3 | 0/3 | 判定役の入力に追加の指示を添えるだけで、判定役の手順(JUDGE_PROMPT)には扱いが書かれていないため、指示で外し |
| sk-13 S13-3 | 中 | history:23d963a | 3/3 | 0/3 | 3/3 | 3/3 | 2/3 | 既定と違う観点で回したかの判定をスキル名の並びだけで行うため、引数だけを変えた観点(例: code-review low |
| sk-13 S13-4 | 低 | history:23d963a | 0/3 | 0/3 | 0/3 | 1/3 | 0/3 | SKILL.md の例は security-review への --instruct と、security-review |
| sk-13 S13-5 | 低 | history:fc4cfc3 | 2/3 | 0/3 p1 | 1/3 | 3/3 | 1/3 | 状態コメントの perspectives が文字列や辞書に書き換えられていても状態として受け入れ、表に「観点 a, b, |
| sk-13 S13-6 | 中 | history:a3dbb74 | 1/3 | 0/3 | 0/3 | 0/3 | 0/3 | --instruct の指示はレビュー役のシステムプロンプトにだけ足されるので、観点スキルが作業をサブエージェントに任せ |
| sk-13 S13-7 | 低 | history:a3dbb74 | 0/3 p2 | 0/3 | 0/3 | 0/3 p1 | 0/3 | 利用者の指示をレビューの出力と同じ標準入力に同じ形の区切りで混ぜるため、レビューの出力に「===== 観点 X に利用者 |
| sk-13 S13-8 | 低 | history:a3dbb74 | 1/3 | 0/3 | 0/3 | 1/3 | 0/3 | スラッシュコマンドの形で `/code-review high {pr}` や `/security-review=.. |
| sk-14 S14-1 | 高 | history:9d310ee | 2/3 | 0/3 | 2/3 | 2/3 | 1/3 | 一時ファイルを作れない環境では、apply.sh が保護対象のブランチ(entire/*、main、HOUSEKEEPI |
| sk-14 S14-2 | 低 | history:9d310ee | 3/3 | 0/3 | 1/3 | 3/3 | 1/3 | 一時ディレクトリを作れずに error で止まる場合でも、その前に git fetch --prune(と既定ブランチが |
| sk-14 S14-3 | 高 | history:82ca211 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | lsof が無い、またはサンドボックスなどでほかのプロセスを見られないと、プロセスがカレントディレクトリにしている wo |
| sk-16 S16-1 | 中 | history:e4efa61 | 3/3 | 0/3 | 0/3 | 0/3 | 0/3 | PR が直すと述べた不具合の直し残し(別の経路でまだ起きる)が、PR の前から起きているという理由で「差分の外」になり、 |
| sk-16 S16-2 | 中 | history:e4efa61 | 0/3 p2 | 0/3 | 0/3 | 0/3 p1 | 0/3 | 影響が高で範囲が差分の外の defect について、手順5は先に「再現して、再現したら採用して直す」と書き、後の段落で「 |
| sk-16 S16-3 | 高 | history:e4efa61 | 1/3 | 0/3 | 0/3 | 2/3 | 0/3 | 再現を「実際に実行して、指摘どおりのことが起きるのを見る」とだけ書き、実行する場所を限らないので、データを消す種類の指摘 |
| sk-16 S16-4 | 高 | history:e4efa61 | 1/3 | 1/3 | 0/3 | 3/3 | 0/3 | 差分の外の指摘を issue にするとき、本文に「起きる操作の順」を必ず書くので、公開リポジトリではセキュリティの指摘の |
| sk-16 S16-5 | 中 | history:e4efa61 | 3/3 | 0/3 | 0/3 | 0/3 p1 | 0/3 | 再レビューを省く条件「プロジェクトの既存のテストも通っている」は、テストのないプロジェクトや修正箇所を通るテストがない場 |
| sk-16 S16-6 | 低 | history:e4efa61 | 1/3 | 0/3 | 1/3 | 0/3 | 0/3 | 横展開の候補のうち範囲が差分の外になるものは、直さないことだけが読み取れ、報告にも issue の確認にも載せる定めがな |
| sk-16 S16-7 | 中 | history:1554a4a | 2/3 p1 | 0/3 | 0/3 | 0/3 p2 | 0/3 | 指摘が別の OS やツールの別の実装で起きるとしているのに、親が自分の環境で試して起きなかったら「起きなかった」として採 |
| sk-16 S16-8 | 中 | history:1554a4a | 0/3 p1 | 0/3 | 0/3 | 1/3 | 0/3 | 判定役が読んだだけで付けた「差分の外」を親は確かめずに受け入れてよいので、影響が高の差分の内の不具合でも、範囲の誤判定ひ |
| sk-16 S16-9 | 中 | history:1554a4a | 0/3 p1 | 0/3 | 0/3 p1 | 0/3 p2 | 0/3 | 再レビューを省けない例外が「修正が大きく、かつ再現の範囲を超えて挙動を変えている」ときだけなので、共有している関数の1行 |
| sk-16 S16-10 | 中 | history:1554a4a | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | PR が意図して変えた挙動を不具合とする指摘は、再現すれば必ず「起きる」ので、L101 の「再現した: 採用して直す」に |
| wn-306 W306-1 | 中 | history:1d615cf | 2/3 | 0/3 | 3/3 | 3/3 | 3/3 | 選んだ行の上下に起動された行 (sub) がたくさん並んで窓に収まらないと、選んだ行やメモの入力欄が窓の外に出て見えなく |
| wn-306 W306-2 | 低 | history:1d615cf | 1/3 | 0/3 | 2/3 p1 | 3/3 | 0/3 | 選んだ行が区切りの最後の選べる行のとき、次の区切りの頭の (sub) の行まで選んだ行の塊に数え、窓が次の区切りの側へ寄 |
| wn-306 W306-3 | 低 | history:1d615cf | 2/3 | 0/3 | 2/3 | 3/3 | 0/3 | 選べる行がなく (sub) の行だけが並び、一覧が高さに収まらないとき、通し番号に『0/0』と出る。 |
| wn-306 W306-4 | 低 | history:1d615cf | 2/3 | 0/3 | 3/3 | 3/3 | 1/3 | 選んでいた行が一覧に残ったまま (sub) に変わってカーソルが移ったとき、直後の Ctrl+X を断る知らせが『<名前 |
| wn-306 W306-5 | 低 | history:7badbcc | 0/3 | 0/3 | 0/3 | 1/3 | 0/3 | メモの入力中にその行が (sub) と分かると、カーソルは隣の行に移るのに、入力欄は (sub) の行に開いたまま残る。 |
| wn-306 W306-6 | 低 | history:7badbcc, history:95ce697 | 0/3 p1 | 1/3 | 0/3 | 2/3 | 0/3 | 作業台の案内が、(sub) と分かったばかりの行をまだ指していると、そこからの ctrl+q ctrl+e で (sub |
| wn-306 W306-7 | 低 | history:1d615cf | 0/3 | 0/3 | 1/3 | 0/3 | 0/3 | README に、(sub) の行も『Both can be selected』と選べるように書いてあるが、実装では選べ |
| wn-308 W308-1 | 低 | history:f02e9ea | 0/3 p2 | 0/3 | 0/3 | 2/3 p1 | 0/3 | 異常終了した前の whatnext の tmux サーバから作業台を Y で引き継ぐと、その作業台のステータス行は作られ |
| wn-313 W313-1 | 中 | history:0a9e461 | 1/3 | 0/3 | 1/3 | 0/3 | 0/3 | 作業台の画面が作業台(sh-<id>)を映している間に案内のセッション wbguide が消えると、誰も作り直さないので |
| wn-313 W313-2 | 低 | history:0a9e461 | 3/3 | 0/3 | 3/3 | 3/3 | 1/3 | 案内の起動し直しの回数を、間隔に関係なくペインの通算で数えるので、長く動かしていて案内がたまに落ちるだけでも、通算6回目 |
| wn-313 W313-3 | 低 | history:0a9e461 | 2/3 | 0/3 | 0/3 p2 | 3/3 | 0/3 | 作業台の画面につながったあとで tmux のクライアントがシグナルで止められると、つなげなかった扱いになり、`could |
| wn-313 W313-4 | 低 | history:e2be0ce | 0/3 | 0/3 | 0/3 | 1/3 | 0/3 | 案内のセッションで利用者が分割したペイン(ctrl+q % など)が終わると、閉じずに同じコマンドで5回まで起動し直され |
| wn-313 W313-5 | 低 | history:2086680 | 1/3 | 0/3 | 0/3 | 1/3 | 0/3 | つながったあとに attach が 0 以外で終わって失敗の道に入ると、端末のタイトルを消す OSC 2 が出ず、タイト |
| wn-313 W313-6 | 低 | history:2086680 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 案内のセッションは残っているが案内のプログラムのペインがない(利用者が分割したあと案内のペインだけが閉じた)とき、案内は |

### 構成を外したときに失うもの

「固有」は、その構成だけが1回でも検出した不具合。「残りの構成」は、その構成を外した残り全部で、1回でも検出した不具合の数。

| 構成 | 固有の検出 | 残りの構成での検出 |
|---|---|---|
| code-review | 4(sk-13 S13-6、sk-16 S16-1、sk-16 S16-5、sk-16 S16-7) | 30/41 |
| security-review | 0 | 34/41 |
| mattpocock | 1(wn-306 W306-7) | 33/41 |
| perspectives | 5(sk-13 S13-4、sk-16 S16-8、wn-306 W306-5、wn-308 W308-1、wn-313 W313-4) | 29/41 |
| prove | 0 | 34/41 |

全構成を合わせて、1回でも検出した不具合: 34/41

## 余計な指摘(埋め込んでいない指摘)

1試行あたりの平均件数。分類は、同じ指摘をまとめたまとまりごとに付けたもの。「本物」は差分の内 / 外に分ける。

| 構成 | 合計 | 本物(内) | 本物(外) | 些末 | 誤り | 未確定 | 未分類 | 不具合のない題材での合計 |
|---|---|---|---|---|---|---|---|---|
| code-review | 6.1 | 0.5 | 0.0 | 4.8 | 0.6 | 0.2 | 0.0 | 8.2 |
| security-review | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| mattpocock | 8.8 | 0.3 | 0.1 | 7.9 | 0.4 | 0.1 | 0.0 | 9.7 |
| perspectives | 6.0 | 0.5 | 0.1 | 4.8 | 0.4 | 0.2 | 0.0 | 7.4 |
| prove | 0.2 | 0.1 | 0.0 | 0.1 | 0.0 | 0.0 | 0.0 | 0.2 |

## 時間とトークン(1試行あたり)

| 構成 | 時間の中央値 | 最長 | 入力の中央値 | 出力の中央値 | 費用の中央値 | 費用の合計 |
|---|---|---|---|---|---|---|
| code-review | 2.3分 | 9.8分 | 38万 | 1万 | $0.55 | $17.48 |
| security-review | 0.8分 | 1.4分 | 17万 | 0万 | $0.46 | $13.16 |
| mattpocock | 2.8分 | 13.4分 | 66万 | 1万 | $1.10 | $33.82 |
| perspectives | 1.8分 | 4.2分 | 30万 | 1万 | $0.55 | $17.40 |
| prove | 3.6分 | 14.4分 | 58万 | 1万 | $0.65 | $21.31 |

レビュー役の費用の合計 $103.17、採点 $12.21、まとめと分類 $22.81(API 換算)。

## 確かめること

- 題材の外へのアクセスの疑い: 39 件
  - clean-sk-14 code-review #2: `Bash cat /Users/masahirompp/.claude/projects/-private-var-folders-5t-j2015ppn7pj1lf0h39j3c5jm0000gn-T-rb-1t-d3kns-w-4b654a8c1c-skills/5561ad09-579e-4c10-882c-28`
  - clean-sk-14 code-review #2: `Bash sed -n 1,60p /Users/masahirompp/.claude/projects/-private-var-folders-5t-j2015ppn7pj1lf0h39j3c5jm0000gn-T-rb-1t-d3kns-w-4b654a8c1c-skills/5561ad09-579e-4c1`
  - clean-sk-14 mattpocock #1: `Bash sed -n 60,400p /Users/masahirompp/.claude/projects/-private-var-folders-5t-j2015ppn7pj1lf0h39j3c5jm0000gn-T-rb-v3u49r-y-w-bec506bdcb-skills/4e97a85b-961a-4`
  - clean-sk-14 mattpocock #1: `Bash sed -n 38,62p /Users/masahirompp/.claude/projects/-private-var-folders-5t-j2015ppn7pj1lf0h39j3c5jm0000gn-T-rb-v3u49r-y-w-bec506bdcb-skills/4e97a85b-961a-4f`
  - clean-sk-14 mattpocock #2: `Bash cat /Users/masahirompp/.claude/projects/-private-var-folders-5t-j2015ppn7pj1lf0h39j3c5jm0000gn-T-rb-1t-d3kns-w-9a3666cc12-skills/ecad7f65-d34e-4c36-a46a-17`
  - clean-sk-14 mattpocock #3: `Bash cat /Users/masahirompp/.claude/projects/-private-var-folders-5t-j2015ppn7pj1lf0h39j3c5jm0000gn-T-rb-1t-d3kns-w-be873f2f57-skills/6cdb034c-cf26-4254-ba3c-25`
  - clean-sk-14 perspectives #1: `Bash cat /Users/masahirompp/.claude/projects/-private-var-folders-5t-j2015ppn7pj1lf0h39j3c5jm0000gn-T-rb-v3u49r-y-w-90adaff96e-skills/454c5aae-d787-4d99-8be3-a7`
  - clean-sk-14 perspectives #2: `Bash cat /Users/masahirompp/.claude/projects/-private-var-folders-5t-j2015ppn7pj1lf0h39j3c5jm0000gn-T-rb-1t-d3kns-w-5ce0b71351-skills/6ee281b7-1c9f-4c6f-8b87-95`
  - clean-sk-16 perspectives #2: `Bash F=/Users/masahirompp/.claude/projects/-private-var-folders-5t-j2015ppn7pj1lf0h39j3c5jm0000gn-T-rb-1t-d3kns-w-ac388a4f27-skills/2aa508b1-27b5-4dac-a143-2dfc`
  - clean-sk-16 perspectives #2: `Bash cd /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-1t_d3kns/w/ac388a4f27/skills; grep -n "差分の外\|再現を試みたが\|実行で確かめていない修正\|悪用の手順\|gh issue create\|`
  - clean-wn-315 code-review #1: `Bash git log -3 --format='%h %ad %s' --date=iso; git log main -15 --format='%h %ad %s' --date=short | head -15; gh issue list --search "n 候補 先頭" --state all --l`
  - clean-wn-315 code-review #2: `Bash grep -n "ghq\|起動したディレクトリ" docs/DESIGN.md CONTEXT.md | head; gh issue list --label decision-log --limit 5 2>/dev/null | head; git log main..HEAD --format='%`
  - clean-wn-315 mattpocock #3: `Bash gh issue list -R masahirompp/whatnext --state all --search "n 候補 先頭" --limit 5 2>&1 | head; grep -n "select(\|^export function panel\|function panel" test/`
  - sk-12 mattpocock #1: `Bash cat /Users/masahirompp/.claude/projects/-private-var-folders-5t-j2015ppn7pj1lf0h39j3c5jm0000gn-T-rb-v3u49r-y-w-03be44abbb-skills/fc9b85d6-05b7-4ca1-99d2-44`
  - sk-12 mattpocock #2: `Bash cat /Users/masahirompp/.claude/projects/-private-var-folders-5t-j2015ppn7pj1lf0h39j3c5jm0000gn-T-rb-v3u49r-y-w-942483f5d2-skills/09d1c759-cd66-43f9-ba2f-9e`
  - sk-12 prove #2: `Bash mkdir -p scratch/wrap && cat > scratch/wrap/claude <<'EOF'
#!/usr/bin/env python3
import json, os, stat, sys, time
ORIG = os.environ["ORIG_FAKE"]
mode = os`
  - sk-13 mattpocock #3: `Bash cat /Users/masahirompp/.claude/projects/-private-var-folders-5t-j2015ppn7pj1lf0h39j3c5jm0000gn-T-rb-1t-d3kns-w-4a91fdc631-skills/44695631-67f5-46e6-817c-ba`
  - sk-16 perspectives #1: `Bash cd /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-v3u49r_y/w/0bd36a0933/skills; grep -n "直す前に再現する\|起きなかった: 採らない\|PR のベースのコードで\|継続の理由にしない\|回さずに`
  - sk-16 perspectives #2: `Bash cd skills/review-loop; grep -n "範囲が「差分の外」\|修正したら手順1\|再現を試みたが\|実行では示せない(\|どの修正も\|gh issue create\|判定と異なる判断\|指摘は仮説" SKILL.md; grep -n "範囲は、その問題\|再現は、分類" scri`
  - wn-306 code-review #1: `Bash git log -3 --format='%h %ad %s' --date=short; gh issue view 305 --json title,body,createdAt 2>/dev/null | head -50`
  - wn-306 mattpocock #1: `Bash cat docs/agents/issue-tracker.md | head -30; gh issue view 305 --repo masahirompp/whatnext --comments 2>&1 | head -150; cat biome.json`
  - wn-306 mattpocock #1: `Bash cat /Users/masahirompp/.claude/projects/-private-var-folders-5t-j2015ppn7pj1lf0h39j3c5jm0000gn-T-rb-v3u49r-y-w-70bf371831-whatnext/908d1942-4c92-4f1c-9ca7-`
  - wn-306 mattpocock #1: `Bash cat /Users/masahirompp/.claude/projects/-private-var-folders-5t-j2015ppn7pj1lf0h39j3c5jm0000gn-T-rb-v3u49r-y-w-70bf371831-whatnext/908d1942-4c92-4f1c-9ca7-`
  - wn-306 mattpocock #1: `Bash cat /Users/masahirompp/.claude/projects/-private-var-folders-5t-j2015ppn7pj1lf0h39j3c5jm0000gn-T-rb-v3u49r-y-w-70bf371831-whatnext/908d1942-4c92-4f1c-9ca7-`
  - wn-306 mattpocock #2: `Bash gh issue view 305 --json title,body,labels,comments --jq '{title,body,labels:[.labels[].name],comments:[.comments[].body]}'; ls docs/agents; cat biome.json`
  - wn-306 mattpocock #2: `Bash sed -n 20,400p /Users/masahirompp/.claude/projects/-private-var-folders-5t-j2015ppn7pj1lf0h39j3c5jm0000gn-T-rb-v3u49r-y-w-df338ede0a-whatnext/bf35c1bb-8a2b`
  - wn-306 mattpocock #2: `Bash grep -n "marker" src/ops/*.ts | head; gh issue view 305 --json title,labels,milestone 2>&1 | head -5; npm test 2>&1 | tail -6`
  - wn-306 mattpocock #3: `Bash gh issue view 305 --json title,body,labels,comments --jq '{title,body,labels:[.labels[].name],comments:[.comments[].body]}'; ls CODING_STANDARDS.md CONTRIB`
  - wn-306 mattpocock #3: `Bash sed -n 1,400p /Users/masahirompp/.claude/projects/-private-var-folders-5t-j2015ppn7pj1lf0h39j3c5jm0000gn-T-rb-1t-d3kns-w-38af6e6718-whatnext/24239c3c-5145-`
  - wn-306 perspectives #1: `Bash cat /Users/masahirompp/.claude/projects/-private-var-folders-5t-j2015ppn7pj1lf0h39j3c5jm0000gn-T-rb-v3u49r-y-w-e0e56fc323-whatnext/567ec2df-da55-4e76-83ac-`
  - wn-308 mattpocock #1: `Bash grep -n '窓' docs/PRODUCT.md | head -20; grep -n -A3 '作業台の画面' CONTEXT.md | grep -n -i 'avoid' ; gh issue list -R masahirompp/whatnext --search 'strftime OR `
  - wn-308 mattpocock #2: `Bash gh issue list -R masahirompp/whatnext --state all --search "split 作業台 キー" --limit 10 2>&1 | head; ls CODING_STANDARDS.md CONTRIBUTING.md 2>&1; ls docs/adr `
  - wn-308 mattpocock #3: `Bash sed -n 12,30p test/e2e/workbench.test.ts; grep -n "setSessionName\|@wn_name" lib/tmux/tmux.ts src -r | head; gh issue list -R masahirompp/whatnext --search`
  - wn-308 mattpocock #3: `Bash grep -n "status\|workbenchOptions\|describe\|it(" lib/tmux/tmux.test.ts | head -30; sed -n 320,345p lib/tmux/tmux.ts; gh issue list -R masahirompp/whatnext`
  - wn-313 mattpocock #1: `Bash sed -n 1,60p docs/lib/tmux.md; grep -rn "wn_req_\|SIGUSR2\|'@wn_pid'\|@wn_pid" src lib --include=*.ts | grep -v test | head; grep -n "process.env\|WHATNEXT`
  - wn-313 mattpocock #1: `Bash gh issue list -R masahirompp/whatnext --state all --limit 8 --search "wbguide OR 案内のセッション OR exec" 2>&1 | head; grep -rn "wn_respawned\|wn_guide_died" docs`
  - wn-313 mattpocock #1: `Bash grep -n "pane-died\|run-shell\|detach-client\|detach'" -r lib/tmux/tmux.ts src | head -20; gh issue list --label decision-log --state all --limit 8 2>/dev/`
  - wn-313 mattpocock #3: `Bash ls docs docs/lib docs/adr | head -60; ls CODING_STANDARDS.md CONTRIBUTING.md biome.json* 2>/dev/null; ls .claude/skills; gh issue list --search "wbguide OR`
  - wn-313 mattpocock #3: `Bash grep -rn "SIGUSR2\|wn_req_" lib src | head; grep -n "'agentview'\|=== '" src/ops/app.ts | sed -n 1,20p; grep -n "workbenchOptions" src/cli/*.ts; gh issue l`
- 作業ツリーを変えた試行(prove 以外): 0 件
- 採点役の引用が、レビューの出力に見つからなかった件数: 0


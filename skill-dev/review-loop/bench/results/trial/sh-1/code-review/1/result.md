差分は `skills/housekeeping/scripts/scan.sh` の1ファイルだけで、指摘は4件です。上位2件は旧版（main）と新版（HEAD）を使い捨てリポジトリで走らせて再現を確認しました。既存の `skill-dev/housekeeping/test.sh` は新版でも「全件成功」になり、どちらも検出しません。

4 findings, most severe first:

1. `skills/housekeeping/scripts/scan.sh:93`: verify_pr_merged の祖先判定で引数の向きが逆になり(旧: sha が oid の祖先 → 新: is_ancestor "$oid" "$sha")、マージ後に追加コミットがあるブランチが delete 候補になる。

   Failure scenario: PR #1 が squash マージされた後、同じブランチに未マージのコミットを1件積んで push した状態で走査する。旧版は「keep: PR #1 のマージ後に追加コミットが 1 件ある」だが、新版はローカルもリモートも「delete: PR #1 マージ済み」になる。承認すると apply.sh が git branch -D と push --force-with-lease で消し、未マージのコミットを指す ref がローカルとリモートの両方から無くなる。逆に、手元が PR の head より古いだけのブランチ(旧版は delete)は「keep: 追加コミットが 0 件ある」という矛盾した理由で残り続ける。SKILL.md 93行目と scan.sh 223行目の「先端が PR の head に含まれる」とも食い違う。

2. `skills/housekeeping/scripts/scan.sh:82`: 存在する ref だけを rev-list に渡す処理と、失敗・空のときに error で止まるガードを削ったため、既定ブランチのローカルかリモートの片方が無いと first-parent 一覧が空のまま判定が進む。

   Failure scenario: ローカルの main を消して origin/main だけがあるリポジトリで走査する。rev-list は bad revision で失敗して何も出さず(stderr は捨てている)、first-parent ファイルは空になる。on_first_parent は常に 1 を返すので、main に含まれる PR なしブランチがすべて「delete: merge コミットで main に取り込み済み」になる。旧版では、作成直後で未着手のブランチは「ask: 未着手の可能性」だった。個別確認のはずの行が、誤った理由つきで一括承認の区分に入る。

3. `skills/housekeeping/scripts/scan.sh:122`: 「first-parent 履歴を読めない」の分岐(on_fp > 1)は、rev-list の失敗を検出できず実質的に到達しない。

   Failure scenario: リダイレクトがファイルを必ず作るので、rev-list が失敗しても grep は 2 ではなく 1 を返す。85行目のコメント「それ以外は履歴を読めない」が約束する keep 側への倒し込みは働かず、読めない履歴と「first-parent 上に無い」を区別できない。旧版はこれを rev-list の終了コードと [ -s ] で止めていた。grep の終了コードに頼らず、rev-list の成否を直接確かめるのが根本の直し方。

4. `skill-dev/housekeeping/test.sh:62`: 削除可否を決める判定を書き換えたのに、向きの逆転と ref の欠落を区別できるテストケースが無い。

   Failure scenario: MERGED の PR はすべて add_pr に git rev-parse <branch> を渡すので oid と sha が等しく、祖先判定はどちら向きでも真になる。ローカルの既定ブランチが無いケースも無い。そのため上の2件が入った状態でも test.sh は全件成功する。「マージ後に追加コミットあり → keep」「手元が PR の head より古い → delete」「ローカル main なしで fresh → ask」の3ケースが要る。

`is_ancestor` と `on_first_parent` への切り出し自体と、`merged_into_default` の書き換えは挙動が変わっておらず妥当です。問題は93行目の引数の取り違えと、82行目でガードごと削った簡略化の2点です。規約の観点では、リポジトリ内に CLAUDE.md は無く、ユーザーレベルの CLAUDE.md は応答方針のみでコードへの規則が無いため、指摘はありません。

再現用の一時ディレクトリ `/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/hkrev.j6frxy` が残っています。削除コマンドが安全チェックで拒否されたためで、不要なら手動で消してください。リポジトリの作業ツリーは変更していません。

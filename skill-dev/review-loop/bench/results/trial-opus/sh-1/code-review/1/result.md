レビュー対象は `main...HEAD` の差分で、変更は `skills/housekeeping/scripts/scan.sh` の 1 ファイルです。コミットメッセージは「読みやすくする」となっていますが、実際には判定の動作が 2 か所で変わっています。いずれも消してはいけないブランチやリモートブランチを `delete` 判定にする方向に倒れます。

- **祖先判定の向きが逆になった。** `merge-base --is-ancestor "$sha" "$oid"` が `is_ancestor "$oid" "$sha"` に置き換わり、引数の順が入れ替わっています。
- **ref が欠けたときの扱いが変わった。** first-parent 履歴を取る前の ref の存在確認と、読めないときに止める処理が消えました。ローカルに `main` が無いなど ref が 1 つ欠けただけで履歴が空になり、`delete` 判定に倒れます。手元で `git rev-list --first-parent <存在しない ref> refs/heads/main --` を実行すると、`fatal: bad revision` で終了コード 128 になることを確かめました。

`skill-dev/housekeeping/test.sh` は全件成功します。ただしテストは「ローカルの先端と PR の head が同じ」場合と「ローカルとリモートの両方に `main` がある」場合しか作っていないので、どちらの退行も検出できません。CLAUDE.md はユーザー用の 1 つだけで、コードの規約は書かれていないため、規約の観点からの指摘はありません。

8 findings, most severe first:

1. `skills/housekeeping/scripts/scan.sh:93`: verify_pr_merged の祖先判定の引数が逆になった。元は「手元の先端 sha が PR head oid の祖先か」だったが、今は「oid が sha の祖先か」を見ているので、マージ後に追加コミットがあるブランチが delete 判定になる。

   Failure scenario: PR #N がマージされた後、同じローカルブランチ(または worktree)で 2 件コミットする。oid は sha の祖先なので is_ancestor "$oid" "$sha" が真になり、'delete PR #N マージ済み' と出る。apply.sh がブランチと worktree ごと消し、未 push のコミットが失われる。SKILL.md の表にある「マージ後に追加コミットがある → keep」に反する。

2. `skills/housekeeping/scripts/scan.sh:230`: 同じく逆になった判定がリモートブランチの経路でも使われる。マージ後に誰かが push したコミットのあるリモートブランチが delete 候補になる。直前のコメント(223 行目)「リモートの先端が PR の head に含まれるものだけ」とも食い違う。

   Failure scenario: PR マージ後に共同作業者が origin/feature へ追加で push する。リモートの先端 sha の祖先に oid があるので delete になり、apply.sh の git push :refs/heads/feature で共有リモートからそのコミットが消える。--force-with-lease は走査時点の sha と比べるだけなので止まらない。

3. `skills/housekeeping/scripts/scan.sh:93`: 逆の判定のせいで、手元が PR head より古いだけのブランチが keep になり、理由が「追加コミットが 0 件ある」という矛盾した文になる。

   Failure scenario: PR の head が別の端末から進められてマージされ、手元のブランチは古い先端のまま。sha は oid の祖先だが oid は sha の祖先ではないので else 側に進み、git rev-list --count oid..sha が 0 を返して 'keep PR #N のマージ後に追加コミットが 0 件ある' と出る。消してよいブランチが残り、理由も誤っている。

4. `skills/housekeeping/scripts/scan.sh:82`: 存在する ref だけを rev-list に渡す絞り込みが消えた。refs/heads/$default か refs/remotes/$hk_remote/$default のどちらかが無いと、rev-list 全体が fatal(128)で失敗して first-parent ファイルが空になる。

   Failure scenario: ローカルの main を消して origin/main だけで運用しているリポジトリで、PR の無いブランチ fresh(main の先端から作っただけで未着手)を走査する。first-parent ファイルが空なので grep は 1 を返し、on_fp=1 になる。merged_into_default は真なので、'ask 未着手の可能性' のはずが 'delete merge コミットで取り込み済み' と誤判定される。fast-forward で取り込んだブランチの理由も誤る。

5. `skills/housekeeping/scripts/scan.sh:82`: 履歴を読めないときに止める処理(`[ -s ] || { echo error; exit 1; }`)が消え、rev-list の失敗が 2>/dev/null で握りつぶされたまま走査が続く。

   Failure scenario: 既定ブランチ名は gh から取れたが、fetch の失敗などで refs/remotes/origin/<default> がまだ無い。以前は「error: main の履歴を読めない」で止まっていたが、今は空の履歴のまま全ブランチを判定し、上の誤った delete がそのまま出力される。

6. `skills/housekeeping/scripts/scan.sh:122`: on_fp が 1 より大きくなる経路(「first-parent 履歴を読めない」で keep)に到達しなくなった。grep が 2 を返すのはファイルが無いときだけだが、82 行目のリダイレクトが必ずファイルを作る。84 行目のコメント「それ以外は履歴を読めない」も実態と合わない。

   Failure scenario: rev-list が失敗しても first-parent ファイルは空のまま存在するので、grep は 2 ではなく 1 を返す。読めない状態が「first-parent 上に無い」と区別されず、安全側の keep に倒れる設計が働かない。

7. `skill-dev/housekeeping/test.sh:59`: マージ後に追加コミットがあるケースと、ローカルかリモートの既定ブランチが無いケースのテストが無い。今回の 2 つの退行を検出できない。

   Failure scenario: add_pr はどれも headRefOid を手元の先端と同じにしており、ローカルにもリモートにも main がある。is_ancestor の向きが逆でも、ref の絞り込みが消えても全件成功する(実際に test.sh を実行して確認した)。

8. `skills/housekeeping/scripts/scan.sh:82`: 根本的な対処は、元の「存在する ref だけを集めて渡し、結果が空なら止める」を残すこと。ref を全部渡して rev-list に和集合を任せる書き方は、ref が 1 つ欠けただけで全体が失敗するので、git の動作を前提にした読みやすさのための変更が成り立っていない。

   Failure scenario: ローカルだけのリポジトリや、ローカルの main を消した運用など、ref が片方だけの環境は普通にある。その環境で毎回 first-parent の判定が壊れる。リファクタリングで動作を変えた分、レビューと回帰テストの負担が増える。

修正としては、93 行目を `is_ancestor "$sha" "$oid"` に戻すことと、存在する ref の絞り込みと空のときに止める処理を元に戻すことを勧めます。あわせて、上の 2 ケースを `test.sh` に足すと再発を防げます。

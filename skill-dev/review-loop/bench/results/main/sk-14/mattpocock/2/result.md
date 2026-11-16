Standards と Spec の2軸のサブエージェントを並列で走らせています。完了通知を待って集約します。

Standards 軸のレビューは終わりました。Spec 軸のレビューはまだ実行中です。2つの報告がそろってから、まとめて提示します。

`git diff main...HEAD`(コミット be0ad06 の1件)を、Standards と Spec の2つの軸でレビューしました。Issue はないので、Spec はコミットメッセージを仕様として扱いました。どちらの軸でも `skill-dev/housekeeping/test.sh` を作業ツリーの外で実行し、全件成功しています。作業ツリーには触れていません。

## Standards

**文書化された規約へのハード違反はありません。** リポジトリにある規約の文書は README.md だけなので、既存スクリプトの書き方も慣習として照らし合わせました。

規約・慣習に沿っている点:
- **lib.sh**: 共通関数の `hk_` 接頭辞、冒頭の環境変数一覧への追記、`local` と代入を分けて終了コードを保つ書き方が、既存と揃っています。
- **scan.sh**: エラーは `error: ...` を stderr に出して `exit 1` する既存の書式どおりです。
- **test.sh**: README の「housekeeping は test.sh で検証する」に従っています。

判断の問題(baseline smell):
1. **possible Duplicated Code**(`skills/housekeeping/scripts/lib.sh`、`scan.sh`、`SKILL.md`)
   - 既定値の連鎖 `${HOUSEKEEPING_TMPDIR:-${TMPDIR:-/tmp}}` が、`hk_mktemp_dir` と scan.sh のエラーメッセージに別々に書かれています。SKILL.md にも同じ規則を文章で書いています。
   - どこかを直し忘れると、エラーに出る場所と実際に作る場所が食い違います。`hk_tmp_base` のような関数で一か所にまとめる案があります。
2. **置き場所**(`lib.sh`): lib.sh は「scan.sh と apply.sh の共通部分」と名乗っていますが、`hk_mktemp_dir` を使うのは scan.sh だけになりました。将来ほかでも使うと見て lib.sh に置く判断も成り立つので、軽微です。
3. **コメントの書式**(`lib.sh`): 既存の関数コメントは `# hk_path_in_use <path> <process-cwds>: ...` のように名前と引数から書き始めています。`hk_mktemp_dir` だけがこの形になっていません。
4. **テストとコメントのずれ**(`skill-dev/housekeeping/test.sh`): コメントは「HOUSEKEEPING_TMPDIR の下に作り、終了時に消す」ですが、確かめているのは `hk-tmp` が最後に空であることだけです。

**apply.sh を変数に持たせた変更は、挙動を保っています。**
- 入力が空でも、`printf` が出す空行は awk の条件に合わないので、結果は変わりません。
- `$(...)` が落とす末尾の改行は、`printf '%s\n'` が付け直します。
- `set -e` を使っていないので、`grep` が1件も当てなくても止まりません。

## Spec

**仕様の4項目はどれも実装されています。** ただし、テストのうち2件は主張していることを検証できていません。

**(c) 実装済みに見えるが問題がある**
1. > 「test.sh: …apply.sh が TMPDIR に依存しないことを検証」
   - macOS のテンプレートなしの `mktemp` は TMPDIR を見ません。手元でも `TMPDIR=/no-such mktemp` を実行して確かめ、rc=0 で `/var/folders/...` に作られました。
   - そのため、`TMPDIR="$root/no-such-dir"` を渡す今のテストは、変更前の apply.sh でも通るはずです。変更前の版で実際に流してはいません。
   - 回帰テストとして効かせるには、PATH の先頭に必ず失敗する偽の `mktemp` を置く必要があります。
2. > 「scan.sh: 一時ディレクトリを HOUSEKEEPING_TMPDIR → TMPDIR → /tmp の下に…作り」
   - 片付けのテストは `hk-tmp` が空であることしか見ないので、scan.sh が別の場所に作っても通ります。
   - TMPDIR へのフォールバックと /tmp へのフォールバックは、どちらも検証されていません。
   - 「作れない場合」のテストそのものは妥当です。rc≠0、stdout が空、エラー文言の三つを確かめています。

**(a) 欠けている要件**: ありません。スクリプト側の mktemp は `hk_mktemp_dir` 1か所にまとまっています。

**(b) スコープクリープ**: 実質的なものはありません。

**SKILL.md の案内**
- scan.sh の案内は、そのまま実行できて正確です。
- apply.sh は「同じように `!` で」とあるだけです。承認済みの行を標準入力に流す具体的なコマンド(`… | <skill-dir>/scripts/apply.sh`)を書いておくと、ユーザーがそのまま実行できます。

**仕様の解釈**: HOUSEKEEPING_TMPDIR が設定されていて書けない場合、TMPDIR に落ちずに止まります。仕様の「→」を「未設定なら次」と読めば正しく、SKILL.md の書き方とも一貫しています。

---

**要約**: Standards は判断の問題が4件(ハード違反なし)で、最も重いのは既定値の連鎖が3か所に重複している点です。Spec は問題が2件と案内の不足が1件で、最も重いのは apply.sh の TMPDIR テストが変更前のコードでも通ってしまい、回帰を検出できない点です。

2つのサブエージェントの報告が揃ったので、集約して報告します。

# レビュー結果: `git diff main...HEAD`(983110a、`skills/housekeeping/scripts/scan.sh`)

仕様は issue や仕様ファイルが無いため、コミットメッセージ(「挙動は変えない」)を仕様として扱いました。結論を先に言うと、**「挙動は変えない」は 2 か所で成り立っておらず、どちらも消すべきでないブランチを `delete` と判定する方向の変化です**。このままのマージは勧めません。

## Standards

文書化された標準は、README.md・SKILL.md・`.claude/settings.json` には書き方の規約が無く、拾えたのは次の 2 つです。

- `skills/housekeeping/scripts/lib.sh` 9〜12 行: 「判定の結果が空になったときは、残す側に倒す」
- `skills/housekeeping/SKILL.md` 94 行の判定表: 「PR マージ済みだが、マージ後に追加コミットがある → `keep`」

ヒアドキュメントの禁止、`set -uo pipefail`、関数コメントの形には違反がありません。

**(a) 文書化された標準への違反(厳格)**

1. **first-parent のハンク(80〜85 行): 「残す側に倒す」に反する**
   - ref の存在確認と `|| { echo "error: ..."; exit 1; }` が消え、`git rev-list` の終了コードを見なくなった。
   - 2 つの ref のどちらかが無いと rev-list は失敗して何も出さないが、リダイレクトで空の `$tmp/first-parent` は作られる。そのため `grep -qxF` は 2 ではなく 1 を返す。
   - 結果、「履歴を読めない → keep」には届かず、`delete`(merge コミットで取り込み済み)に入る。
   - 85 行のコメント「それ以外は履歴を読めない」も、この経路では成り立たない。
2. **`verify_pr_merged` のハンク(93 行): SKILL.md 94 行の表に反する**
   - 変更前は `--is-ancestor "$sha" "$oid"`、変更後は `is_ancestor "$oid" "$sha"` で、引数の向きが逆。
   - マージ後に追加コミットがあるブランチが `delete` になる(表では `keep`)。

**(b) baseline smell(判断事項)**

- **possible Mysterious Name**(73〜74 行 `is_ancestor <a> <b>`): 同じ型の位置引数が 2 つで、名前から向きが読めない。上の 2 はこの取り違えそのもの。抽出自体は Duplicated Code の解消として妥当。
- **possible Middle Man**(85 行 `on_first_parent`): 呼び出しが 1 箇所の 1 行の包みで、3 値の終了コードの説明が使う場所(118〜119 行)から離れた。軽微。

## Spec

main 版と HEAD 版をリポジトリ外の一時ディレクトリに取り出し、使い捨てリポジトリで両方を実行して比べた結果です。

**(c) 実装が誤っている要件**

1. **`verify_pr_merged` の引数が逆(93 行)** — 仕様:「`git merge-base --is-ancestor` の呼び出しを `is_ancestor` にまとめる」「挙動は変えない」
   - 実測: PR マージ後にローカルで 1 コミット足したブランチは、main 版 `keep`(追加コミットが 1 件)→ HEAD 版 `delete`(PR マージ済み)。
   - 実測: PR の head より手前にあるブランチは、main 版 `delete` → HEAD 版 `keep`(「追加コミットが 0 件ある」)。
   - 推測(未実測): 同じ関数を通るリモートブランチも、マージ後に追加コミットが push されていれば `delete` になる。
2. **既定ブランチの ref が片方しか無いと first-parent 履歴が空になる(82 行)** — 仕様:「first-parent の履歴を、rev-list の1回の呼び出しで作る」「挙動は変えない」
   - 実測(リモート追跡だけ、ローカルだけ、の両方で同じ): 作成直後で未着手のブランチは、main 版 `ask` → HEAD 版 `delete`。SKILL.md 98 行に反する。
   - 実測: fast-forward で取り込んだブランチは `delete` のままだが、理由が「merge コミットで取り込み済み」に変わる。
   - 終了コードは 0 で、stderr にも何も出ない。
   - 両方の ref が無い場合と履歴が空の場合は未実測(コードを読んだ判断)。

**(b) 求められていない変更**

- `verify_pr_merged` の is-ancestor に `2>/dev/null` が付いた(変更前は stderr が出ていた)。実害は小さい。
- `error: $default の履歴を読めない` と `exit 1` の削除。

**(a) 欠けている要件**

- なし。`is_ancestor` と `on_first_parent` の切り出し、rev-list の 1 回化はどれも入っている。
- `merged_into_default` と、`on_first_parent` の呼び出し側(118〜119 行)のハンクは等価。

**test.sh が捕捉できるか**

- 実測: main 版と HEAD 版の両方で 70 件 ok。コミットメッセージの「全件成功」は事実だが、上の 2 件は検出できない。
- MERGED の PR はすべて `headRefOid` がローカルの先端と同じで、引数の順序が効かない。
- 常に `origin/main` とローカル `main` の両方がある。

## まとめ

Standards: 厳格 2 件・判断事項 2 件(最悪は、rev-list の失敗が空ファイル経由で `delete` に倒れること)。Spec: 誤実装 2 件・scope creep 2 件(最悪は、引数の逆転でマージ後の追加コミットを持つブランチが `delete` になること)。

## 検討材料

- **テストの信頼度**: 「test.sh 全件成功」は今回、等価性の根拠になっていませんでした。「マージ後に追加コミットがあるブランチ」と「既定ブランチの ref が片方だけ」のケースを先に足し、main 版で通ることを確かめてから整理し直すのが、同じ見落としを防ぐ順序です。
- **`is_ancestor` の抽出を残すか**: 抽出自体は妥当ですが、今回の誤りはまさにこの位置引数の取り違えです。コメントに頼らず、`is_ancestor_of <子孫> <祖先>` のように向きが名前に出る形にするかは検討の余地があります。
- **rev-list の 1 回化**: もとから rev-list は 1 回で、消えたのは ref の存在確認のループです。片方の ref が無い環境(ローカルに既定ブランチを持たない clone など)は普通にありうるので、このループとエラー終了は戻すべきだと考えます。

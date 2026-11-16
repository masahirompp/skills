証明できた指摘はありません。

試したことは次のとおりで、いずれも変更の意図どおりに動きました。

| 試したこと | 結果 |
|---|---|
| `skill-dev/housekeeping/test.sh`(`TMPDIR=scratch`、macOS の `/bin/bash` 3.2.57) | 全件成功 |
| `TMPDIR=/nonexistent` で `scan.sh` | fetch の前に `error: 一時ディレクトリを作れない(/nonexistent)…` を出し、rc=1 で止まった |
| `sandbox-exec` で `/private/var/folders` と `/private/tmp` への書き込みを禁じ、TMPDIR を外して `scan.sh` | `mktemp: … Operation not permitted` のあと同じエラーを出し、rc=1 で止まった。`/prs.json` へは書きに行かなかった |
| 同じサンドボックスで `TMPDIR` を書き込める場所にして `scan.sh` | 正常に判定し、rc=0 |
| ローカルの `main` を消してから `scan.sh` | 止まらず、取り込み済みの `feat` を正しく `delete` と判定した。コミットメッセージにある、すべてが「merge コミットで取り込み済み」になる誤りは出なかった |
| `hk_parse_action` に複数行・空・タブなし・未知の action を渡す | どれも `keep` に倒れた。理由の中のタブはそのまま残った |
| `hk_is_protected` で git config の `rel/*`、空白を含むパターン、`set +f` のあとの `HOUSEKEEPING_PROTECT='*'` を試す | 期待どおりに照合した(`two words` は一致し、`two` は一致しない)。ファイル名への glob 展開も起きなかった |
| `scripts/` の中でヒアドキュメントとヒアストリングを grep する | 残っていなかった |

確かめられなかったことが1つあります。`hk_process_cwds` の「自分自身が lsof に出るか」という確認は、自分のプロセスは見えるのにほかのプロセスは隠れる環境だと、すり抜けるはずです。そうなると、ほかのプロセスが使っている worktree を「使用中でない」と判定します。ただ、この環境では lsof がすべてのプロセスを見られました(586 件)。偽の lsof を作って示しても実際の挙動の証明にはならないので、指摘には入れていません。

作業用のリポジトリとスクリプトは `scratch/fx/` に残っています。

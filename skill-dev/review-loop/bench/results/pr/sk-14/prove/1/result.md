証明できた指摘は1件です。変更の中心であるサンドボックス対策は実際に効いていて、壊せませんでした。

## 指摘1: 一時ディレクトリを作れないとき、止まる前に `git fetch --prune` でリモート追跡ブランチを消している

SKILL.md に今回足した「作れなければ何もせずに止まる」と、実際の挙動が合っていません。scan.sh は `git fetch --prune` を実行してから一時ディレクトリを作るので、error で止まった時点で追跡ブランチはもう消えています。

**実行したコマンド**

`scratch/repro-scan-prune.sh` の内容です。bare リポジトリを origin にし、`feature-x` を push して fetch します。そのあとリモート側でだけ `feature-x` を消し、`HOUSEKEEPING_TMPDIR` に存在しないディレクトリを渡して scan.sh を実行します。
```
cd scratch && ./repro-scan-prune.sh
```
中で scan.sh を呼んでいる行:
```
HOUSEKEEPING_TMPDIR="$w/no-such-dir" HOUSEKEEPING_PR_JSON=/dev/null "$scripts/scan.sh"; echo "scan_rc=$?"
```

**出力**
```
--- before: refs/remotes
refs/remotes/origin/HEAD
refs/remotes/origin/feature-x
refs/remotes/origin/main
--- scan
mktemp: mkdtemp failed on /private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-pn2pr0k5/w/101e875af0/skills/scratch/work-prune/no-such-dir/housekeeping.fMEIDT: No such file or directory
error: 一時ディレクトリを作れない(/private/var/folders/5t/j2015ppn7pj1lf0h39j3c5jm0000gn/T/rb-pn2pr0k5/w/101e875af0/skills/scratch/work-prune/no-such-dir)。HOUSEKEEPING_TMPDIR で書き込める場所を指定する
scan_rc=1
--- after: refs/remotes
refs/remotes/origin/HEAD
refs/remotes/origin/main
```

**出るべきだった出力**

「何もせずに止まる」が正しいなら、after は before と同じになるはずです。`refs/remotes/origin/feature-x` が残っていなければいけません。

```
--- after: refs/remotes
refs/remotes/origin/HEAD
refs/remotes/origin/feature-x
refs/remotes/origin/main
```

**重さ**:低めです。`fetch --prune` は SKILL.md がもともと認めている scan.sh の副作用で、消えるのはリモートで既に消えたブランチの追跡 ref だけです。直し方は2つあります。`hk_mktemp_dir` を fetch より前に移すか、SKILL.md の記述を実際の挙動に合わせるかです。

## 試したが壊れなかったもの(指摘ではありません)

- **想定したサンドボックスでの走査**:`sandbox-exec` を使い、`/var/folders/.../T`・`/tmp`・`/var/tmp` への書き込みを禁じました。そのうえで `TMPDIR` だけを書き込める場所にしました。
  - 新しい scan.sh:rc=0 で正しく TSV を出し、一時ディレクトリも残しませんでした。
  - 旧版:`cp: /prs.json: Read-only file system` や `/wt: Read-only file system` が出ました。コミットメッセージにある「空のパスのまま書きに行く」不具合です。
  - つまり、修正は狙いどおりに効いています。
- **apply.sh が本当に一時ファイルなしで動くか**:この環境の bash は 3.2 で、ヒアドキュメントを一時ファイルで実装しています。そこで `TMPDIR`・`/tmp`・`/var/tmp` をすべて書けなくして、保護対象のブランチを偽装した行を流しました。結果は `skipped	branch entire/checkpoints/v1: 保護対象` で、正しく拒否されました。bash は最後に作業ディレクトリへ一時ファイルを作るため、git が動ける環境なら壊れません。
- **既存のテスト**:`skill-dev/housekeeping/test.sh` は「全件成功」でした。

再現スクリプトと作業用のリポジトリは `scratch/` に置いたままです。

レビューが終わりました。重大な問題が1件あります。apply.sh はこの差分のあとも一時ファイルを使っており、作れない環境では保護対象のブランチと使用中の worktree を消しうる状態です。

前提として、コミットメッセージにある「macOS の mktemp はテンプレートなしだと TMPDIR を見ない」は手元で確かめました(`TMPDIR=<別dir> mktemp -d` でも `/var/folders/.../T/tmp.XXXX` が返る)。そのため `hk_mktemp_dir` でテンプレートを明示する方針と、`|| exit 1` で止める修正自体は妥当です。ルート直下の `/prs.json` に書きに行く不具合は、これで確実に塞がっています。

## 正確性 / セキュリティ

- **`skills/housekeeping/SKILL.md:98`、`skill-dev/housekeeping/test.sh:185`: 「apply.sh は一時ファイルを使わない」は事実と違う**
  - macOS 標準の bash 3.2 は、ヒアドキュメント(`<<EOF`)を実行するたびに一時ファイルを作ります。apply.sh が呼ぶ `lib.sh` の `hk_is_protected`(`lib.sh:48`)と `hk_path_in_use`(`lib.sh:67`)は、どちらもヒアドキュメントを使っています。
  - `sandbox-exec` で書き込みを禁止して試すと、`cannot create temp file for here document: Read-only file system` で失敗しました。
  - test.sh:186 が通るのは、bash が書けない `$TMPDIR` を飛ばして `/tmp` や `/var/tmp` に逃げるからです。「TMPDIR に依存しない」ことの証明にはなっていません。

- **`skills/housekeeping/scripts/lib.sh:43-50`: 一時ファイルを作れないと、保護の判定が「保護しない」側に倒れる(最重要)**
  - ヒアドキュメントが失敗すると `while read` が1行も読まずに終わり、`return 1`(保護対象ではない)が返ります。
  - 実測では `hk_is_protected entire/checkpoints/v1 main` が `NOT_PROTECTED` を返しました。
  - そのまま進むと、`apply.sh:53` と `apply.sh:65` は `entire/*` や `housekeeping.protect` で指定したブランチを、ローカルでもリモート(`git push :refs/heads/...`)でも消せます。
  - この不具合は main の時点からありますが、この差分は「一時ファイルを作れない環境」を正面から扱っているので、ここで直すべきです。
  - 直し方: ヒアドキュメントを `hk_protect_patterns "$2" | while ...` のようなパイプにするか、`case` で直接判定する。あわせて、判定に失敗したら「保護する」側に倒す。

- **`skills/housekeeping/scripts/lib.sh:64-70`、`apply.sh:42-43`: プロセスが使っているかの判定も、同じ理由で「使っていない」側に倒れる**
  - `hk_path_in_use` はヒアドキュメントが失敗すると空を返します(実測で rc=1、出力なし)。
  - 空が返ると `apply.sh:43` は「使っているプロセスなし」と判断し、`git worktree remove` に進みます。未コミットの変更は git が拒否しますが、作業中のプロセスがいる worktree は消えます。
  - 直し方: `printf '%s\n' "$2" | awk ...` に置き換える。

- **`skills/housekeeping/scripts/scan.sh:30-34`: エラー文が勧める `HOUSEKEEPING_TMPDIR` だけを設定しても、ヒアドキュメントは書けない場所に向いたまま**(可能性あり、未再現)
  - scan.sh には `read ... <<EOF` が6か所あります(98、110、156、197、203、218、222 行)。これらは `HOUSEKEEPING_TMPDIR` を見ず、`$TMPDIR` → `/tmp` → `/var/tmp` の順で場所を探します。
  - mktemp は成功したのにヒアドキュメントが失敗する、という状況が起こりえます。そうなると `st`、`action`、`reason` が空のまま判定が進みます。
  - 直し方: 一時ディレクトリを作った直後に `export TMPDIR=$tmp` とする。こうすれば bash のヒアドキュメントも同じ場所を使います。apply.sh は、上の2件をパイプに直せば一時ファイルが要らなくなります。

## 設計

- **`skills/housekeeping/scripts/scan.sh:22` と `:30`: 一時ディレクトリを作る前に `git fetch --prune` が走っている**
  - SKILL.md:98 は「作れなければ何もせずに止まる」と書いていますが、実際には fetch(リモート追跡ブランチの prune を含む)を済ませてから止まります。
  - 一時ディレクトリの作成を 19 行目の直後に移すと、副作用が出る前に止まり、文書とも一致します。

- **`skills/housekeeping/scripts/scan.sh:31`: 一時ディレクトリの場所の決め方が `lib.sh:18` と二重に書かれている**
  - `${HOUSEKEEPING_TMPDIR:-${TMPDIR:-/tmp}}` の優先順位を変えるときに、片方だけ直されてずれるおそれがあります。
  - 場所を返す関数(例 `hk_tmp_base`)を lib.sh に置き、両方からそれを使うのがよいです。

- **`skills/housekeeping/scripts/apply.sh:21`: 承認済みの行を変数で持つ変更自体は問題ない**
  - 入力が空なら `printf '%s\n' ""` が空行を1行出しますが、`$2 == k` に当たらないので影響はありません。
  - コマンド置換で末尾の改行が消える点も、行単位の処理なので問題ありません。
  - ただしコメントの「一時ファイルを使わない」は、上の理由で今のところ成り立っていません。

## テスト

- **`skill-dev/housekeeping/test.sh:172-175`: 「HOUSEKEEPING_TMPDIR の下に作る」ことを確かめていない**
  - 確かめているのは、終了後に `hk-tmp` が空であることだけです。`HOUSEKEEPING_TMPDIR` が無視されて別の場所が使われても通ります。
  - 164 行目の「存在しないディレクトリなら失敗する」テストと組み合わせれば間接的には確かめられますが、ディレクトリが作られたことを直接見ていません。

- **`skill-dev/housekeeping/test.sh:185-186`: 環境を偽装するテストとしては弱い**
  - 書き込めない場所を `TMPDIR` で指しても、bash が `/tmp` に逃げるので検証になりません。
  - macOS に限ってよいなら、`sandbox-exec -p '(version 1)(allow default)(deny file-write* (subpath "/private/tmp") (subpath "/private/var"))'` で apply.sh を実行する案があります。この条件で保護対象の行が `skipped` になることを確かめれば、上の「保護しない側に倒れる」不具合を検出するテストになります。

## 並行性 / プライバシー

- **並行性:** 新しい問題はありません。`mktemp -d` が実行ごとに別の 0700 のディレクトリを作るので、scan.sh を同時に動かしても衝突しません。trap による削除も自分のディレクトリだけが対象です。
- **プライバシー:** 新しい問題はありません。SKILL.md:35 は、ユーザーに絶対パスを展開したコマンドを示すよう案内していますが、示す相手はユーザー本人のシェルで、外部には送りません。

---

**判断の材料:** この差分が想定している状況は、「`/var/folders` には書けないが `$TMPDIR` には書ける」というサンドボックスのように見えます。その状況なら、ヒアドキュメントは `$TMPDIR` に書けるので、上の重大な問題は実際には起きません。ただし SKILL.md と test.sh は「一時ファイルに依存しない」と言い切っており、その主張が成り立たないうえ、成り立たなかったときに安全でない側に倒れます。主張を弱めて済ませるより、ヒアドキュメントをパイプに置き換えるほうが直す量が少なく、確実だと考えます。

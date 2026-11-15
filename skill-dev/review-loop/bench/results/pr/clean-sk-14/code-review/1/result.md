PR #13 の後に積まれたブランチ `housekeeping-mktemp`(`main...HEAD`、5ファイル)を対象に、8つの観点でレビューしました。テストは macOS の bash 3.2 で全件成功し、lib.sh の新しい関数も bash 3.2 で手動確認して想定どおり動きました。リポジトリ側の CLAUDE.md はありません。ユーザーの CLAUDE.md は対話の姿勢についての規約で、コードには当てはまらないため、規約違反の指摘はありません。

一番重いのは1件目です。lsof の出力に自分の PID が出るかどうかだけで「プロセスを見られる」と判定しているため、この PR が狙ったサンドボックス内の誤判定が残る可能性があります。ただし、「自分と同じサンドボックスのプロセスだけが見える」環境を実際に作っての確認はしていません。この環境では lsof で約1200プロセスが見え、PID 1 は見えませんでした。

8 findings, most severe first:

1. `skills/housekeeping/scripts/lib.sh:96`: hk_process_cwds は、lsof の一覧に自分自身($$)が出るかどうかだけで「プロセスを見られる」と判定している。自分と同じサンドボックスのプロセスだけが見える環境では、判定をすり抜けて、ほかのプロセスが使っている worktree を「使用中でない」とみなす。

   Failure scenario: Seatbelt などで lsof に見えるのが自分のプロセスと子プロセスだけのサンドボックスで、scan.sh または apply.sh を実行する。$$ は一覧に出るので cwds は空にならず、「確かめられない」の経路に入らない。別のセッションやエディタがカレントにしている clean な worktree(PR マージ済み)が delete と判定され、apply.sh の git worktree remove で消える。SKILL.md:110 の「プロセスを見られない(サンドボックスなど)ときは…残す」という説明も、この場合は成り立たない。$$ ではなく、確実に外にあるプロセス(親のログインシェルや、同じユーザーの別プロセスなど)が見えるかで判定すべき。

2. `skills/housekeeping/scripts/lib.sh:52`: git config の読み取りに失敗すると、hk_is_protected は黙ってすべてのブランチを保護対象にする。stderr に何も出さないので、原因がユーザーに伝わらない。

   Failure scenario: ~/.gitconfig が壊れている(git config が終了コード 128 を返す)。scan.sh の全ブランチが「保護対象(既定ブランチ・監査用・設定による保護)」の keep になり、リモートブランチも黙って候補から外れる。apply.sh も全行を「branch X: 保護対象」で skipped にする。安全側には倒れているが、設定ファイルの破損が原因とはどこにも出ず、エージェントとユーザーは「何も消せない」理由を誤って説明する。

3. `skills/housekeeping/scripts/scan.sh:85`: 既定ブランチの first-parent 履歴を読めないと、scan.sh 全体が error で止まる。この履歴を使うのは「PR なし」のブランチの判定だけなので、止める範囲が広すぎる。

   Failure scenario: refs/remotes/origin/main が無い(origin/HEAD は別名を指す、あるいは fetch に失敗して追跡 ref が消えている)状態で、ローカルの main も無い。classify_branch の NONE 経路には on_fp が 2 以上のとき keep にする処理があるのに、その手前の 86 行目で exit 1 する。PR があるブランチの判定や worktree の prune まで含めて何も得られない。また、on_fp>1 の分岐(123行目)は実際には通らない。

4. `skills/housekeeping/scripts/lib.sh:104`: hk_path_in_use は「確かめられない」を、pid を返すのと同じ文字列の戻り値で表している。そのため呼び出し側の理由が「使用中か、確かめられない」という曖昧な文言にまとめられている。

   Failure scenario: pid 123 が実際に使っている worktree の理由が「プロセスがカレントディレクトリとして使用中か、確かめられない(pid 123 zsh)」になり、確実に使用中なのに不確かに読める。SKILL.md は理由の部分文字列「lsof でプロセスを確かめられない」を手がかりに案内を変えるよう求めており、文言を変えると案内が壊れる。hk_process_cwds が「確かめられない」を終了コードなどで返し、呼び出し側で別の理由を出すほうが堅い。

5. `skill-dev/housekeeping/test.sh:202`: temp_usage は、行全体がコメントの行しか除外しない。行末のコメントや文字列、算術式の中にある '<<' や 'mktemp' でも誤って fail する、壊れやすい静的チェックになっている。

   Failure scenario: scan.sh に `x=$((1<<2))` と書く、または scan.sh:128 のような行末コメントに「mktemp を使わない」と書くと、ヒアドキュメントも一時ファイルも使っていないのに「一時ファイルを使う書き方がある」で FAIL する。逆に、lib.sh や apply.sh から source する別ファイルにヒアドキュメントがあっても検出できない。

6. `skills/housekeeping/scripts/scan.sh:49`: parse_pr_info はパラメータ展開で空白区切りを手作業で分けている。lib.sh 冒頭のコメントで許しているプロセス置換を使えば `read -r st num oid < <(pr_info "$name")` の1行で済み、空のときに UNKNOWN にする処理だけ足せばよい。

   Failure scenario: 同じ役割の分解処理が scan.sh(parse_pr_info)と lib.sh(hk_parse_action、hk_is_protected の手作業の行分割)に別々の書き方で3つあり、保守の手間が増えている。hk_is_protected も `rest=$(...) || return 0` で失敗を確かめたあと、`while IFS= read -r p; do ...; done < <(printf '%s\n' "$rest")` とすれば、${rest%%$'\n'*} と case による手作業の分割がいらない。

7. `skills/housekeeping/SKILL.md:72`: 「何も渡さないと、何も消さずに終わる」という説明は、標準入力が端末のときには当てはまらない。apply.sh の `input=$(grep -v '^action\t')` は端末からの入力を待って止まる。

   Failure scenario: ユーザーが案内を読んで、パイプを付けずに自分の端末で `<skill-dir>/scripts/apply.sh` を実行すると、grep が端末の EOF を待って応答しなくなる。apply.sh で、標準入力が端末なら(`[ -t 0 ]`)エラーにするか、説明を直すべき。

8. `skills/housekeeping/scripts/lib.sh:46`: hk_protect_patterns 内の `set -f` は、$(...) の中で呼ばれる前提でしか外に漏れない。また hk_is_protected のコメント「単語分割を使わない」は、hk_protect_patterns が HOUSEKEEPING_PROTECT を単語分割していることと食い違っている。

   Failure scenario: 今後 hk_protect_patterns を直接呼ぶ(デバッグ用に一覧を出すなど)と、呼び出し元のシェルに set -f が残る。その後の glob(テストの `rm -rf "$root/tmpdir"/*` など)が展開されず、意図しない動作になる。`local -` は bash 3.2 に無いので、関数の本体を ( ) にするか、前提をコメントで固定すべき。

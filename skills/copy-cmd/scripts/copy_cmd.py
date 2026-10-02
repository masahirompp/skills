#!/usr/bin/env python3
"""会話から抜き出したコマンドを整形してクリップボードに入れる。

  copy_cmd.py set     # 標準入力のコマンドを整形・登録し、全コマンドをまとめてコピー
  copy_cmd.py next    # 登録済みの次の1コマンドをコピー
  copy_cmd.py line N  # 登録済みの N 番目(1始まり)をコピー
  copy_cmd.py all     # 登録済みの全コマンドをまとめてコピーし直す

整形の規則:
  - 行末の \\ による継続行は1行につなぐ(クォートの中では \\<改行> を消すだけで空白は残す)
  - トップレベルの && で分けて1コマンド1行にする(|| ; | はそのまま)。
    まとめてコピーするときは行末に && を残して改行する。シェルは行末の && で次の行に続くので、
    途中で失敗すればそこで止まる。1つずつコピーするときは && を付けない
  - 行頭の `!`(Claude Code の bash モード)と `$ `(プロンプト)を外す。&& の後ろの ! は否定なので残す
  - コードフェンス、空行、行全体のコメントを捨てる
  - クォート・$( )・ヒアドキュメント・if / for / case / { } などの複合コマンドは分けずに1コマンドとして残す

登録はセッションごと(環境変数 CLAUDE_CODE_SESSION_ID、--session で上書き可)の一時ファイルに保存する。
環境変数 COPY_CMD_SINK にファイルパスを入れると、クリップボードの代わりにそのファイルへ書く(テスト用)。
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HEREDOC_RE = re.compile(r"<<(-?)[ \t]*(['\"]?)([A-Za-z0-9_.-]+)\2")
FENCE_RE = re.compile(r"[ \t]*(```|~~~)[^\n]*(\n|$)")
KEYWORD_RE = re.compile(r"(if|then|else|elif|fi|case|esac|for|select|while|until|do|done|\{|\}|!)(?=[\s;&|()]|$)")
OPENERS = {"if", "case", "do", "{"}
CLOSERS = {"fi", "esac", "done", "}"}
# この語の次の語もコマンドの位置にある
KEEPS_CMD_POS = {"if", "then", "else", "elif", "while", "until", "do", "{", "!"}


def parse(text):
    """シェルのクォートとネストを追いながら、論理行と && で区切ったコマンドを返す。

    要素は (コマンド, 次のコマンドと && でつながっていたか)。
    """
    text = text.replace("\r\n", "\n")
    out = []
    buf = []
    pending_heredocs = []  # (delimiter, strip_tabs)
    i, n = 0, len(text)
    quote = None  # "'", '"', '`'
    depth = 0  # $( ) や ( ) の深さ
    block = 0  # if/fi, do/done, case/esac, { } の深さ
    cmd_pos = True  # 次の語がコマンドの位置にあるか(予約語の判定に使う)
    line_start = True  # 今のコマンドが論理行の先頭から始まったか(&& の後ろではないか)

    def flush(chained=False):
        nonlocal cmd_pos, line_start
        cmd = "".join(buf).strip()
        if cmd and line_start:
            cmd = re.sub(r"^!\s*", "", cmd)
            cmd = re.sub(r"^\$\s+", "", cmd).strip()
        if cmd:
            out.append((cmd, chained))
        buf.clear()
        cmd_pos = True
        line_start = not chained

    def at_word_start():
        return not buf or buf[-1] in " \t\n;|&()"

    while i < n:
        c = text[i]

        if quote is None and (i == 0 or text[i - 1] == "\n"):
            m = FENCE_RE.match(text, i)
            if m:
                i = m.end()
                continue

        if quote == "'":
            buf.append(c)
            if c == "'":
                quote = None
            i += 1
            continue

        if c == "\\" and i + 1 < n:
            if text[i + 1] == "\n":
                i += 2
                if quote is not None:
                    continue  # クォートの中では \<改行> を消すだけ
                # 継続行: \<改行> を消し、前後に空白があれば1つにまとめる
                had_ws = bool(buf) and buf[-1] in " \t"
                while buf and buf[-1] in " \t":
                    buf.pop()
                j = i
                while i < n and text[i] in " \t":
                    i += 1
                if had_ws or i > j:
                    buf.append(" ")
                continue
            buf.append(c + text[i + 1])
            i += 2
            cmd_pos = False
            continue

        if quote is not None:  # '"' か '`'
            buf.append(c)
            if c == quote:
                quote = None
            i += 1
            continue

        if c in "'\"`":
            quote = c
            buf.append(c)
            i += 1
            cmd_pos = False
            continue

        if c == "#" and at_word_start():
            # コメントは行末まで捨てる
            while i < n and text[i] != "\n":
                i += 1
            continue

        if text.startswith("<<<", i):  # ヒアストリング。ヒアドキュメントと取り違えない
            buf.append("<<<")
            i += 3
            continue

        if text.startswith("<<", i):
            m = HEREDOC_RE.match(text, i)
            if m:
                pending_heredocs.append((m.group(3), m.group(1) == "-"))
                buf.append(m.group(0))
                i = m.end()
                continue

        if c == "\n":
            if pending_heredocs:
                # ヒアドキュメントの本文は区切り行までそのまま付ける
                buf.append("\n")
                i += 1
                while pending_heredocs and i < n:
                    end = text.find("\n", i)
                    end = n if end == -1 else end
                    line = text[i:end]
                    buf.append(line)
                    i = end + 1
                    delim, strip_tabs = pending_heredocs[0]
                    if (line.lstrip("\t") if strip_tabs else line) == delim:
                        pending_heredocs.pop(0)
                        if not pending_heredocs:
                            break
                    buf.append("\n")
                if depth == 0 and block == 0:
                    flush()
                else:
                    buf.append("\n")
                    cmd_pos = True
                continue
            i += 1
            if depth > 0 or block > 0:
                buf.append(c)
                cmd_pos = True
            else:
                flush()
            continue

        if c == "&" and text.startswith("&&", i):
            # ヒアドキュメントと同じ行の && は分けない(本文の後ろに && を置けないため)
            if depth == 0 and block == 0 and not pending_heredocs:
                flush(chained=True)
            else:
                buf.append("&&")
                cmd_pos = True
            i += 2
            continue

        if c in " \t":
            buf.append(c)
            i += 1
            continue

        if c in ";|&(":
            if c == "(":
                depth += 1
            buf.append(c)
            i += 1
            cmd_pos = True
            continue

        if c == ")":
            if depth > 0:
                depth -= 1
            buf.append(c)
            i += 1
            cmd_pos = False
            continue

        if cmd_pos and at_word_start():
            m = KEYWORD_RE.match(text, i)
            if m:
                word = m.group(1)
                if word in OPENERS:
                    block += 1
                elif word in CLOSERS and block > 0:
                    block -= 1
                buf.append(word)
                i = m.end()
                cmd_pos = word in KEEPS_CMD_POS
                continue

        buf.append(c)
        i += 1
        cmd_pos = False

    flush()
    if out:
        out[-1] = (out[-1][0], False)
    return out


def render_all(cmds):
    return "\n".join(cmd + (" &&" if chained else "") for cmd, chained in cmds)


def state_path(session):
    key = re.sub(r"[^A-Za-z0-9_-]", "_", session)
    return os.path.join(tempfile.gettempdir(), f"copy-cmd-{key}.json")


def load_state(session):
    try:
        with open(state_path(session)) as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit("copy-cmd: 登録済みのコマンドがない。先に set でコマンドを登録する")


def save_state(session, state):
    with open(state_path(session), "w") as f:
        json.dump(state, f, ensure_ascii=False)


def copy(text):
    sink = os.environ.get("COPY_CMD_SINK")
    if sink:
        with open(sink, "w") as f:
            f.write(text)
        return
    for cmd in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "-ib"]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, input=text.encode(), check=True)
            return
    sys.exit("copy-cmd: クリップボードに書くコマンド(pbcopy / wl-copy / xclip / xsel)が見つからない")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["set", "next", "line", "all"])
    p.add_argument("n", nargs="?", type=int)
    p.add_argument("--session", default=os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
    a = p.parse_args()
    if not a.session:
        # セッションを区別できないと、別のセッションの登録を next で拾ってしまう
        sys.exit("copy-cmd: セッション ID が分からない。--session で指定する")

    if a.mode == "set":
        cmds = parse(sys.stdin.read())
        if not cmds:
            sys.exit("copy-cmd: コマンドが見つからない")
        state = {"cmds": cmds, "cursor": 0}
        save_state(a.session, state)
    else:
        state = load_state(a.session)
        cmds = state["cmds"]

    if a.mode in ("set", "all"):
        text = render_all(cmds)
        copy(text)
        print(f"[copied all {len(cmds)} command(s)]")
        print(text)
        return

    if a.mode == "line":
        if a.n is None or not 1 <= a.n <= len(cmds):
            sys.exit(f"copy-cmd: 番号は 1〜{len(cmds)} で指定する")
        idx = a.n - 1
    else:  # next
        idx = state["cursor"]
        if idx >= len(cmds):
            sys.exit(f"copy-cmd: 全 {len(cmds)} コマンドをコピー済み。最初からなら line 1")

    copy(cmds[idx][0])
    state["cursor"] = idx + 1
    save_state(a.session, state)
    print(f"[copied {idx + 1}/{len(cmds)}]")
    print(cmds[idx][0])
    if idx + 1 < len(cmds):
        print(f"[next] {cmds[idx + 1][0]}")


if __name__ == "__main__":
    main()

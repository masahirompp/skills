#!/usr/bin/env python3
"""会話から抜き出したコマンドを整形してクリップボードに入れる。

  copy_cmd.py set  [--session ID]   # 標準入力のコマンドを整形・保存し、全行をコピー
  copy_cmd.py next [--session ID]   # 保存済みの次の1行をコピー
  copy_cmd.py line N [--session ID] # 保存済みの N 番目(1始まり)をコピー
  copy_cmd.py all  [--session ID]   # 保存済みの全行をコピーし直す
  copy_cmd.py normalize             # 整形結果を標準出力に出すだけ(テスト用)

整形の規則:
  - 行末の \\ による継続行は1行につなぐ
  - トップレベルの && で分割して1コマンド1行にする(|| ; | はそのまま)
  - 各行頭の `!`(Claude Code の bash モード)と `$ `(プロンプト)を外す
  - コードフェンス、空行、行全体のコメントを捨てる
  - クォート・$( )・ヒアドキュメントの中身はそのまま残す

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


def split_commands(text):
    """シェルのクォートとネストを追いながら、論理行と && で区切ったコマンドの一覧を返す。"""
    out = []
    buf = []
    pending_heredocs = []  # (delimiter, strip_tabs)
    i, n = 0, len(text)
    quote = None  # "'", '"', '`'
    depth = 0  # $( ) や ( ) の深さ

    def flush():
        cmd = "".join(buf).strip()
        if cmd:
            out.append(cmd)
        buf.clear()

    def at_word_start():
        return not buf or buf[-1] in " \t;|&()"

    while i < n:
        c = text[i]

        if quote == "'":
            buf.append(c)
            if c == "'":
                quote = None
            i += 1
            continue

        if c == "\\" and i + 1 < n:
            if text[i + 1] == "\n":
                # 継続行: \<改行> を消し、前後に空白があれば1つにまとめる
                had_ws = bool(buf) and buf[-1] in " \t"
                while buf and buf[-1] in " \t":
                    buf.pop()
                i += 2
                j = i
                while i < n and text[i] in " \t":
                    i += 1
                if (had_ws or i > j) and quote is None:
                    buf.append(" ")
                continue
            buf.append(c + text[i + 1])
            i += 2
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
            continue

        if c == "(":
            depth += 1
        elif c == ")" and depth > 0:
            depth -= 1

        if c == "#" and at_word_start():
            # コメントは行末まで捨てる
            while i < n and text[i] != "\n":
                i += 1
            continue

        if c == "<" and text.startswith("<<", i) and not text.startswith("<<<", i):
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
                flush()
                continue
            if depth > 0:
                buf.append(c)
                i += 1
                continue
            flush()
            i += 1
            continue

        if c == "&" and text.startswith("&&", i) and depth == 0:
            flush()
            i += 2
            continue

        buf.append(c)
        i += 1

    flush()
    return out


def strip_prefix(cmd):
    cmd = re.sub(r"^!\s*", "", cmd)
    cmd = re.sub(r"^\$\s+", "", cmd)
    return cmd.strip()


def normalize(text):
    text = text.replace("\r\n", "\n")
    lines = [l for l in text.split("\n") if not re.match(r"^\s*(```|~~~)", l)]
    cmds = [strip_prefix(c) for c in split_commands("\n".join(lines))]
    return [c for c in cmds if c]


def state_path(session):
    key = re.sub(r"[^A-Za-z0-9_-]", "_", session or "") or "default"
    return os.path.join(tempfile.gettempdir(), f"copy-cmd-{key}.json")


def load_state(session):
    try:
        with open(state_path(session)) as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit("copy-cmd: 保存済みのコマンドがない。先に set でコマンドを登録する")


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


def report(lines, label):
    print(label)
    for line in lines:
        print(line)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["set", "next", "line", "all", "normalize"])
    p.add_argument("n", nargs="?", type=int)
    p.add_argument("--session", default="")
    a = p.parse_args()

    if a.mode == "normalize":
        print("\n".join(normalize(sys.stdin.read())))
        return

    if a.mode == "set":
        lines = normalize(sys.stdin.read())
        if not lines:
            sys.exit("copy-cmd: コマンドが見つからない")
        save_state(a.session, {"lines": lines, "cursor": 0})
        copy("\n".join(lines))
        report(lines, f"[copied all {len(lines)} command(s)]")
        return

    state = load_state(a.session)
    lines = state["lines"]

    if a.mode == "all":
        copy("\n".join(lines))
        report(lines, f"[copied all {len(lines)} command(s)]")
        return

    if a.mode == "line":
        if a.n is None or not 1 <= a.n <= len(lines):
            sys.exit(f"copy-cmd: 番号は 1〜{len(lines)} で指定する")
        idx = a.n - 1
    else:  # next
        idx = state["cursor"]
        if idx >= len(lines):
            sys.exit(f"copy-cmd: 全 {len(lines)} コマンドをコピー済み。最初からなら line 1")

    copy(lines[idx])
    state["cursor"] = idx + 1
    save_state(a.session, state)
    report([lines[idx]], f"[copied {idx + 1}/{len(lines)}]")
    if idx + 1 < len(lines):
        print(f"[next] {lines[idx + 1]}")


if __name__ == "__main__":
    main()

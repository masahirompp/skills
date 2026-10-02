#!/usr/bin/env python3
"""copy-cmd の copy_cmd.py を検証する。クリップボードには触れない(COPY_CMD_SINK を使う)。
  python3 skill-dev/copy-cmd/test.py
"""

import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "../../skills/copy-cmd/scripts/copy_cmd.py")
sys.path.insert(0, os.path.dirname(SCRIPT))
from copy_cmd import normalize, parse, render_all  # noqa: E402


class RenderAll(unittest.TestCase):
    """まとめてコピーする内容: && でつながっていた行だけ行末に && を残す。"""

    def render(self, src):
        return render_all(*parse(src))

    def test_and_kept_at_line_end(self):
        self.assertEqual(self.render("! cd app && npm i && npm test"), "cd app &&\nnpm i &&\nnpm test")

    def test_separate_commands_not_chained(self):
        self.assertEqual(self.render("```\nnpm ci\n```\n```\nnpm run build\n```"), "npm ci\nnpm run build")

    def test_mixed(self):
        src = "brew install jq\ncorepack enable && \\\n  corepack prepare pnpm --activate"
        self.assertEqual(self.render(src), "brew install jq\ncorepack enable &&\ncorepack prepare pnpm --activate")

    def test_trailing_and_without_backslash(self):
        self.assertEqual(self.render("make &&\nmake install"), "make &&\nmake install")

    def test_heredoc_line_and_not_split(self):
        src = "cat > a <<'EOF' && echo ok\nbody\nEOF"
        self.assertEqual(normalize(src), [src])
        self.assertEqual(self.render(src), src)

    def test_stops_on_failure_in_bash(self):
        # 行末の && で次の行に続き、失敗したらそこで止まることを実際の bash で確かめる
        text = self.render("false && echo should-not-run")
        r = subprocess.run(["bash", "-c", text + "\necho after"], capture_output=True, text=True)
        self.assertEqual(r.stdout, "after\n")
        text = self.render("true && echo ran")
        r = subprocess.run(["bash", "-c", text], capture_output=True, text=True)
        self.assertEqual(r.stdout, "ran\n")


class Normalize(unittest.TestCase):
    def check(self, src, *expected):
        self.assertEqual(normalize(src), list(expected))

    def test_bang_prefix(self):
        self.check("! gh auth login", "gh auth login")
        self.check("!gh auth login", "gh auth login")

    def test_prompt_prefix(self):
        self.check("$ npm install", "npm install")
        self.check("echo $HOME", "echo $HOME")

    def test_and_split(self):
        self.check("cd app && npm install && npm test", "cd app", "npm install", "npm test")
        self.check("! cd app && npm test", "cd app", "npm test")

    def test_other_operators_kept(self):
        self.check("make || echo failed; ls | wc -l", "make || echo failed; ls | wc -l")

    def test_and_in_quotes_kept(self):
        self.check("""echo 'a && b' && echo "c && d\"""", "echo 'a && b'", 'echo "c && d"')

    def test_and_in_subshell_kept(self):
        self.check("x=$(cd a && pwd) && echo $x", "x=$(cd a && pwd)", "echo $x")

    def test_continuation_joined(self):
        self.check(
            "docker run \\\n  -p 8080:80 \\\n  -v $(pwd):/app \\\n  nginx",
            "docker run -p 8080:80 -v $(pwd):/app nginx",
        )

    def test_continuation_without_space(self):
        self.check("foo\\\nbar", "foobar")

    def test_continuation_then_and(self):
        self.check(
            "gcloud auth login \\\n  --no-launch-browser && \\\n  gcloud config set project x",
            "gcloud auth login --no-launch-browser",
            "gcloud config set project x",
        )

    def test_continuation_line_starting_with_bang(self):
        self.check("find . \\\n  ! -name '*.md'", "find . ! -name '*.md'")

    def test_code_fence_and_comments(self):
        self.check(
            "```bash\n# 依存を入れる\nnpm ci  # lockfile どおり\n\nnpm run build\n```",
            "npm ci",
            "npm run build",
        )

    def test_hash_inside_word_kept(self):
        self.check("echo ${#arr[@]} a#b 'x # y'", "echo ${#arr[@]} a#b 'x # y'")

    def test_heredoc_kept(self):
        src = "cat > a.txt <<'EOF'\nfoo && bar\n  \\\nEOF\necho done"
        self.check(src, "cat > a.txt <<'EOF'\nfoo && bar\n  \\\nEOF", "echo done")

    def test_multiline_quote_kept(self):
        self.check('git commit -m "line1\n\nline2" && git push', 'git commit -m "line1\n\nline2"', "git push")

    def test_herestring_not_heredoc(self):
        self.check("cat <<< hi && echo x\nhi\necho y", "cat <<< hi", "echo x", "hi", "echo y")


class Cli(unittest.TestCase):
    def setUp(self):
        fd, self.sink = tempfile.mkstemp()
        os.close(fd)
        self.session = f"test-{os.getpid()}"

    def tearDown(self):
        os.unlink(self.sink)
        path = os.path.join(tempfile.gettempdir(), f"copy-cmd-{self.session}.json")
        if os.path.exists(path):
            os.unlink(path)

    def run_cli(self, *args, stdin=""):
        env = dict(os.environ, COPY_CMD_SINK=self.sink)
        r = subprocess.run(
            [sys.executable, SCRIPT, *args, "--session", self.session],
            input=stdin, capture_output=True, text=True, env=env,
        )
        with open(self.sink) as f:
            return r, f.read()

    def test_set_next_line_all(self):
        r, clip = self.run_cli("set", stdin="! a && b && c\n")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(clip, "a &&\nb &&\nc")  # 末尾に改行を付けない(貼った瞬間に実行されないように)
        _, clip = self.run_cli("next")
        self.assertEqual(clip, "a")
        r, clip = self.run_cli("next")
        self.assertEqual(clip, "b")
        self.assertIn("[next] c", r.stdout)
        _, clip = self.run_cli("next")
        self.assertEqual(clip, "c")
        r, _ = self.run_cli("next")
        self.assertNotEqual(r.returncode, 0)
        _, clip = self.run_cli("line", "2")
        self.assertEqual(clip, "b")
        _, clip = self.run_cli("next")
        self.assertEqual(clip, "c")
        _, clip = self.run_cli("all")
        self.assertEqual(clip, "a &&\nb &&\nc")

    def test_empty_input_fails(self):
        r, _ = self.run_cli("set", stdin="```\n# only comment\n```\n")
        self.assertNotEqual(r.returncode, 0)

    def test_next_without_state_fails(self):
        r, _ = self.run_cli("next")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()

Review target `2` is PR #2, and its head branch is the current `workbench-split-keys`. I reviewed it with `git diff main...HEAD`, which covers commit 71d31d0 across 5 files.

I found no correctness bug that breaks behaviour. The `%%` escape is right, because status-format goes through strftime before the `#{}` placeholders are filled. The default tmux bindings for `%`, `"` and `c` stay in the prefix table: `serverConfig` only unbinds `C-j` and `j`. The two spaces the test regex expects before `·` follow from the trailing space in the `#{W:...}` loop. The full string is about 66 columns, so it fits the 80-column e2e workbench screen. The width-60 "not adopted" example also matches tmux's trimming rule (right part trimmed first, from its left): 35 + 25 = 60. What remains is wording in the permanent-layer docs, conventions, and low-severity maintenance points.

6 findings, most severe first:

1. `docs/PRODUCT.md:557`: The new text calls the tmux window list 「窓の一覧」, but in PRODUCT.md and DESIGN.md 「窓」 already means the list's scroll viewport (「窓の中央に置き」「窓から差し引く」「窓に収まる」). The same bullet's parent line also says 「作業台のウィンドウの一覧」, so one concept gets two names.

   Failure scenario: Someone writing the next cycle from the docs alone could read 「キーは窓の一覧のあとに続け」 as being about the list's scroll range. docs are the strictly maintained layer that the next cycle's input is distilled into, so a term collision carries straight into the next implementation. docs/lib/tmux.md:31 「作業台では窓の一覧のあとに」 has the same problem. Use 「ウィンドウの一覧」 consistently.

2. `docs/PRODUCT.md:558`: The rejected form is shown as a captured screen at width 60, but the adopted form is not shown at the same width, so the two cannot be compared side by side.

   Failure scenario: The project CLAUDE.md says: 「画面の見た目(列の並び、字下げ、入れ子、注記の出し方)に関わる決定は、文章の説明ではなく、等幅の画面の例を示して合意する。「採らない」と決めた案も、画面の例で「こうはならない」と見せる。」 The adopted form appears only inline in prose (`workbench: fix-login  0:zsh* 1:zsh  · ^Q% split │ ...`). Its untruncated length is about 76 columns, which is not the screen you would actually see at width 60 (cut around `^Q" sp`). The user can only picture the adopted screen in their head while comparing, which is the risk this rule exists to prevent.

3. `docs/PRODUCT.md:442`: The bottom line of the workbench side in the diagram (`0:zsh*  · ^│`) looks hand-edited to show truncation. Nothing indicates it was rebuilt from a real render.

   Failure scenario: The project CLAUDE.md says: 「画面の例は手で書かず、実際の描画(描画の関数か、画面の通しのテストで取った画面)から作る。」 The diagram adds one space of padding after `│`, which a real tmux pane does not have, so whether the cut lands at `^` depends on whether the inner width is 33 or 34. In the same diagram, docker and pnpm run in two panes, yet the window name stays `zsh` (automatic-rename would show the active pane's command). A hand-written line can make the user agree to a screen that differs from the real one by a character or two.

4. `lib/tmux/tmux.ts:340`: The key text `^Q` is hard-coded separately from the `prefix C-q` set a few lines above and from the `^Q^X help` rendering in src/ops/keys.ts (ATTACH_KEYS_HELP). The prefix and its display are no longer defined in one place.

   Failure scenario: If the prefix changes, the status line keeps showing `^Q%` and points users at a key that does not work. The claude screen's key help is passed in from src as `keysHelp`, but the workbench's is fixed inside lib, so the two follow different patterns. One fix is to build the help string from the prefix value inside workbenchOptions.

5. `lib/tmux/tmux.ts:340`: `│` and `─` in the status line are East Asian Ambiguous width characters, so terminals set to treat ambiguous characters as 2 columns disagree with tmux's width calculation.

   Failure scenario: Japanese users often set iTerm2 or similar to ambiguous = wide. There, tmux treats the 2 characters as 1 column each while the terminal draws them 2 wide, so the right end of the status line overflows and the following draw shifts. The existing `·` and `…` already carry the same risk, but this change adds two more such characters. Plain ASCII such as `split |` and `split -` avoids it.

6. `lib/tmux/tmux.ts:336`: The status-format of lib/, a promoted module, changed without a unit test in lib/tmux/tmux.test.ts. It is covered only by an e2e test that depends on a real tmux and the shell's window name.

   Failure scenario: Under the CLAUDE.md promoted-module policy (「永続層として厳格に維持する(テストを持ち越し…)」), nothing pins the value of the string lib produces: the `%%` escape, keeping GUIDE free of keys, and the separator. If someone later drops `%%` back to `%`, only e2e catches it, and e2e timeouts also absorb environment-specific window names.

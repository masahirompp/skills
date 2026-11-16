6 findings, most severe first:

1. `src/ops/app.ts:853`: In the list, `n` now preselects the cursor row's root (`rootOfSid`). If the row's location can't be resolved, for example because its worktree was deleted, that root is the raw `cwd`, which may no longer exist, and it is still placed first and selected.

   Failure scenario: A session's worktree is removed after the session moved into it. `locate` fails, so the plain location's root equals the `cwd`, and the cursor sits on that row. The user presses `n`, `Enter`, `Enter`. `claude --bg` is spawned with a `cwd` that does not exist and fails with 'claude --bg did not start a session' or ENOENT. The old default (`launchDir`) always existed. Only `Other...` checks the path with `resolveDir`; the first candidate is never checked.

2. `src/ops/app.ts:1260`: PRODUCT.md now says `ctrl+q ctrl+n` keeps the session's repo first even while `--json` is erroring, but no test covers this. The list `n` test only checks the opposite (error leads to `launchDir`).

   Failure scenario: A later change copies the `this.error ? undefined : sid` guard into `attachKey`, or makes `openNew` read `this.error` itself. While the error is shown, `ctrl+q ctrl+n` would then put `launchDir` first, against the spec text at PRODUCT.md:513, and the e2e suite would stay green.

3. `src/ops/app.ts:853`: The rule 'don't use hidden rows while erroring' is enforced at each call site (the `listKey` early return, then a separate ternary for `n`) instead of once, for example with a visible-cursor getter that returns undefined while `this.error` is set.

   Failure scenario: Each new list key that uses `this.cursor` has to remember to add the same `this.error` check. The early-return allowlist at line 823 and the ternary at line 853 already encode the same rule twice. Missing it once brings back actions on stale rows that are not shown.

4. `src/ops/app.ts:952`: While `--json` is erroring, `n` still adds every stale (hidden) row's repo from `this.rows` to the candidate list. Only the first candidate is guarded, which is inconsistent with the stated reason: 'the rows are not on screen, so don't put an unseen row's repo first'.

   Failure scenario: After the error, the user presses `n` and sees `launchDir` first, followed by repos of sessions that are not visible (and may no longer exist). This partly contradicts the reason given in PRODUCT.md for skipping the cursor row's repo.

5. `docs/PRODUCT.md:591`: The rationale is dated '2026-11-02、利用者の判断', but the commit that makes this change is dated 2026-11-15, and the last commit on main is from 11-02 and unrelated. The decision date looks wrong.

   Failure scenario: Later readers use the date to locate the decision (in issues or session logs) and find nothing for 11-02. That weakens the record that the user approved this observable behavior change, which the repo CLAUDE.md layer-2 rule (escalation to the user is required) depends on.

6. `src/ops/app.ts:944`: Candidates are deduped by exact string only. The cursor row's root for a non-git `cwd` is `realpathSync(cwd)`, while `launchDir` and the other row `cwd`s are not normalized, so the same directory can appear twice once the cursor row's root is the first entry.

   Failure scenario: whatnext is started in a symlinked non-git directory (for example under `/tmp` on macOS), and the cursor row runs in the same directory. The candidates show `private/tmp/foo` first and `tmp/foo` second for one location. The user sees two entries labeled with disambiguating parents for one directory.

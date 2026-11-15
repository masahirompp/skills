5 findings, most severe first:

1. `src/ops/app.ts:952`: openNew (the function this diff touches) collects candidates from every row in this.rows, including rows with tier === null that are not shown in the list. locations.refresh is only called for rows with tier !== null, so these rows' cwd never gets mapped to its repo root and goes in as-is.

   Failure scenario: A session that has moved into a worktree and is idle or hidden (tier null) is in --json. Pressing n puts the raw worktree path (for example .../app/.claude/worktrees/x) in the candidate list. That breaks the PRODUCT.md rule to map worktree paths back to the original repository, and it adds a candidate the user can't see in the list. Line 463 filters on tier !== null, but openNew does not.

2. `src/ops/app.ts:853`: n now depends on which row the cursor is on, but it doesn't check the guard (this.guard) that is set when the cursor moves automatically. Right after the row under the cursor leaves the list and the cursor jumps to a neighbouring row, n silently puts a different repository first.

   Failure scenario: The cursor is on a row in repo app. The update that removes that row from the list moves the cursor to the neighbouring row in lib (Ctrl+X is protected by the guard). The user presses n right away, meaning to start in app. lib is first in the candidates, and if they press Enter without noticing, the session starts in an unintended repository.

3. `test/e2e/ops.test.ts:103`: The new test only covers sessions whose cwd is a normal repository. It doesn't cover the worktree case (rootOfSid must map back to the original repo), the cursor on a (tty) row, the no-rows case, or ghq adding candidates later.

   Failure scenario: If rootOfSid stopped mapping back to the root, n with the cursor on a session that moved into a worktree would put the worktree path first and the test would still pass. Nothing guards the spec for scenario 8 that the candidate is the repository.

4. `src/ops/app.ts:823`: The guard at line 823 explicitly lets n through during the error, and line 853 checks this.error again to drop sid. The 'don't act on hidden rows during the error' decision is now split across two places.

   Failure scenario: If another key that depends on the cursor (like n) is let through during the error later, it's easy to add it only to line 823 and forget the drop at line 853, so the hidden row gets used. Making it one place, by setting `const sid = this.error ? undefined : this.cursor` once, avoids the duplicated condition.

5. `docs/PRODUCT.md:591`: The decision date added to the permanent docs, '2026-11-02、利用者の判断', doesn't match the commit date of this change (2026-11-15). It may have been copied from the previous merge commit (2026-11-02).

   Failure scenario: Under CLAUDE.md's 'ドキュメントは厳格に' (docs are kept strictly), a wrong decision date in PRODUCT.md, which is the input for the next cycle, distorts when the decision was made. It conflicts with the chronology in cycle-audit and in the decision-log issue.

I found 5 candidates, below the requested 5-to-10 range in spirit but meeting the floor. I didn't run a verification pass, so each is unconfirmed. The changed logic itself (`this.error ? undefined : sid`) looks right. The most serious finding is the first: an existing problem in `openNew`, the function this diff touches. Note that I read the target `1` as the last commit (`HEAD~1`).

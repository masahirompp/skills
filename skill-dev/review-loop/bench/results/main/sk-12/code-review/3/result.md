10 findings, most severe first:

1. `skills/review-loop/scripts/review_loop.py:249`: A config denial event with no tool_use_id puts None into `seen`, so every permission_denials entry in result that also lacks tool_use_id is silently treated as an allowed config denial (fails open).

   Failure scenario: The stream has a permission_denied event with source=config and no tool_use_id, and the result's permission_denials contains a different denial (for example a nested-sandbox denial) whose tool_use_id is also missing. `d.get("tool_use_id") not in seen` evaluates to `None not in {None}`, which is False. The denial is skipped, no permission_denied is raised, and the attempt is recorded as completed. This contradicts the stated policy of failing closed when the source is unknown.

2. `skills/review-loop/scripts/review_loop.py:309`: config_denied is a dict keyed by tool_use_id, so config denials with a missing or repeated id overwrite each other. new_config_denials slices by count, so the second and later denials never reach warn or denials.txt.

   Failure scenario: Two config denials arrive whose tool_use_id is None, or duplicated because they come from different subagents. The dict stays at one entry, so `list(values())[self.reported:]` comes back empty. The second denial (for example a blocked `gh pr diff`) is missing from both stderr and denials.txt, and the parent cannot confirm what was dropped when it follows the SKILL.md advice to check denials.txt.

3. `skills/review-loop/scripts/review_loop.py:305`: Treating every source=config denial as continue-the-attempt also lets through denials of reads a review cannot do without, so a review that saw nothing can pass as completed with no findings and make the loop look converged.

   Failure scenario: The user's deny rules happen to block `gh pr diff` or `git diff`. The child cannot read the diff and returns something like 'no changes found / no findings'. The script only logs a warn line and continues, the judge returns '## 指摘 なし', and the result is iter+1 with consecutive_failures=0. The parent sees no findings and ends the loop. Before this change it failed loudly as permission_denied.

4. `skills/review-loop/scripts/review_loop.py:805`: Because the judge's result lines are now joined, any result line after the closing fence leaves the fence in the middle of the text, so the regex that strips a trailing fence no longer matches and verdict.md keeps the stray fence and the trailing text.

   Failure scenario: The judge emits result 1 = 'Here is the verdict\n```markdown\n## 指摘 ...\n```' and result 2 = 'その内容から変わりません'. In the joined text, `\n```\s*$` does not match, so verdict ends with '```\n\nその内容から変わりません'. That broken fence and extra sentence go to stdout and verdict.md, which the parent reads.

5. `skills/review-loop/scripts/review_loop.py:242`: Applying the join-all-result-lines policy to the judge as well means an intermediate draft verdict and the final verdict both end up in the verdict when each carries the headings.

   Failure scenario: The judge emits a draft verdict with '## 指摘 / ## 競合' at turn 1 and the final verdict at turn 2. min(start) points at the draft's first heading, so verdict.md contains two sets of sections with different content, and the parent cannot tell which F1 or C1 is the real one. Before this change only the last result was used, so this did not happen. The review side can also end up passing duplicated report bodies to the judge.

6. `skills/review-loop/scripts/review_loop.py:786`: Switching the judge to stream-json makes StreamTail.poll read only up to the last newline, so a final result line written without a trailing newline is now treated as 'no result line'.

   Failure scenario: If the judge's last stdout line ends without a newline (for example on abnormal exit or a buffering difference), `chunk.rfind(b"\n")` defers that line to the next read. The process has already exited, so no next read happens. check_result fails with child_error 'result の行がない'. The old json format read the whole file with json.load, so this case did not exist.

7. `skills/review-loop/scripts/review_loop.py:293`: Success is judged only from the last result line, so an error in an earlier result line (is_error or a non-success subtype) is ignored.

   Failure scenario: A review emits result 1 = subtype error_during_execution, is_error true (the main body was cut off), and then result 2 = success with a short text. data=results[-1] passes the check, and the review is accepted as complete even though its body is broken.

8. `skills/review-loop/scripts/review_loop.py:786`: The judge's polling loop (poll, then watch_denials, then timeout check, then sleep, then a final poll and watch after exit) re-implements almost exactly the loop in run_reviews.

   Failure scenario: The same logic is maintained in two places, and a future change to how denials or timeouts are handled can easily update only one of them. A shared helper such as `wait_child(label, p, tail, timeout, workdir)` would let both run_reviews and run_judge use it.

9. `skills/review-loop/scripts/review_loop.py:252`: check_result rebuilds the summary dict for tail.denial by hand, duplicating the input lookup that StreamTail.summary already does.

   Failure scenario: The `{"tool_name":..., "tool_input": tail.tool_inputs.get(...)}` construction exists in both places, and a change to one (for example to the input lookup) can leave the other behind and make the two summaries differ. Have StreamTail return the dict through something like a `denial_entry(d)` method and use it in both places.

10. `skills/review-loop/scripts/review_loop.py:716`: When a review finishes, watch_denials is called twice in a row with running=False. The first call is redundant.

    Failure scenario: Line 708 already calls it with running=False when rc is not None, and line 716 calls it again after tail.poll(). The first call is wasted. Skipping the first call when rc is not None, or calling it once after the rc check, keeps the same behavior with simpler code.

8 findings, most severe first:

1. `skills/review-loop/scripts/review_loop.py:307`: Any denial with source == "config" is now non-fatal. If real claude in -p mode also tags the ordinary case (a call with no allow rule is turned into a deny, e.g. reason_type subcommandResults) as source config, the main guard is effectively off.

   Failure scenario: The read-only allow rule for gh pr diff is missing → a compound call like `gh pr diff 7; grep ...` is denied with source=config, reason_type=subcommandResults → the attempt does not stop, the reviewer returns 'no findings' without having read the diff, the judge treats it as a valid review, and only a warn line and denials.txt are left. This contradicts the SKILL.md precondition that 'calls to tools that are not allowed are denied and the attempt fails'. The tests only use the fake's source values and never check the real event schema.

2. `skills/review-loop/scripts/review_loop.py:242`: Joining every non-empty top-level result line keeps superseded drafts from earlier turns, so the review and verdict text can contain the same content twice, or contradictory content.

   Failure scenario: A skill using background subagents outputs 'Standards: findings A, B' in turn 2 and then a final report in turn 3 that drops B and adds C → result.md and judge-input.md contain both the retracted B and the duplicate A, and the judge adopts the retracted finding. For the judge itself, a draft verdict plus a final verdict both go into verdict.md, giving two '## 指摘' sections.

3. `skills/review-loop/scripts/review_loop.py:263`: The child_error message now shows the first 500 characters of the joined text instead of the last result, so the actual error text is cut off.

   Failure scenario: Several result lines; the last one is is_error=true / subtype=error_during_execution and its result holds the error message → the failed: line and failure.txt show only progress text such as 'running in the background' from the top of the joined text, and the cause cannot be determined. Before this change, data['result'] of the last line was shown.

4. `skills/review-loop/scripts/review_loop.py:249`: config_denied is a dict keyed by tool_use_id, so if a config-denial event has no tool_use_id, None goes into seen and fatal denials in the result's permission_denials that also lack tool_use_id are dropped as already seen.

   Failure scenario: A config-denial event without tool_use_id plus a sandbox or similar denial recorded only in the result's permission_denials (no tool_use_id) → d.get('tool_use_id') is None and is in seen → skipped, so the attempt that should be permission_denied passes. Several config denials without an id also overwrite the same key, so later ones are never reported to new_config_denials, the warn line or denials.txt.

5. `skills/review-loop/scripts/review_loop.py:245`: Tokens are taken only from the last result line, but the docstring says both 'modelUsage is a session total' and 'every line has the same value', which contradict each other. If modelUsage is per turn, earlier turns are not counted.

   Failure scenario: A child whose subagents run in the background and that goes through several turns, where modelUsage is per turn → only the last turn (which may be just a short note like 'unchanged from the previous message') is counted, attempt['tokens'] is far too low, and the cost shown in the state comment is understated. The test uses the same value on every line, so it cannot tell the two cases apart.

6. `skills/review-loop/scripts/review_loop.py:804`: After the judge's result lines are joined, the closing-fence removal (regex anchored at the end, `\n```\s*$`) does not match when a short line follows the verdict, and that trailing text stays in verdict.md.

   Failure scenario: The judge outputs 'Here is the verdict ```' + verdict + '```' in one turn and 'Done.' in the next → the end of the joined text is 'Done.', so the closing fence and 'Done.' remain in verdict.md and the output the parent reads is broken.

7. `skills/review-loop/scripts/review_loop.py:252`: check_result builds `{tool_name, tool_input: tail.tool_inputs.get(...)}` by hand, duplicating the logic of the new StreamTail.summary.

   Failure scenario: If the way denials are summarized changes (for example, adding reason_type), it has to be changed in two places and the stop message and the check_result message drift apart. A helper that returns the dict for tail.denial could be shared instead.

8. `skills/review-loop/scripts/review_loop.py:708`: When rc is not None, watch_denials(running=False) runs, and after finish/poll it runs again with the same arguments at line 716, so the first call is redundant.

   Failure scenario: Two calls on the exit path make it hard to see which one does the reporting. Calling it only inside `if rc is None` with running=True does the same job.

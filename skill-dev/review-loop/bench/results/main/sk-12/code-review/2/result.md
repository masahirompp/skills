8 findings, most severe first:

1. `skills/review-loop/scripts/review_loop.py:802`: The judge's output now joins every non-empty top-level result line, and verdict is sliced from the first heading to the end of that joined text. Any non-empty result line after the verdict, or a second copy of the verdict, ends up in verdict.md.

   Failure scenario: The judge emits result lines in the order [verdict, "前のメッセージの内容から変わりません"] or [verdict, the same verdict again]. verdict.md then has a stray sentence after the 競合 section, or two copies of ## 指摘 / ## 競合 with duplicate F1 entries, and the parent reads that as the verdict. The multi test only covers the case where the last line is empty. The judge is told to output Markdown only, so it does not need the join. Using only the last non-empty result line (or the line that contains the headings) would be safer.

2. `skills/review-loop/scripts/review_loop.py:308`: Any denial with source == "config" is now treated as allowed to continue. Denials from the user's deny rules that protect against forbidden operations no longer fail the attempt.

   Failure scenario: A child ignores NO_MUTATION and tries `git push` or `gh pr comment`, and a user deny rule (source config) blocks it. Before this change that was a permission_denied failure. Now it is only a warn line and denials.txt, and the attempt succeeds. If a deny rule hits a core command such as `gh pr diff`, the review is effectively empty but still counts as success. If the CLI also reports `-p`-mode denials of commands with no allow rule (ask) as config, the SKILL.md premise that missing allow rules make the attempt fail no longer holds. The exemption should be narrowed to read-only Bash or to reason_type == subcommandResults.

3. `skills/review-loop/scripts/review_loop.py:242`: A review's text is every non-empty result line joined together, so if the skill puts the body in an intermediate line and repeats the same body as its final answer, the review appears twice.

   Failure scenario: A background-subagent skill emits results ["本文…", "最終レビュー: 本文…"]. Both copies go into judge-input.md, doubling the judge's input tokens and making it more likely the judge counts the same finding twice. Mid-run progress lines such as "バックグラウンドで実行しています" also reach the judge and can trigger a false 観点の欠落 (missing perspective) report.

4. `skills/review-loop/scripts/review_loop.py:309`: config_denied is keyed by tool_use_id, so config denial events with no id collapse into one entry, and None gets into seen.

   Failure scenario: Several config denials arrive without a tool_use_id. Only the first is written to denials.txt and stderr, and the rest are not recorded. Because seen contains None, any permission_denials entry in a result that also lacks tool_use_id is skipped, so a denial that should stop the attempt is missed. Keying by (tool_use_id or a sequence number) and excluding None from seen would avoid both.

5. `skill-dev/review-loop/test.py:506`: The judge was moved to stream-json polling, but its new paths (stopping on a live non-config denial, and the timeout check inside the polling loop) have no tests.

   Failure scenario: There is no FAKE_JUDGE=denylive or hang mode. If `watch_denials("judge", ..., running=True)` or the timeout check in the judge loop regresses, a judge that keeps working after a denial can run for up to 20 minutes. The test suite would still pass.

6. `skills/review-loop/scripts/review_loop.py:785`: run_judge copies the poll / watch_denials / timeout / sleep loop from run_reviews.

   Failure scenario: The two loops now have to be kept in sync by hand when denial or timeout handling changes, and they are already slightly different: run_reviews calls watch_denials twice after the child exits, run_judge calls it once. A shared helper such as `wait_child(label, p, tail, timeout, workdir)`, which run_reviews could also use per child, would remove the duplication. The first watch_denials call in run_reviews (running=False) is redundant with the one after finish.

7. `skills/review-loop/scripts/review_loop.py:707`: Config denials are only written to denials.txt when the poll loop reaches that child. If another review fails first, config denials from the reviews still running are never recorded.

   Failure scenario: Review A emits a config denial. Before the next loop iteration reaches A, review B raises (timeout, child_error, etc.). A's denial never reaches denials.txt or the warn line, so it is missing from what the user is told to check when a perspective fails. Flushing denials for every running tail in the exception path would fix this.

8. `skills/review-loop/scripts/review_loop.py:237`: The docstring says modelUsage is a session total and that every result line has the same value. A running total grows line by line, so those two claims contradict each other.

   Failure scenario: A maintainer who trusts "どの行も同じ値" (every line has the same value) may switch to using the first line or the max, and token counts are then undercounted. The fake emits the same modelUsage on every line, so the test (4*300) cannot tell whether the counts grow.

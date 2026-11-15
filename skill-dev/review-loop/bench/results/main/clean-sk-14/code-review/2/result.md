The diff covers 5 files (`scan.sh`, `lib.sh`, `apply.sh`, `SKILL.md`, `test.sh`). I ran `skill-dev/housekeeping/test.sh` and every test passed. No CLAUDE.md applies to this code: the repo has none, and the user-level one only sets how to respond, not how to write code. There were 6 findings. Only the first is about safety (whether a worktree can be deleted while in use); the other 5 are lower-severity improvements.

6 findings, most severe first:

1. `skills/housekeeping/scripts/lib.sh:96`: hk_process_cwds only checks that its own process ($$) shows up in the lsof list to decide that lsof can see processes. That does not prove it can see other processes, so a sandbox that shows only its own processes still passes.

   Failure scenario: Sandboxes like the macOS Seatbelt profile can let a process see processes in the same sandbox but not those outside it. In that case scan.sh's own process is listed, so the check passes. A user's terminal shell that has cd'd into a worktree is not listed, so the worktree is judged 'not in use' and becomes delete. apply.sh then runs git worktree remove on a clean worktree while that shell is still in it. This is exactly the case the PR set out to protect against, yet the test only simulates lsof exiting 1, so it never covers this.

2. `skills/housekeeping/scripts/lib.sh:91`: When lsof is missing (common in minimal Linux and Docker images), the code always returns an empty list. Every worktree is then treated as 'cannot verify' and kept, so worktree cleanup stops working completely in those environments.

   Failure scenario: Run on a Linux CI image or container without lsof: every non-main worktree in scan.sh becomes keep, and its branch becomes keep through wt_action=keep. apply.sh also skips every worktree row. On Linux, the cwd of each process can be read from /proc/*/cwd with readlink, so falling back to that would fix the cause instead of just keeping everything.

3. `skills/housekeeping/SKILL.md:20`: With the new ${TMPDIR:-/tmp} fallback, the scan result goes to a fixed, predictable file name, /tmp/housekeeping-scan.tsv, in the shared /tmp.

   Failure scenario: On Linux without TMPDIR, two sessions working on different repositories at the same time overwrite each other's scan.tsv. The rows passed to apply.sh can then come from the other repository. Another user can also create a symlink at that path in advance, so the > redirect writes to the symlink's target. Using a unique name from mktemp, or a file under the repository, avoids both problems.

4. `skills/housekeeping/scripts/scan.sh:49`: parse_pr_info re-implements string splitting by hand, even though lib.sh's comment allows process substitution, so a plain read would do the same job.

   Failure scenario: `IFS=' ' read -r st num oid < <(pr_info "$name"); [ -n "$st" ] || st=UNKNOWN` behaves the same and uses no temporary file. As it stands, a custom parser lives in scan.sh next to hk_parse_action in lib.sh, and each future change to the splitting rules has to be checked in two places.

5. `skills/housekeeping/scripts/scan.sh:119`: on_fp is computed with grep before merged_into_default, even for unmerged branches where it is never used. Since lines 85-86 now stop the scan unless the first-parent file exists and is non-empty, the `on_fp -gt 1` branch is effectively unreachable.

   Failure scenario: In a repository whose default branch has tens of thousands of commits, branches with unmerged commits now also grep the whole first-parent list, which is wasted work. Running the grep only after the merged_into_default check, and dropping the dead `-gt 1` branch, keeps the same behavior.

6. `skills/housekeeping/scripts/apply.sh:37`: hk_process_cwds (lsof across every process) runs even when the approved input contains no worktree rows to delete.

   Failure scenario: Passing only branch or remote rows still runs lsof, which can take several seconds on macOS with many processes. scan.sh also runs it when the only worktree is the main one. Running it lazily, only when there is at least one target worktree, removes the wait.

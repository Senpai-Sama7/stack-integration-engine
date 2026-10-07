# Recovery exercises

## Expired or killed worker

1. Stop new dispatch with `stack-agent pause RUN_ID`.
2. Inspect the task and lease event history.
3. Run controller reconciliation (performed automatically at startup/run boundaries in supported
   flows). The task must become `reconciling`, never immediately `ready`.
4. Inspect the managed worktree and any external side effect.
5. Move to `ready` with `stack-agent task retry TASK_ID` only when the old process cannot
   continue and retry is safe; otherwise leave it in `awaiting_input` or drop it with
   `stack-agent task cancel TASK_ID`. The run loop never requeues a reconciled task by itself.
6. `resume` and `run` the run, and confirm the new lease has a larger fencing token. A late old
   submission must fail.

## Provider protocol failure

Malformed/truncated JSON, a missing Codex terminal event, Claude `is_error`, timeout, or nonzero exit
creates an unsuccessful provider result. Preserve its bounded transcript. Re-run `doctor`, correct
the provider/version/configuration issue, then start a new attempt; do not edit the result record.

## Candidate changes after review

Request changes, return the task to `ready`, and produce a new candidate hash. The controller does
this automatically up to `max_task_attempts` (policy, default 2) and gives the next attempt the
previous verdict and findings; beyond that the task stays `changes_requested` until
`task retry`. Existing reviews and
checks remain in history but cannot satisfy the new candidate. Assign a new opposite-provider
review and rerun every required check.

## Integration conflict or changed target base

The integration writer cherry-picks verified commits in dependency order and compares the expected
head before each one. A failed cherry-pick is aborted so the worktree stays inspectable and the run
is marked failed with a finding. Recompose in a fresh integration worktree (re-running integration
recreates it). Conflicts are source changes requiring review,
not mechanical evidence. Run combined checks on the final head.

## Database recovery

Create backups through `stack-agent backup FILE` (SQLite's online backup API, safe while the
controller runs). Pause dispatch before copying the artifact tree. Restoring goes through the same
API in reverse (`ControllerDatabase.restore_from`), never a raw file copy over a WAL database,
which could replay stale `-wal` pages.
To test recovery, open the backup with a separate `--state` directory, verify schema migration,
list runs/tasks, and validate referenced artifact hashes before resuming any work.

## Disk cleanup

Every task gets its own worktree under `STATE/worktrees/PROJECT/RUN/`. After a run is completed,
failed, or cancelled and you no longer need to inspect it, `stack-agent cleanup RUN_ID` removes
those worktrees and prunes Git's worktree records. A completed run's `stack-agent/RUN_ID` branch is
kept; candidate commits of a failed run become unreachable once their worktrees are removed.

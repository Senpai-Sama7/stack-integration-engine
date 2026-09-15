# Recovery exercises

## Expired or killed worker

1. Stop new dispatch with `stack-agent pause RUN_ID`.
2. Inspect the task and lease event history.
3. Run controller reconciliation (performed automatically at startup/run boundaries in supported
   flows). The task must become `reconciling`, never immediately `ready`.
4. Inspect the managed worktree and any external side effect.
5. Move to `ready` only when the old process cannot continue and retry is safe; otherwise retain
   `awaiting_input` or `failed`.
6. Resume and confirm the new lease has a larger fencing token. A late old submission must fail.

## Provider protocol failure

Malformed/truncated JSON, a missing Codex terminal event, Claude `is_error`, timeout, or nonzero exit
creates an unsuccessful provider result. Preserve its bounded transcript. Re-run `doctor`, correct
the provider/version/configuration issue, then start a new attempt; do not edit the result record.

## Candidate changes after review

Request changes, return the task to `ready`, and produce a new candidate hash. Existing reviews and
checks remain in history but cannot satisfy the new candidate. Assign a new opposite-provider
review and rerun every required check.

## Integration conflict or changed target base

The integration writer compares the expected head before each cherry-pick. On mismatch, stop and
rebase/recompose in a fresh integration worktree. Conflicts are source changes requiring review,
not mechanical evidence. Run combined checks on the final head.

## Database recovery

Create backups through `stack-agent backup FILE`. Pause dispatch before copying the artifact tree.
To test recovery, open the backup with a separate `--state` directory, verify schema migration,
list runs/tasks, and validate referenced artifact hashes before resuming any work.

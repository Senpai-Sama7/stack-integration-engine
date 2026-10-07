# Operator guide

## Preflight

Run `stack-agent doctor --project PATH`. Both provider capabilities should be `supported` for a
two-team run. A required capability marked `degraded`, `unsupported`, or `untested` must not be
added to a task.

Doctor probes supported authentication status commands but redacts account identity. It also
negotiates NEXUS tools and validates the SDLC launcher or source fallback.

## Projects

`stack-agent project add PATH` (and `plan SPEC PATH`) accepts a repository root or any committed
subdirectory of one. A subdirectory is its own project: task paths, check commands, and the
provider working directory are all relative to it, and changes outside it fail scope enforcement.
Workers only see the base commit, so `plan` warns when the project has uncommitted changes.

## Run specification

Start from `examples/local-review.json`. Unknown fields are rejected at every level, so a typo
fails planning instead of silently dropping a constraint. The top level has `objective`,
`acceptance`, `tasks`, and optionally `scope_paths`, `checks`, and `budget`
(`max_sessions`, `max_modifying_tasks`, `max_verification_jobs`, `wall_time_seconds`,
`reported_cost_usd`). Every acceptance ID must be covered by at least one task. Each task has:

- a stable ID and description;
- `codex` or `claude` ownership;
- dependency IDs;
- project-relative allowed paths inside the run's `scope_paths`;
- acceptance IDs inherited from or narrowing the run acceptance list;
- `read_only` or `worktree_write` side effect;
- any required capability IDs observed by doctor.

The DAG is rejected for duplicate or malformed IDs (letters, digits, `.`, `_`, `-`; `integration`
is reserved), unknown dependencies, cycles, self-dependencies, missing capabilities, side effects
other than `read_only`/`worktree_write`, and paths that are absolute, contain `..`, or leave the run
scope. A failed admission cancels the half-created run.

For modifying runs, add explicit top-level `checks` when auto-detection is insufficient. Each check
has an ID, name, argument-vector `command`, timeout, required flag, and `expects_tests` flag. These
commands are operator-authorized code execution; review them before planning an unfamiliar repo.

## During a run

Use `runs` to list runs and `status RUN_ID` for the controller's truth. Use `inspect task TASK_ID`
for the full versioned record. `steer RUN_ID TEXT [--task TASK_ID]` records an operator instruction
that is placed directly in later prompts and context packets; it does not rewrite prior evidence.
`pause` stops new dispatch while in-flight tasks finish; `resume` followed by `run` continues.
`cancel` marks every task cancelled, and an active `run` process terminates its in-flight provider
processes.

A task that ends in `awaiting_input` (for example after lease reconciliation), `blocked`, or
`changes_requested` past the attempt limit stays there until you act. After inspecting its worktree
(`inspect task TASK_ID` shows the path), use `task retry TASK_ID` to return it to `ready`, or
`task cancel TASK_ID` to drop it, then `resume`/`run` the run.

## Results

A completed run publishes its verified, integrated commit on `refs/heads/stack-agent/RUN_ID` in the
project repository; `status` and `report` show the branch and commit. Nothing touches your checked
out branch or working tree. Review and merge it like any other branch. When you are done with a
finished run, `cleanup RUN_ID` removes its worktrees; the branch is kept.

## Policy

Optional `STATE/policy.json` overrides controller limits. Unknown sections are rejected:

```json
{
  "teams": {"max_concurrent_model_sessions": 6, "max_active_modifying_tasks": 2,
            "max_parallel_verification_jobs": 2},
  "scheduling": {"lease_seconds": 90, "heartbeat_seconds": 15, "task_wall_time_seconds": 1200,
                 "review_wall_time_seconds": 900, "max_task_attempts": 2}
}
```

`doctor` reports whether a policy file is in effect.

## Reports

`report` includes run state, a summary (task/review/check/finding tallies and known token and cost
totals, which stay `null` when any value is unknown), tasks, reviews, checks, findings, sessions,
normalized usage, artifact manifests, and explicit limitations. `run RUN_ID --summary` prints just
the run and its summary. Artifact content remains in the state directory and is
project-scoped. Back up SQLite with `backup`; copy artifacts separately while dispatch is paused.

## Bridge configuration

Issue a short-lived token:

```bash
stack-agent issue-grant PROJECT_ID codex-worker builder codex --scope src --ttl 1800
```

Launch the hidden stdio bridge with that token in `STACK_AGENT_GRANT` and the same state directory.
The bridge implements MCP `initialize` (with protocol-version negotiation), `tools/list`,
`tools/call`, and `ping`. Its tools cover task query/claim/heartbeat/proposal, messages, findings,
artifacts, reviews, decisions, checkpoints, and operator-admitted verification. Tool failures come
back as `isError` results the model can read; protocol errors use JSON-RPC error codes. Task
proposals go through the same validation as `plan`. The authenticated token—not a JSON
`actor_id` field—sets caller identity.

Never place grant tokens in task prompts, reports, repository files, or shell history. Let the
controller populate a child process environment in automated integrations.

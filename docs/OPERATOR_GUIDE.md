# Operator guide

## Preflight

Run `stack-agent doctor --project PATH`. Both provider capabilities should be `supported` for a
two-team run. A required capability marked `degraded`, `unsupported`, or `untested` must not be
added to a task.

Doctor probes supported authentication status commands but redacts account identity. It also
negotiates NEXUS tools and validates the SDLC launcher or source fallback.

## Run specification

Start from `examples/local-review.json`. Each task has:

- a stable ID and description;
- `codex` or `claude` ownership;
- dependency IDs;
- project-relative allowed paths;
- acceptance IDs inherited from or narrowing the run acceptance list;
- `read_only` or `worktree_write` side effect;
- any required capability IDs observed by doctor.

The DAG is rejected for duplicate IDs, unknown dependencies, cycles, self-dependencies, or missing
capabilities.

For modifying runs, add explicit top-level `checks` when auto-detection is insufficient. Each check
has an ID, name, argument-vector `command`, timeout, required flag, and `expects_tests` flag. These
commands are operator-authorized code execution; review them before planning an unfamiliar repo.

## During a run

Use `status` for the controller’s truth. Use `inspect task TASK_ID` for the full versioned record.
`steer` appends an operator-authored message to future context packets; it does not rewrite prior
evidence. `pause` stops new dispatch at controller boundaries. `cancel` prevents resume and should
be followed by reconciliation if a provider process was active.

## Reports

`report` includes run state, tasks, reviews, checks, findings, sessions, normalized usage, artifact
manifests, and explicit limitations. Artifact content remains in the state directory and is
project-scoped. Back up SQLite with `backup`; copy artifacts separately while dispatch is paused.

## Bridge configuration

Issue a short-lived token:

```bash
stack-agent issue-grant PROJECT_ID codex-worker builder codex --scope src --ttl 1800
```

Launch the hidden stdio bridge with that token in `STACK_AGENT_GRANT` and the same state directory.
The bridge implements MCP `initialize`, `tools/list`, `tools/call`, and `ping`. Its initial tools
cover task query/claim/heartbeat, messages, and findings. The authenticated token—not a JSON
`actor_id` field—sets caller identity.

Never place grant tokens in task prompts, reports, repository files, or shell history. Let the
controller populate a child process environment in automated integrations.

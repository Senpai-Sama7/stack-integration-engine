# Architecture

## Control flow

```text
operator CLI
    |
    v
single controller authority ---- signed grant ----> MCP stdio bridge
    |        |                                      /        \
    |        +--> SQLite WAL + event outbox   Codex sessions  Claude sessions
    |        +--> content-addressed artifacts       \        /
    |        +--> scheduler + leases/fencing         findings
    |        +--> Git task worktrees                  reviews
    |        +--> independent verifier                 |
    +------------------------------------------> serialized integration
```

The controller owns task assignment, state transitions, grants, and integration. Providers own
reasoning and bounded work products, not authority. Every provider process has an explicit task,
role, project root, timeout, output contract, and session identity.

## Lifecycle

1. Register a Git project using its common directory identity.
2. Freeze a run objective, scope, base commit, acceptance version, and budget.
3. Validate task IDs, dependencies, cycles, required capabilities, paths, and side effects.
4. Atomically lease ready tasks. A monotonically increasing fencing token rejects late writers.
5. Build a context artifact from the current task, evidence, messages, and source revision.
6. Start Codex or Claude in a separate managed session. Modifying work receives a detached Git
   worktree; read-only work receives the project root with read-only provider permissions.
7. Register provider output as producer evidence. It does not verify itself.
8. Freeze the candidate hash and assign the opposite provider to review it.
9. Run project checks in an independent subprocess and store complete bounded logs.
10. Mark the task verified only when review, requirement coverage, and checks all pass.
11. Commit accepted worktree changes, serialize cherry-picks in an integration worktree, and rerun
    combined checks against the resulting candidate.

## Storage

SQLite uses WAL, full synchronous writes, foreign-key enforcement, and immediate transactions. A
state write and its event-outbox row share one transaction. Mutable aggregates carry revisions for
compare-and-swap. Artifacts are SHA-256 addressed under a per-project directory and checked on
every read.

The current scale target is one local operator, at most six provider sessions, two modifying
tasks, and two verification jobs. SQLite is intentionally retained until measurement demonstrates
that a larger scheduler or multi-user database is necessary.

## Provider modes

The default mode is controller-managed sessions: `codex exec` and `claude --print`. This makes
identity, capacity, cancellation, output parsing, and restart behavior observable.

Codex App Server is a future persistent transport optimization, not required for correctness.
Codex subagents and Claude print-mode subagents can be admitted after child lifecycle and capacity
tests. Claude interactive agent teams require a separate interactive bridge; they are not claimed
to exist in print mode.

## Optional upstream tools

NEXUS is a code-intelligence tool server, accessed over MCP stdio after `initialize` and
`tools/list` negotiation. Mutating NEXUS tools are not admitted through the read-only adapter.

SDLC is accessed through JSON CLI commands. The adapter checks exit status and JSON shape. It may
use a verified source script when an installed launcher is unhealthy, and reports that fallback.

SAGE, PROMETHEUS, and PLATFORM compatibility classes remain fail-closed until a real transport and
contract are configured. Their prior constant-success behavior has been removed.

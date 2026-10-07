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

1. Register a Git project. A repository root is identified by its Git common directory; a
   subdirectory (for example one package of a monorepo) is a distinct project whose scope paths,
   checks, and provider working directory are relative to that subdirectory.
2. Freeze a run objective, scope, base commit, acceptance version, and budget.
3. Validate task IDs, unknown fields, dependencies, cycles, required capabilities, side effects
   (only `read_only` and `worktree_write` are admitted), and paths (normalized, inside the run
   scope).
4. Dispatch is event-driven: a task starts as soon as its dependencies verify, bounded by the
   session and modifying-task limits. Each start atomically leases the task; a monotonically
   increasing fencing token rejects late writers, and one heartbeat keeps the lease alive from
   the claim until the task leaves `running`. Blocking Git work (worktree creation, hashing,
   diffing, committing) runs in worker threads so the event loop keeps renewing leases and
   enforcing timeouts.
5. Give every task its own detached Git worktree at the run's base revision, with the verified
   commits of all transitive dependencies cherry-picked in dependency order (read-only reviews of
   upstream work therefore see that work).
6. Build a context artifact from the current task, evidence, messages, and source revision. The
   prompt also carries operator `steer` instructions and, on retries, the previous review verdict
   and findings.
7. Start Codex or Claude in a separate managed session with read-only or worktree-write provider
   permissions. Prompts over 100 KiB travel over stdin instead of argv (Linux limits one argument
   to 128 KiB).
8. Register provider output as producer evidence. It does not verify itself.
9. Enforce the task's path scope on the changed files, freeze the candidate hash, and assign the
   opposite provider to review a diff that includes newly created files.
10. Run project checks in an independent subprocess (without the bridge credential and without
    bytecode writes) and store complete bounded logs.
11. Mark the task verified only when review, requirement coverage, and checks all pass and the
    checks did not alter the reviewed candidate. The candidate commit is recorded in the same
    transaction as `verified`, so a dependent can never start without the commit it builds on.
    Otherwise request changes, up to the policy's attempt limit.
12. Commit accepted worktree changes, cherry-pick them in dependency order in an integration
    worktree, rerun combined checks, and publish the result as `refs/heads/stack-agent/<run-id>`
    without touching the operator's checked-out branch or working tree.

## Storage

SQLite uses WAL, full synchronous writes, foreign-key enforcement, and immediate transactions. A
state write and its event-outbox row share one transaction. Mutable aggregates carry revisions for
compare-and-swap. Artifacts are SHA-256 addressed under a per-project directory and checked on
every read.

The current scale target is one local operator, at most six provider sessions, two modifying
tasks, and two verification jobs. The controller serializes statements on its shared SQLite
connection, so the API's worker threads and the run loop can share it safely. SQLite is
intentionally retained until measurement demonstrates that a larger scheduler or multi-user
database is necessary.

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

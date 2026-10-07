# Changelog

## 0.3.0 (2026-10-07)

### Fixed

- **Reviewers saw an empty diff for new files.** Review prompts used `git diff BASE`, which omits
  untracked files, so a task that only created files was reviewed blind. The diff now includes
  them (rendered without touching the index).
- **Large review prompts could not launch.** Reviews embed up to 200 KB of diff, over Linux's
  128 KiB single-argument limit (`E2BIG`). Prompts over 100 KiB are piped over stdin.
- **Dependent tasks built on the wrong base.** Only direct dependencies' commits were composed, so
  a modifying task behind a read-only review started from the bare base, and read-only reviews of
  upstream work never saw that work. All transitive dependency commits are composed, in dependency
  order, for every task; integration also cherry-picks in dependency order.
- **Bytecode caches broke candidates.** `__pycache__` written by tests counted as candidate files
  (scope violations) and as post-review drift. Provider and verification processes now run with
  `PYTHONDONTWRITEBYTECODE=1`.
- `updated_at` recorded the creation time on every update.
- A subprocess whose descendant kept stdout open could hang the controller indefinitely; stdin was
  written outside the wall-time limit.
- Artifact temp files collided between threads; restoring a backup copied files over a live WAL
  database.
- A transient storage error permanently stopped lease heartbeats.
- Scope enforcement misread non-ASCII file names (Git quoted them); an untracked nested repository
  crashed the review diff; `cleanup` aborted on a directory that was not a registered worktree.
- Malformed reviewer output (unknown verdict, malformed findings) crashed the task instead of
  abstaining.
- Claude's positional prompt could be swallowed by the variadic `--mcp-config`.
- MCP bridge: tool failures were protocol errors instead of `isError` results; the protocol
  version was never negotiated; `task_propose` skipped plan validation and accepted any side
  effect; binary artifacts crashed `artifact_get`.
- Redaction missed real Anthropic and OpenAI key formats, JSON-quoted secrets, env-style tokens,
  and several common token prefixes.
- Dashboard rendered task counts as `[object Object]`; each API request rebuilt a full controller.
- Event bus crashed on synchronous handlers and grew without bound.
- **Untrusted output could stall the controller.** The PEM private-key redaction pattern rescanned
  to the end of the text from every unterminated `-----BEGIN` marker, and the test-count parser
  retried an unanchored `(\d+)` from every digit of a long digit run. Both were quadratic
  (doubling the input quadrupled the time: 13 s for 40 000 digits). Provider output and
  candidate test output are untrusted and are processed on the event loop, so a hostile or merely
  unlucky output could hang the controller. Both are linear now, and a truncated PEM key (cut off
  by the output limit) is redacted instead of passed through.
- The MCP client failed on any tool response over asyncio's 64 KiB line limit (a NEXUS context
  pack or search result easily exceeds it), and one long stderr line crashed `close()` and masked
  the real error. The limit is 16 MiB and configurable; oversized responses are a clean
  `McpProtocolError`; stderr is read in bounded chunks.
- The lease heartbeat covered only the provider call. Workspace setup and the scope and hash work
  before submission could outlast a lease on a large repository and fail the submission.
- Project Aurora did not load in Godot (scripts at the wrong paths, a missing main script, invalid
  scene files, colliding class names), and its load check could not fail.

### Performance

Measured on a 10 000-file repository with three parallel modifying tasks:

- Event-loop stall during a run: 4.5 s to 0.04 to 0.09 s. Worktree creation, candidate hashing,
  diffing, and committing now run in worker threads instead of on the loop that renews leases and
  enforces provider timeouts. Operations that edit the shared repository's worktree records and
  refs are serialized so concurrent tasks cannot race `git worktree prune`.
- Review diff for 1 000 new files: 1 003 Git processes and 4.0 s to 4 processes and 0.7 s (a
  scratch copy of the index marks new files intent-to-add; the repository's index and object store
  are untouched).
- Candidate hashing streams files: peak Python memory for a 150 MB untracked file 157 MB to 2 MB.
- Redacting 10 MB of clean output: 1.8 s to 0.13 s (a cheap substring check skips patterns whose
  literals cannot occur; an equivalence test proves it never skips a match).
- `GET /api/runs` with 300 runs and 12 000 tasks: 150 ms to 60 ms (one SQL aggregate instead of a
  query and a model parse per task).
- Controller overhead per task, profiled with instant fake providers, is about 36 ms (mostly
  worktree creation and SQLite commits), so nothing further was changed there.

### Added

- Event-driven dispatch: dependents start as soon as prerequisites verify; operator cancel stops
  in-flight provider processes. Budgets stop model dispatch (with a recorded reason) but no longer
  prevent integrating a fully verified run.
- Verified results are published as `refs/heads/stack-agent/RUN_ID`; runs record
  `integration_commit` and `integration_ref`.
- Repository subdirectories (monorepo packages) as projects.
- Retry prompts carry the previous verdict and findings; `steer` instructions reach prompts
  directly.
- CLI: `runs`, `task retry`, `task cancel`, `cleanup`, `--version`, `--log-level`,
  `run --summary`, `steer --task`; one-line errors instead of tracebacks.
- Plan validation: unknown fields, uncovered acceptance IDs, admitted side effects, task ID shape,
  normalized in-scope paths, `budget`; failed admissions cancel the half-created run; uncommitted
  changes produce a warning.
- Optional `STATE/policy.json`, validated, including `max_task_attempts` and
  `review_wall_time_seconds`.
- Report summary with status tallies and known token/cost totals.
- Dashboard run detail view, auto-refresh, hash-based CSP, and security headers.
- Project Aurora: deterministic simulation, validated content, 23 headless tests, and a
  validation tool that fails on unloadable or uncompilable resources.
- CI: 80% branch-coverage gate, isolated wheel install, container smoke test, and the Aurora
  Godot suite; schema drift test.

### Changed

- `serve` no longer prints the operator token (it is in the 0600 token file);
  `STACK_AGENT_PRINT_TOKEN=1` restores the old behavior.
- Candidate commits skip repository hooks and signing so the commit equals the reviewed candidate.
- The package version is single-sourced from `stack_integration.__version__`.

## 0.2.0

- Fail-closed dual-team controller for Codex and Claude Code.

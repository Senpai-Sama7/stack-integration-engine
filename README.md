# Stack Integration Engine

A local-first controller that lets authenticated Codex and Claude Code CLIs work as two
bounded engineering teams. It persists task state, isolates modifying work in Git worktrees,
requires opposite-provider review, runs checks independently, and records evidence before it
integrates a candidate.

This repository previously returned synthetic success from every workflow step and service
adapter. Version 0.2 fails closed: unavailable capabilities, malformed output, missing tests,
stale leases, and unknown steps remain visibly unsuccessful.

## What is implemented

- Strict Pydantic contracts for projects, runs, tasks, leases, sessions, capabilities,
  artifacts, findings, reviews, checks, decisions, authorizations, events, messages, and usage.
- SQLite WAL storage with compare-and-swap revisions, atomic event outbox, backup, and message
  deduplication.
- DAG validation, atomic leases, heartbeat renewal, fencing tokens, and expired-writer
  reconciliation.
- Content-addressed, project-scoped artifacts with hash and size verification.
- Role/path/side-effect policy enforcement plus signed, expiring bridge grants.
- Real `codex exec --json --output-schema` and `claude --print --output-format json
  --json-schema` adapters with explicit session IDs, timeouts, process-group cancellation, and
  bounded output.
- Managed parallel teams, reproducible context packets, opposite-provider review tied to exact
  candidate hashes, revision rounds, and serialized integration.
- Independent check execution that refuses to accept launch errors, truncation, nonzero exits,
  or zero collected tests.
- NEXUS integration over its observed MCP stdio protocol and SDLC integration over its JSON CLI.
- Operator CLI, authenticated loopback status API, and local dashboard.

Native model delegation is capability-detected but is not falsely equated with managed teams:
Codex can use subagents in an admitted session, while Claude’s interactive agent-team feature is
not available in `--print` mode. The reliable default is controller-managed parallel sessions.

## Install

Requirements: Python 3.11+, Git, and at least one supported provider CLI. For two-team operation,
both `codex` and `claude` must already be authenticated through their supported login flows.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev,api]'
.venv/bin/stack-agent doctor --project .
```

The controller never asks for or stores provider credentials. It uses the existing CLI login
state. `doctor` records capability status without including account email, organization IDs, or
tokens.

## First local collaboration

Plan the included two-provider read-only review:

```bash
.venv/bin/stack-agent plan examples/local-review.json --project .
```

The command returns a generated run ID. Execute and inspect it:

```bash
.venv/bin/stack-agent run RUN_ID
.venv/bin/stack-agent status RUN_ID
.venv/bin/stack-agent report RUN_ID --output run-report.json
```

For a modifying task, set `side_effect` to `worktree_write` and constrain `allowed_paths`. A
successful worker narrative is insufficient: a changed candidate, opposite-provider review,
requirement coverage, and independent project checks are all required.

## Operator commands

```text
doctor                     probe providers, authentication, NEXUS, and SDLC
project add PATH           register a Git repository without modifying it
plan SPEC --project PATH   validate and persist a run/task DAG
run RUN_ID                 execute, cross-review, verify, and integrate
status RUN_ID              show authoritative task states
inspect KIND ID            inspect a versioned record
steer RUN_ID TEXT          add an operator instruction to subsequent context
pause/resume/cancel        control new dispatch
report RUN_ID              export evidence and explicit limitations
backup DESTINATION         create a consistent SQLite backup
schemas DIRECTORY          generate contract JSON Schemas
serve                      run the token-protected loopback dashboard/API
issue-grant                create a short-lived signed MCP bridge token
```

State defaults to `~/.local/state/stack-agent`; override it with `--state` or
`STACK_AGENT_STATE`. The dashboard defaults to `127.0.0.1:8765`. Remote listeners are rejected by
local policy.

## Trust model

The controller is the only database writer and authority source. Provider text is untrusted data.
A reviewer cannot approve its own provider’s implementation. Reviews and checks are bound to one
candidate hash and become stale when the candidate changes. Peer messages cannot grant push,
deploy, deletion, privilege, policy, or scope authority.

Git worktrees prevent accidental overlap, but they are not security sandboxes. Provider-native
permission controls remain enabled. Push, deployment, destructive operations, and credential
changes are outside the default grant set.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Operator guide](docs/OPERATOR_GUIDE.md)
- [Contracts and state machine](docs/CONTRACTS.md)
- [Security and threat model](docs/SECURITY.md)
- [Recovery exercises](docs/RECOVERY.md)
- [Compatibility matrix](docs/COMPATIBILITY.md)
- [Implementation status](docs/IMPLEMENTATION_PLAN.md)
- [Live provider probe](docs/evidence/live-provider-probe.json)

## Development verification

```bash
.venv/bin/ruff check stack_integration tests
.venv/bin/ruff format --check stack_integration tests
.venv/bin/mypy stack_integration
.venv/bin/pytest --cov=stack_integration --cov-report=term-missing
```

The deterministic suite covers controller invariants without spending model quota. Live-provider
checks are separate because provider availability and subscription quota are external conditions.

## Container status dashboard

The container runs only the controller status API; host CLI authentication is intentionally not
copied into the image.

```bash
docker compose up --build
docker compose exec orchestrator sh -c 'cat /var/lib/stack-agent/operator.token'
```

The host publishes only `127.0.0.1:8765`. Run model work through the host CLI unless you have built
an independently reviewed credential/socket forwarding boundary.

## License

MIT

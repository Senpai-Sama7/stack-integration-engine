# Implementation status

The controller was built in dependency order from the local collaboration blueprint.

| Milestone | Delivered | Remaining/conditional |
|---|---|---|
| M0 baseline | Packaging, entry point, contracts, capability/auth probes, provider fixtures | None |
| M1 controller | SQLite/outbox, artifacts, DAG/leases/fencing, policy, worktrees, reconciliation | More OS-level containment is a future hardening option |
| M2 teams | Real Codex/Claude adapters, signed MCP bridge, context packets, bounded dispatch, live probe | Persistent App Server/interactive bridge only if benchmarks justify it |
| M3 engineering loop | Typed dispatch, verifier, cross-review, revision rounds, serialized integration, operator CLI | Provider-dependent modifying demo must be rerun after provider upgrades |
| M4 tools/reliability | NEXUS MCP, SDLC CLI fallback, usage ledger, failure tests, evidence lineage | Native delegation remains capability-detected, not admitted by default |
| M5 operating quality | CI matrix, docs, loopback dashboard/API, packaging and container assets | Outcome benchmark needs a held-out project/task corpus |

Conditional remote A2A, credential brokerage, multi-user storage, and outcome-trained routing are
not activated because their triggers are absent in the local single-operator objective. This is a
deliberate security boundary, not an implied feature claim.

Release gates are:

1. isolated install and import;
2. Ruff formatting/lint and mypy;
3. deterministic invariant/failure tests;
4. provider/tool doctor;
5. live structured read-only probe;
6. opposite-provider review of the fixed candidate;
7. package and container smoke tests;
8. accurate docs, compatibility labels, rollback, and residual-risk report.

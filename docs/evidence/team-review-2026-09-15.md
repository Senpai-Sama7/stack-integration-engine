# Parallel team review — 2026-09-15

Four read-only reviewers were launched concurrently against the working-tree candidate with a
six-minute boundary: two Codex reviewers (storage/concurrency and integration/recovery) and two
Claude reviewers (security and contracts/provider interfaces).

## Outcomes

- Both Codex reviewers timed out. No review verdict or approval was inferred from those runs.
- Claude security requested changes for whole-project/empty scope handling and questioned bridge
  message/finding authorization.
- Claude contracts requested changes for Claude top-level cost capture and noted the PEP 639
  setuptools floor.

## Disposition

- Fixed root `"."` semantics in both policy and Git scope enforcement and added regressions.
- Fixed the empty-scope fail-open in admission, policy, and Git enforcement and added regressions.
- Fixed Claude `total_cost_usd` extraction into the normalized usage ledger and retained nested raw
  usage metadata.
- Raised the build-system setuptools floor to 77 for PEP 639 metadata.
- Replaced the dynamic `asyncio` import with a static import.
- Rejected the bridge authorization concern: `message_send` and `finding_publish` call
  `CoordinationService`, whose methods enforce `SideEffect.READ_ONLY` against the authenticated,
  token-derived actor before persistence.

The candidate still requires a successful Codex review after the timeout; provider timeout remains
visible evidence, not a passing gate.

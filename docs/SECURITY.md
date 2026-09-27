# Security and threat model

## Assets and trust boundaries

Protected assets are source code, user working-tree changes, provider login state, controller
authority, evidence integrity, and deployment credentials. Provider/model output, repository text,
MCP tool descriptions, and peer messages are untrusted inputs.

The local operator and controller are trusted. Codex/Claude workers receive role grants. Reviewers
cannot write candidates. The independent verifier does not accept provider assertions as check
results. Worktrees isolate collaboration but share the host account and are not containment.

## Primary controls

- No credential ingestion; existing provider CLI auth remains in provider-owned storage.
- Strict structured output and terminal-event validation.
- Explicit process arguments, no shell interpolation, output limits, wall times, and process-group
  termination.
- Project-relative path grants and post-work Git changed-path enforcement.
- Atomic leases and fencing tokens against duplicate or late writers.
- Opposite-provider review and exact-candidate evidence binding.
- HMAC-SHA256 signed bridge grants, random nonces, expiry, constant-time signature checks, and a
  mode-0600 secret.
- Loopback-only dashboard binding and a mode-0600 bearer token.
- Push, deployment, delete, privilege, policy mutation, and scope expansion excluded from worker
  grants.

## Residual risks

A provider process still runs under the local user account; provider-native sandbox and approval
behavior is therefore essential. A malicious repository may target toolchain commands executed by
the verifier. Verification definitions should be reviewed before use, especially in an unfamiliar
project. Local bearer/grant tokens can be stolen by another process running as the same OS user.

The current controller is single-operator and local. Do not expose the bridge or API on a network,
share one state directory between users, or treat this design as a hardened multi-tenant service.

## Secret handling

Reports omit auth output beyond boolean/method capability. Provider stderr is bounded and should
still be treated as potentially sensitive. Before sharing a report or artifact directory, run a
secret scanner and review every included provider transcript.

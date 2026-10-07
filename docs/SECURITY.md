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
- Loopback-only dashboard binding and a mode-0600 bearer token that `serve` does not echo by
  default; the dashboard is served with a hash-based Content-Security-Policy (no inline-script
  allowance), `X-Frame-Options: DENY`, `no-store` caching, and no OpenAPI/docs routes.
- Verification commands run without `STACK_AGENT_GRANT` in their environment, so candidate code
  under test cannot reuse the bridge credential.
- Candidate commits skip repository hooks (`--no-verify`) and signing prompts, so the committed
  tree is byte-for-byte the reviewed candidate; a formatting hook cannot change it after review.
- Parsing of untrusted output (provider results, check output, MCP responses) is linear-time and
  size-bounded: redaction and test-count patterns have no unbounded repetition that can be
  restarted from many positions, MCP lines are capped at 16 MiB, and stderr is kept as a bounded
  tail. Hostile-input regression tests fail if a pattern becomes quadratic.
- Task side effects are limited to `read_only` and `worktree_write` at admission, and task IDs and
  paths are validated before they reach the filesystem.
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

Redaction covers authorization headers, bare bearer tokens, quoted or unquoted `key=value` secrets,
environment-style `*_TOKEN`/`*_KEY`/`*_SECRET`/`*_PASSWORD`/`*_GRANT` assignments, private keys,
JWTs, and known token formats (Anthropic, OpenAI, Stripe, GitHub, GitLab, Slack, AWS, Google), plus
sensitive keys in structured payloads. It is conservative pattern matching, not a guarantee.
Reports omit auth output beyond boolean/method capability. Provider stderr is bounded and should
still be treated as potentially sensitive. Before sharing a report or artifact directory, run a
secret scanner and review every included provider transcript.

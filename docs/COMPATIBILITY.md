# Compatibility matrix

Observed locally on 2026-09-15. `doctor` is authoritative for the current machine.

| Component | Observed version | Transport | Status | Notes |
|---|---:|---|---|---|
| Codex CLI | 0.154.0 | structured `exec` JSONL | supported | Output schema, explicit thread ID, resume, worktree, App Server detected |
| Claude Code | 2.1.267 | print-mode JSON | supported | JSON schema, explicit session ID, resume, subagents/background/worktree detected |
| NEXUS | 1.0.0 source | MCP stdio | supported | 32 tools negotiated; only an allowlist is admitted read-only |
| SDLC | 1.3.1 source | JSON CLI | supported with fallback | Installed launcher is unhealthy; source CLI is used and reported |
| SAGE | inspected source only | none admitted | unavailable | Compatibility adapter fails closed |
| PROMETHEUS | inspected source only | none admitted | unavailable | No gate decision or authority is fabricated |
| PLATFORM | inspected source only | none admitted | unavailable | Compatibility adapter fails closed |

## Delegation modes

| Mode | Initial support | Reason |
|---|---|---|
| Controller-managed Codex sessions | yes | Structured lifecycle and bounded subprocess are observable |
| Controller-managed Claude sessions | yes | Structured lifecycle and bounded subprocess are observable |
| Codex native subagents | capability detected | Admission still requires child identity/capacity/cancellation tests |
| Claude print-mode subagents | capability detected | Managed sessions remain the accounting boundary |
| Claude interactive agent teams | no automated claim | Agent teams are interactive/experimental, not print-mode teams |
| A2A remote workers | deferred | Local single-operator system has no multi-machine requirement |

The live structured probe is stored in `docs/evidence/live-provider-probe.json`. It demonstrates
compatibility, not correctness of arbitrary model output.

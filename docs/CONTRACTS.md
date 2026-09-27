# Contracts and state machine

All shared records use `schema_version: "1.0"`, reject unknown fields, and require timezone-aware
timestamps. Generate machine-readable schemas with `stack-agent schemas DIRECTORY`.

| Record | Identity binding | Key invariant |
|---|---|---|
| Project | Git common directory | Worktrees of one repository share a project ID |
| Run | Project, base commit | Objective, scope, acceptance, and budget are revisioned |
| Task | Run, provider, role | Dependencies and required capabilities must be admitted |
| Lease | Task, actor, attempt | Only the current fencing token may submit |
| Session | Task/run grant | Provider session IDs are explicit; “latest” is never inferred |
| Artifact | Project/run/task | Bytes must match registered SHA-256 and size |
| Finding | Author and evidence | Confidence/proposal is distinct from verified status |
| Review | Reviewer and candidate | Opposite provider; exact candidate only |
| Check | Definition and candidate | Launch/parse/no-tests outcomes cannot pass |
| Authorization | Actor/action/scope | Peer text and review verdicts cannot grant authority |
| Event | Aggregate revision | Inserted atomically with state through the outbox |
| Usage | Session/task | Unknown values remain null, never zero-filled |

## Task transitions

```text
proposed -> ready -> leased -> running -> submitted -> reviewing -> verified -> integrated
              |         |          |            |
              |         +------> reconciling     +-> changes_requested -> ready
              |                        |
              +-> blocked/cancelled    +-> ready/awaiting_input/failed
```

Invalid transitions raise an error. Submission requires the current lease token and a candidate
hash. A lease expiry moves active work to reconciliation; it does not retry an uncertain external
action. Candidate changes naturally invalidate old reviews and checks because all evidence is
looked up by exact candidate hash.

## Provider results

Provider commands return one of `completed`, `failed`, `timeout`, `cancelled`, or
`protocol_error`. Codex requires valid JSONL and a `turn.completed` event. Claude requires a JSON
`result` with `subtype: success` and `is_error: false`. A clean process exit alone is not success.

Raw provider usage allows nested vendor metadata. The shared usage ledger extracts only known
numeric fields; absent or opaque subscription cost remains unknown.

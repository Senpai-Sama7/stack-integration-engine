# Testing Strategy

## Status

- **Status:** Draft v1.0
- **Date:** 2026-09-27

## Testing goals

The game must be testable without relying on visual inspection alone. Gameplay rules are validated through deterministic simulation snapshots and scenario fixtures. Rendering and input-device tests supplement, but do not replace, simulation tests.

## Test layers

### Unit tests

Test isolated rules:

- movement acceleration and gravity;
- jump buffering and coyote time;
- attack phase timers;
- hitbox geometry and contact filtering;
- damage and knockback formulas;
- shield and grab rules;
- stock and respawn transitions;
- stage and character data validation.

### Integration tests

Test complete scenarios:

- two fighters move and attack on Aegis Rooftop;
- a shield blocks an attack;
- a grab transitions through capture and throw;
- a fighter crosses a blast zone and respawns;
- both players are eliminated simultaneously;
- a match pauses, resumes, restarts, and finishes.

### Determinism tests

Run identical command streams twice and compare per-tick snapshots. Differences in positions, velocities, states, damage, stocks, or events fail the test.

### Replay tests

When replay support exists, record a command stream, play it back, and verify the final snapshot and event digest match the original run.

### Headless tests

The project must support a headless validation command that loads the main project and exits with failure on missing resources or startup errors.

### Manual tests

A human checklist covers:

- keyboard and controller mapping;
- readable silhouettes and effects;
- pause behavior;
- camera framing;
- debug hitbox display;
- accessibility settings;
- first-launch experience.

## Acceptance matrix

| Requirement | Minimum evidence |
|---|---|
| movement | unit tests plus deterministic sequence |
| combat | attack/contact scenario tests |
| characters | data validation plus one scenario per fighter |
| stage | geometry, spawn, and blast-zone tests |
| stocks | respawn and match-ending integration tests |
| clean checkout | headless startup and full test run |
| balance change | decision record plus regression test |

## Failure policy

- A missing test is not equivalent to a passing test.
- A renderer-only smoke test cannot prove simulation correctness.
- A provider's narrative cannot replace command output.
- A flaky test must be fixed or quarantined with an explicit decision and owner.
- Any change to timing, collision, damage, or stock rules requires rerunning the relevant scenario suite.

## Required CI checks

1. formatting and linting;
2. static type or script validation where available;
3. unit tests;
4. integration tests;
5. deterministic replay/simulation tests;
6. headless project load;
7. artifact/report generation.

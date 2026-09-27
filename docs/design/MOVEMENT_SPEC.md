# Movement Specification

## Status

- **Status:** Draft v1.0
- **Date:** 2026-09-27

## Coordinate and timing model

- 2D world coordinates use pixels as the initial authoring unit.
- Simulation runs at 60 ticks per second.
- All gameplay movement uses deterministic numeric operations.
- Values below are starting targets and may be tuned only through a recorded decision.

## Shared movement states

```text
Grounded
  -> JumpStartup -> Airborne
  -> Dash / Run / Walk
  -> Shielding / Attacking / Grabbed / Hitstun
Airborne
  -> FastFall / DoubleJump / AirAttack / Special
  -> Grounded on landing
  -> BlastZone on leaving the legal stage region
Respawn
  -> Invulnerable -> Grounded or Airborne
```

## Baseline values

| Value | Target |
|---|---:|
| simulation rate | 60 Hz |
| run speed | 280 px/s |
| ground acceleration | 2200 px/s² |
| ground deceleration | 2600 px/s² |
| air control acceleration | 950 px/s² |
| maximum air speed | 245 px/s |
| gravity | 1450 px/s² |
| jump impulse | -540 px/s |
| fast-fall speed | 760 px/s |
| input buffer | 6 ticks |
| coyote time | 4 ticks |
| landing lock | 2 ticks |

These are original starting values, not intended to reproduce any specific commercial game.

## Jumping

- Pressing jump while grounded applies the jump impulse.
- Releasing jump during ascent applies early-release damping once per jump.
- Each fighter receives one air jump by default; the character resource may change this.
- Jump input within coyote time is accepted after walking off a platform.
- Jump input within the input buffer is consumed on the first valid grounded tick.

## Platforms and ledges

- Solid platforms block movement from all directions.
- Pass-through platforms can be entered from below and landed on from above.
- Down-through behavior is explicit and requires a down command plus jump input.
- Ledge grabbing is not part of the first vertical slice; recovery is handled by movement and special actions.

## Movement locks

Movement may be restricted by:

- attack startup/recovery;
- hitstun;
- grab state;
- respawn invulnerability;
- match pause;
- match end.

Locks are represented as flags or state permissions, not scattered conditionals.

## Character-specific movement

- Captain America: standard run, one air jump, strong ground control.
- Batman: slightly lower raw speed, enhanced directional air control while using a grappling recovery.
- Future fighters must express differences through validated data or explicit, tested abilities.

## Required tests

- acceleration reaches the configured speed cap;
- releasing movement decelerates correctly;
- jump and variable jump height are deterministic;
- coyote time and input buffering work at their boundaries;
- fast fall cannot exceed its cap;
- platform landing is stable;
- movement locks prevent unauthorized control;
- respawn restores the configured state;
- identical input sequences produce identical snapshots.

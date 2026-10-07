# Combat Specification

## Status

- **Status:** Draft v1.0
- **Date:** 2026-09-27

## Attack lifecycle

Every attack uses these phases:

```text
Idle -> Startup -> Active -> Recovery -> Idle
```

An attack definition includes:

- stable ID;
- startup ticks;
- active ticks;
- recovery ticks;
- hitbox geometry;
- damage;
- base knockback;
- knockback growth;
- launch angle;
- hitstun multiplier;
- hitlag;
- priority;
- allowed cancel transitions;
- one-hit-per-target policy.

## Collision terminology

- **Hurtbox:** region that can receive an attack.
- **Hitbox:** region that applies an attack payload.
- **Grabbox:** region that begins a grab interaction.
- **Shield volume:** region that blocks or modifies attacks.

Collision geometry is separate from sprites and animation frames.

## Damage and knockback

Damage is an integer or fixed-point value stored on the fighter. Knockback is computed from attack data, target damage, target weight, and configured modifiers. The exact formula must be centralized in `KnockbackModel` and covered by tests.

A target entering hitstun cannot receive ordinary movement input until the configured control window opens. Directional influence modifies launch velocity only within its defined window.

## Shielding

- Shielding reduces or negates eligible damage according to the ruleset.
- Shield health and regeneration are explicit values.
- A broken shield causes a stunned state.
- Grabs bypass ordinary shielding but do not bypass invulnerability.

## Grabs

A grab has startup, active, whiff recovery, and successful capture states. A captured target enters a constrained state. Throw options are defined as data and apply a single deterministic launch event.

## Simultaneous events

When multiple attacks connect on the same tick:

1. sort contacts by attacker ID, then attack ID, then target ID;
2. evaluate invulnerability and already-hit rules;
3. apply all valid contacts in stable order;
4. publish results after the complete tick resolution.

The ordering is deterministic and must not depend on scene-tree traversal order.

## First fighter move sets

### Captain America

- light strike: fast shield bash;
- heavy strike: committed shield uppercut;
- special: returning shield throw;
- recovery: shield-assisted rising leap;
- defensive identity: parry window and reliable grounded control.

### Batman

- light strike: close-range baton string;
- heavy strike: committed cape-assisted sweep;
- special: tether projectile that pulls Batman toward valid surfaces;
- recovery: grapple recovery with limited uses per airborne state;
- defensive identity: traps and spacing rather than raw strength.

These names and effects are design targets for an original fan prototype. Use original implementation, timing, effects, and assets.

## Stocks and blast zones

Crossing any blast zone queues a stock-loss event after active hit resolution. The target is removed, the stock count decreases, and a respawn timer begins. Simultaneous eliminations are processed in stable order but produce a tie result when both players exhaust their stocks in the same resolution window.

## Required tests

- attack phase timing;
- hitbox activation and deactivation;
- one-hit-per-target behavior;
- simultaneous hit ordering;
- shield reduction and shield break;
- grab capture and throw;
- damage and knockback at multiple percentages;
- hitstun and directional influence boundaries;
- invulnerability;
- blast zones, stocks, respawn, and match completion.

# Project Aurora Implementation Plan

## Current milestone

Build a verified Godot 4 vertical slice with two local players, Captain America and Batman as prototype fighters, one original training stage, deterministic movement and combat, stocks, respawning, pause, restart, and headless validation.

## Implementation order

1. **Foundation** — project bootstrap, main scene, match lifecycle, input abstraction, pause/restart.
2. **Movement** — fixed-step locomotion, jumping, gravity, air control, landing, movement locks.
3. **Combat** — attack data, hitboxes, hurtboxes, damage, knockback, hitstun, shield, grab.
4. **Characters** — Captain America and Batman data/resources plus unique tested abilities.
5. **Stage** — Aegis Rooftop geometry, spawn points, platforms, camera bounds, blast zones.
6. **Integration** — two-player match, HUD, respawn, stocks, debug hitboxes, smoke scene.
7. **Verification** — deterministic tests, headless project loading, manual playtest checklist.

## Task boundaries

Implementation tasks must modify only their assigned directories. Design changes must be recorded in `docs/design/DECISIONS.md` before code changes. Every modifying task is reviewed by the opposite provider and independently checked afterward.

## Definition of done

- Clean checkout opens in Godot without missing resources.
- Main scene launches.
- Two local players can move and attack.
- Damage, knockback, stocks, respawn, and match completion work.
- Gameplay-critical behavior is covered by deterministic tests.
- Debug hitboxes can be enabled.
- The final report lists limitations and unverified features.

# Technical Architecture

## Status

- **Status:** Draft v1.0
- **Date:** 2026-09-27

## Runtime layers

```text
Input layer
  -> command frames / input buffer
Simulation layer
  -> movement, combat, collision, damage, stocks, match rules
Presentation layer
  -> animation, effects, camera, audio, UI
Persistence layer
  -> settings, character data, stage data, replay files
Verification layer
  -> deterministic tests, scenario tests, headless smoke checks
```

The simulation layer is authoritative. Presentation observes simulation state and must not directly alter damage, velocity, stocks, or match status.

## Proposed Godot structure

```text
scenes/
  main.tscn              application root
  match.tscn             match coordinator
  characters/            fighter scenes
  stages/                stage scenes
  ui/                    HUD and menus
scripts/
  core/                  simulation clock, match, ruleset
  input/                 device mapping, commands, buffering
  movement/              locomotion state and controller
  combat/                attacks, hitboxes, hurtboxes, damage
  stages/                platforms, ledges, blast zones
  ui/                    presentation only
data/
  characters/            fighter resources
  attacks/               attack resources
  stages/                stage resources
  rulesets/              stock and timing configuration
tests/
  unit/                  isolated simulation rules
  integration/           full match scenarios
```

## Ownership

- `Match`: owns players, stocks, round status, and end conditions.
- `FighterController`: owns one fighter's simulation state.
- `MovementController`: owns locomotion transitions and velocity.
- `CombatController`: owns attack phase, hit registration, damage, and hitstun.
- `Hitbox`/`Hurtbox`: expose collision geometry and metadata only.
- `StageController`: owns platforms, spawn points, ledges, and blast zones.
- `InputAdapter`: converts devices into per-tick commands.
- `HUD`: reads snapshots; it cannot mutate simulation state.

## Fixed-step simulation

Gameplay advances at a fixed tick rate of 60 ticks per second. Render frames interpolate or display the latest committed simulation state. Inputs are sampled into commands and consumed by the simulation tick.

Each tick processes events in this order:

1. read and validate commands;
2. update timers and state transitions;
3. apply movement and platform collision;
4. update attack phases and hitbox activation;
5. resolve hitbox/hurtbox interactions in stable ID order;
6. apply damage, knockback, hitstun, shielding, and invulnerability;
7. resolve blast zones and stocks;
8. publish an immutable simulation snapshot.

## Data boundaries

Character, attack, stage, and ruleset values live in Godot resources or validated data files. Runtime instances may copy those values but may not mutate shared definitions.

## Signals/events

Use typed events for:

- `fighter_spawned`;
- `attack_started`;
- `hit_confirmed`;
- `damage_changed`;
- `fighter_launched`;
- `stock_lost`;
- `fighter_respawned`;
- `match_finished`.

Events are notifications, not authority. The owning simulation system performs the state change before publishing the event.

## Replay boundary

A future replay system records game version, ruleset version, stage ID, character IDs, random seed, and input commands by tick. It does not record rendered frames as the source of truth.

## Extension rule

Adding a character should require new data and optional fighter-specific behavior, not edits to universal collision or stock logic. New mechanics must be documented before implementation and added to `DECISIONS.md`.

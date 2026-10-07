# Project Aurora

A small, original Godot 4 prototype for a local platform-fighter vertical slice inspired by the
superpower archetypes of Marvel and DC characters. It is a clean-room prototype using the
project's own code, placeholder geometry, and design rules. See
[`docs/design/AI_ENGINEERING_RULES.md`](docs/design/AI_ENGINEERING_RULES.md) and DEC-003 in
[`docs/design/DECISIONS.md`](docs/design/DECISIONS.md) for the distribution limits on protected
names.

## What works today

- Main scene with a fixed 60 Hz simulation loop, pause (Esc), restart (R), and a debug overlay (F3)
  showing hurtboxes, active hitboxes, blast zones, and the tick counter.
- Deterministic movement: ground acceleration/deceleration, air control, gravity with a fall-speed
  cap, jump with early-release short hops, one air jump, coyote time, input buffering, landing lag.
- Data-driven light and heavy attacks with startup/active/recovery phases, one hit per target per
  attack, damage, knockback that grows with damage and shrinks with weight, hitstun, and trades.
- Blast zones, stocks, invulnerable respawns, a winner or a draw, and a HUD.
- Validated JSON content for Captain America, Batman, and the original Aegis Rooftop stage.

Not yet implemented (tracked in the design specs): shielding, grabs, specials, fast fall,
down-through platforms, solid platform sides, camera tracking, menus, and controller support.

## Controls

| Action | Player 1 | Player 2 |
|---|---|---|
| Move | A / D | ← / → |
| Jump | W | ↑ |
| Light attack | J | , |
| Heavy attack | K | . |
| Special / shield (reserved) | L / S | / / ↓ |

Esc pauses, R restarts, F3 toggles the debug overlay.

## Run and verify

Requires Godot 4.2 or newer.

```bash
godot --path .                                              # play
godot --headless --path . -s res://tests/run_tests.gd       # deterministic test suite
godot --headless --path . -s res://tools/validate_project.gd  # load/compile/boot gate
```

Both headless commands exit non-zero on failure and work on a clean checkout without opening the
editor first. `godot --editor --quit` is **not** a usable gate: it exits 0 even when scenes and
scripts fail to parse.

## Layout

```text
data/                 validated JSON content (characters, stages)
docs/design/          game design, specs, decision log, engineering rules
scenes/               Main.tscn, characters/Fighter.tscn, stages/Stage.tscn
scripts/core/         MatchSimulation, FighterState, DataLoader, MatchState, Game (main scene)
scripts/combat/       AttackData validation, KnockbackModel
scripts/input/        InputRouter (keyboard -> per-tick commands)
scripts/stages/       StageView (presentation)
scripts/ui/           FighterView (presentation)
tests/run_tests.gd    headless test runner
tools/                headless project validation
```

The simulation (`MatchSimulation`, `FighterState`) is plain `RefCounted` code with no scene-tree or
physics-server state, so identical inputs always produce identical snapshots (DEC-009).

## Building it with the Stack Integration Engine

`examples/project-aurora-plan.json` in the engine repository drives Codex and Claude through the
remaining milestones with opposite-provider review and these headless checks. The engine accepts a
repository subdirectory as a project, so it can run against this directory in place:

```bash
stack-agent plan examples/project-aurora-plan.json project_aurora
```

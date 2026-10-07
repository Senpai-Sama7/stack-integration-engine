# Design Decisions

## Status

- **Status:** Active decision log
- **Date:** 2026-09-27

## Decision format

Each decision records the date, status, rationale, alternatives, and affected documents or files. Reversing a decision requires a new entry rather than rewriting history.

## DEC-001 — Use Godot 4

- **Date:** 2026-09-27
- **Status:** Accepted
- **Decision:** Build the first prototype in Godot 4.
- **Rationale:** Fast iteration, built-in 2D physics and scene tooling, and straightforward headless validation.
- **Alternatives:** Unity, Unreal, custom engine.
- **Affected:** `TECHNICAL_ARCHITECTURE.md`, project bootstrap.

## DEC-002 — Build a 2D local vertical slice first

- **Date:** 2026-09-27
- **Status:** Accepted
- **Decision:** Start with two local players, one stage, and placeholder presentation.
- **Rationale:** Validates simulation and combat before art, networking, or content scale increase.
- **Alternatives:** Start with online multiplayer or a full roster.
- **Affected:** `GAME_DESIGN.md`, `TESTING_STRATEGY.md`.

## DEC-003 — Use Marvel/DC characters only in an authorized fan prototype

- **Date:** 2026-09-27
- **Status:** Accepted with legal limitation
- **Decision:** The design may reference Marvel and DC characters and powers for private or authorized prototyping. Public distribution of protected names, likenesses, assets, music, or branding requires permission.
- **Rationale:** Separate technical prototyping from rights to distribute protected content.
- **Alternatives:** Use only original characters from the beginning.
- **Affected:** `GAME_DESIGN.md`, `CHARACTER_SPEC.md`.

## DEC-004 — Keep mechanics data-driven

- **Date:** 2026-09-27
- **Status:** Accepted
- **Decision:** Character and attack values live in validated data/resources.
- **Rationale:** Enables roster growth and balance iteration without rewriting global systems.
- **Alternatives:** Hard-code each fighter in the combat engine.
- **Affected:** `TECHNICAL_ARCHITECTURE.md`, `CHARACTER_SPEC.md`, `COMBAT_SPEC.md`.

## DEC-005 — Fixed-step deterministic simulation

- **Date:** 2026-09-27
- **Status:** Accepted
- **Decision:** Gameplay runs at 60 simulation ticks per second.
- **Rationale:** Makes combat timing reproducible and supports future replays.
- **Alternatives:** Variable-step gameplay tied to rendered frames.
- **Affected:** `TECHNICAL_ARCHITECTURE.md`, `MOVEMENT_SPEC.md`, `TESTING_STRATEGY.md`.

## DEC-006 — Placeholder visuals before final assets

- **Date:** 2026-09-27
- **Status:** Accepted
- **Decision:** Prototype with original placeholder geometry and effects.
- **Rationale:** Mechanics can be tested without blocking on art or licensing.
- **Alternatives:** Import final commercial artwork immediately.
- **Affected:** `GAME_DESIGN.md`, `STAGE_SPEC.md`.

## DEC-007 — Stage data is authoritative; blast zones must enclose all geometry

- **Date:** 2026-10-07
- **Status:** Accepted
- **Decision:** `data/stages/aegis_rooftop.json` is the source of truth for Aegis Rooftop geometry. The draft values in `STAGE_SPEC.md` placed the side blast zones 420 px from centre while the central floor is 960 px wide, which would put part of the floor beyond a blast zone. Stage validation now rejects any platform that touches or crosses a blast zone and any spawn point without a platform beneath it.
- **Rationale:** A fighter standing on the floor must never lose a stock. Contradictory spec values are caught by data validation instead of gameplay.
- **Alternatives:** Shrink the floor to fit the spec's blast zones; widen the blast zones in the spec text only.
- **Affected:** `STAGE_SPEC.md`, `scripts/core/DataLoader.gd`, `tests/run_tests.gd`.

## DEC-008 — Provisional foundation rules for collision, combat, and timers

- **Date:** 2026-10-07
- **Status:** Accepted (provisional; tuning requires a new decision)
- **Decision:**
  - Content data uses validated JSON (answers the open data-format question for the prototype).
  - All platforms are one-way: fighters land on a top surface from above; solid sides and down-through are not yet modelled.
  - Countdown timers set to N during tick t apply to ticks t+1 .. t+N (hitstun, landing lock, invulnerability).
  - Coyote time accepts a ground jump on the 4 ticks after leaving a ledge; a jump pressed while airborne is buffered for 6 ticks including the press tick.
  - `stats.damage_scale` multiplies damage the fighter deals.
  - Knockback speed = (base_knockback + knockback_growth × target damage after the hit) / target weight, launched at `angle_degrees` in the attacker's facing direction; hitstun = round(speed / 60 × hitstun_multiplier), clamped to 1..120 ticks. Implemented only in `KnockbackModel`.
  - Contacts are collected for the whole tick, then applied in attacker ID then target ID order, so trades hit both fighters.
- **Rationale:** Gives the vertical slice deterministic, testable behaviour while movement and combat specs are still drafts.
- **Alternatives:** Godot physics bodies (`CharacterBody2D`), which are harder to make bit-for-bit deterministic and cannot be tested without the physics server.
- **Affected:** `MOVEMENT_SPEC.md`, `COMBAT_SPEC.md`, `scripts/core/FighterState.gd`, `scripts/combat/KnockbackModel.gd`.

## DEC-009 — Simulation is independent of the scene tree

- **Date:** 2026-10-07
- **Status:** Accepted
- **Decision:** `MatchSimulation` and `FighterState` are plain `RefCounted` objects advanced once per physics tick. Scene nodes (`FighterView`, `StageView`, HUD) only read simulation state. Scripts are referenced through `preload` constants rather than `class_name`, so a clean checkout runs headless without an editor import step.
- **Rationale:** Implements the authoritative-simulation boundary from `TECHNICAL_ARCHITECTURE.md` and makes determinism tests possible.
- **Alternatives:** Global `class_name` registration, which requires `.godot/global_script_class_cache.cfg` from an editor import.
- **Affected:** all scripts under `scripts/`, `tests/run_tests.gd`.

## Open questions

- Should the first public-facing version use original stand-in characters instead of Marvel/DC names?
- What exact controller remapping and accessibility options are required for the first release?
- What replay format and version compatibility policy should be adopted?
- Which characters are legally authorized for any distribution beyond private testing?

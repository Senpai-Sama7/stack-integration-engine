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

## Open questions

- Should the first public-facing version use original stand-in characters instead of Marvel/DC names?
- What exact controller remapping and accessibility options are required for the first release?
- Should the first prototype use Godot resources, JSON, or a hybrid for content data?
- What replay format and version compatibility policy should be adopted?
- Which characters are legally authorized for any distribution beyond private testing?

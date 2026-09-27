# Project Aurora — Game Design

## Status

- **Status:** Draft v1.0
- **Date:** 2026-09-27
- **Engine target:** Godot 4
- **Genre:** 2D local platform fighter
- **Players:** 2 local players for the first milestone
- **Working title:** Project Aurora: Worlds Collide

## Creative direction

Project Aurora is a fan-oriented crossover platform fighter featuring selected Marvel and DC characters. It is intended for private prototyping and authorized use. Any public commercial release, distribution of official character likenesses, logos, names, voices, music, or assets requires the appropriate rights and licenses.

The game uses original code, original stage construction, original UI, original effects, and original balance values. Characters retain recognizable superpower archetypes while the implementation remains newly written.

## First playable milestone

The first vertical slice contains:

- Captain America and Batman as playable fighters;
- one original training stage, **Aegis Rooftop**;
- local two-player keyboard/controller play;
- movement, jumping, attacks, damage, knockback, shielding, grabs, stocks, blast zones, respawning, pause, and restart;
- placeholder shapes and original effects instead of production art;
- deterministic simulation tests and a headless validation path.

## Match rules

- Each player begins with 3 stocks.
- A player loses a stock after crossing a stage blast zone.
- The player returns at a configured spawn point with temporary invulnerability.
- The match ends when one player has no remaining stocks and is eliminated.
- A tie caused by simultaneous elimination enters a short sudden-death round.
- The first ruleset is local stock mode; timed and team modes are later extensions.

## Fighter roster for design validation

| Character | Power fantasy | Gameplay identity |
|---|---|---|
| Captain America | Shield mastery, elite athleticism, tactical defense | Balanced close-range fighter with shield throws, parries, and reliable recovery |
| Batman | Gadgets, grappling, preparation, mobility | Trap-oriented technical fighter with batarang-like projectiles and grappling recovery |
| Iron Man | Flight, repulsors, armor systems | Air-control specialist with ranged pressure and resource-managed mobility |
| Wonder Woman | Super strength, agility, lasso, bracers | Mid-range bruiser with command-control tools and strong defensive timing |
| Spider-Man | Wall movement, web control, agility | Highly mobile fighter with tether movement and aerial mix-ups |
| Superman | Flight, strength, heat vision | Heavy powerhouse with strong movement but vulnerable commitment windows |

The first implementation should use only Captain America and Batman. Additional characters are data-driven expansions, not changes to the global combat engine.

## Design principles

1. **Readable combat:** hitboxes, startup, active time, recovery, and effects communicate clearly.
2. **Distinct powers:** every fighter has a clear neutral plan, advantage plan, recovery plan, and weakness.
3. **No automatic victories:** superpowers create options, not unavoidable outcomes.
4. **Evidence-driven iteration:** balance changes are recorded and tested.
5. **Original presentation:** no extracted or copied commercial assets.

## Out of scope for v1

- online multiplayer;
- campaign mode;
- loot, progression, or monetization;
- voice acting and licensed music;
- final character models or animation;
- destructible stages;
- assist characters;
- ranked matchmaking.

## Acceptance criteria

- Two players can select and control fighters locally.
- Every attack has deterministic timing and collision behavior.
- Damage, knockback, stocks, respawn, and match completion work without rendering.
- A second character can be added by data/configuration and character-specific scripts without modifying global collision rules.
- The project opens from a clean checkout with no missing resources.

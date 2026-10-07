# Character Specification

## Status

- **Status:** Draft v1.0
- **Date:** 2026-09-27

## Character data model

Each character definition contains:

- `character_id`;
- display name and licensing metadata;
- base movement parameters;
- weight and fall profile;
- jump count;
- hurtbox profile;
- attack IDs;
- special ability IDs;
- recovery configuration;
- spawn and respawn presentation hooks.

The global engine owns simulation rules. Character data owns parameters. Character-specific scripts are limited to genuinely unique abilities.

## Captain America

**Role:** balanced tactical fighter

**Strengths:** reliable ground control, defensive timing, returning projectile, stable recovery.

**Weaknesses:** limited long-range pressure, predictable recovery if shield resources are exhausted.

**Base profile:**

- weight: medium-heavy;
- run speed: standard;
- air control: standard;
- air jumps: 1;
- recovery resources: 1 shield leap plus normal jump;
- preferred range: close to mid-range.

**Ability rules:**

- Shield throw travels outward and can return once.
- The shield cannot be thrown while a prior shield projectile is active.
- Parry has a short startup window and a clear whiff penalty.
- Shield leap consumes the recovery resource until landing or respawn.

## Batman

**Role:** technical mobility and trap fighter

**Strengths:** flexible approach options, tether recovery, projectile spacing, setup pressure.

**Weaknesses:** lower direct damage, weaker close-range trades, resource management complexity.

**Base profile:**

- weight: medium;
- run speed: slightly below standard;
- air control: above standard;
- air jumps: 1;
- recovery resources: 2 grapple charges, restored on landing or respawn;
- preferred range: mid-range.

**Ability rules:**

- Grapple can target only approved stage surfaces.
- A grapple has a travel timeout and can be interrupted by hitstun.
- Batarang-style projectile has a maximum active count.
- Trap deployment consumes a setup window and cannot be placed inside another fighter.

## Future roster candidates

The following are design references for later implementation:

- Iron Man: flight fuel and repulsor pressure;
- Wonder Woman: lasso control and bracer defense;
- Spider-Man: tether mobility and wall interaction;
- Superman: high weight, flight, and powerful committed attacks.

No future fighter may be added without a move-set document, resource schema, test matrix, and balance review.

## Accessibility and readability

Every fighter must have:

- distinct silhouette or color treatment in the prototype;
- attack phase indicators in debug mode;
- readable recovery and invulnerability cues;
- remappable controls;
- no mechanic that depends solely on color.

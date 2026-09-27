# Stage Specification

## Status

- **Status:** Draft v1.0
- **Date:** 2026-09-27

## First stage: Aegis Rooftop

Aegis Rooftop is an original training stage: a broad central rooftop with two elevated side platforms and a lower center platform. It is designed to expose movement, recovery, projectile spacing, and blast-zone behavior without reproducing any commercial stage.

## Geometry

- central floor: 960 px wide;
- left platform: 300 px wide, raised 150 px;
- right platform: 300 px wide, raised 150 px;
- lower center platform: 260 px wide, below the main floor;
- left/right side blast zones: 420 px from stage center;
- upper blast zone: 900 px above stage origin;
- lower blast zone: 500 px below stage origin.

Values are starting targets and must be stored in stage data.

## Stage data

A stage definition contains:

- stable stage ID;
- collision shapes;
- platform type and one-way settings;
- spawn points;
- camera bounds;
- blast zones;
- legal recovery surfaces;
- background and audio presentation references.

## Spawn rules

- Players spawn at separate configured points.
- Spawn points must be inside the legal play region and not overlap solid geometry.
- Respawn points are validated at stage load.
- Respawn invulnerability lasts a configured number of ticks.

## Camera

The camera tracks the bounding box of active fighters with configurable horizontal and vertical margins. It clamps to stage camera bounds and does not affect simulation coordinates.

## Future stages

Future original locations may include:

- a moving research platform;
- a suspended city transit hub;
- a cosmic observatory;
- a magical library arena.

Each new stage requires geometry validation, spawn validation, blast-zone tests, and a manual readability review.

## Required tests

- solid platform collision;
- pass-through platform landing;
- down-through behavior;
- spawn-point validity;
- stage bounds and blast zones;
- camera bounds;
- deterministic stage loading;
- recovery surface validation.

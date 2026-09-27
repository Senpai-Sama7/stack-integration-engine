# Project Aurora

Original Godot 4 local-fighter prototype with deterministic 60 Hz combat simulation.

## Requirements

- Godot 4.2+ available as `godot4` (or `godot`)

## Run the game

```bash
godot4 --path project_aurora
```

If your binary is named `godot`, use:

```bash
godot --path project_aurora
```

## Run headless gameplay tests

```bash
godot4 --headless --path project_aurora --script res://tests/run_tests.gd
```

## Headless project-load validation

```bash
godot4 --headless --path project_aurora --quit
```

## Controls

Player 1:
- `A` / `D`: move
- `W`: jump
- `J`: light
- `K`: heavy
- `L`: special
- `S`: shield

Player 2:
- `Left` / `Right`: move
- `Up`: jump
- `,`: light
- `.`: heavy
- `/`: special
- `Down`: shield

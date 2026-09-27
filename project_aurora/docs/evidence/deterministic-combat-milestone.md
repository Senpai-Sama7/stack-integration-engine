# Deterministic Combat Milestone Evidence

## Files changed

- `project_aurora/scenes/Main.tscn`
- `project_aurora/scenes/Stage.tscn`
- `project_aurora/scenes/fighters/Fighter.tscn`
- `project_aurora/scripts/core/Game.gd`
- `project_aurora/scripts/core/Fighter.gd`
- `project_aurora/scripts/combat/AttackData.gd`
- `project_aurora/scripts/input/InputRouter.gd`
- `project_aurora/tests/run_tests.gd`
- `project_aurora/README.md`

## Validation commands run

1. Inspect `project_aurora` tree

```bash
find project_aurora -print | sort
```

Result: listed all directories/files under `project_aurora/` and confirmed full-tree inspection before edits.

2. Read all existing `project_aurora` files

```bash
for f in $(find project_aurora -type f | sort); do echo "===== $f"; sed -n '1,220p' "$f"; done
```

Result: identified script wiring corruption and scene resource ordering issues.

3. Godot availability check

```bash
if command -v godot4 >/dev/null 2>&1; then godot4 --version; elif command -v godot >/dev/null 2>&1; then godot --version; else echo 'Godot binary not found'; fi
```

Result: `Godot binary not found`.

## Runtime validation status

- `godot4 --headless --path project_aurora --quit`: **not run** (Godot unavailable)
- `godot4 --headless --path project_aurora --script res://tests/run_tests.gd`: **not run** (Godot unavailable)
- Editor/project load validation: **not run** (Godot unavailable)

## Notes

Runtime/headless execution could not be performed in this environment because no Godot executable (`godot4`/`godot`) is installed.

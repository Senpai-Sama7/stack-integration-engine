# Project Aurora AI Engineering Rules

## Scope

Project Aurora is an original Godot 4 platform-fighter prototype using Marvel/DC characters only for private or appropriately authorized fan development. Public distribution of protected names, likenesses, logos, music, or assets requires the necessary rights.

## Engineering rules

- Inspect the repository before changing files.
- Do not copy proprietary source code, extracted assets, animation data, music, or game-specific implementation details.
- Use original code, original effects, original stage layouts, and original balance values.
- Separate input, deterministic simulation, presentation, UI, and persistence.
- Use fixed-step gameplay calculations.
- Keep character and attack values in validated data/resources.
- Do not silently invent gameplay rules while implementing code; update the specification and decision log first.
- Add or update tests for every practical gameplay rule.
- Never claim a test passed unless it was actually run.
- Treat AI output as a proposal until independently reviewed and verified.
- Keep changes within the declared task paths.

## Required task report

Every implementation or review task must report:

1. Summary
2. Files changed
3. Design decisions
4. Tests run with exact commands and results
5. Known limitations
6. Follow-up risks

## Completion standard

A task is incomplete if it has missing practical tests, undocumented gameplay constants, hidden global state, missing-resource errors, unverified claims, or changes outside its assigned scope.

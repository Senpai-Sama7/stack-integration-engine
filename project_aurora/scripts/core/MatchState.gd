extends RefCounted
## Match lifecycle states and result sentinels shared by simulation and presentation.

enum State {
	READY,
	FIGHT,
	PAUSED,
	FINISHED,
}

## `MatchSimulation.winner` when no result exists yet.
const NO_WINNER := -1
## `MatchSimulation.winner` when every remaining fighter is eliminated in one tick.
const DRAW := -2

extends Node2D

const FighterScene = preload("res://scenes/fighters/Fighter.tscn")
const InputRouter = preload("res://scripts/input/InputRouter.gd")
const MatchState = preload("res://scripts/core/MatchState.gd")

const TICK_RATE := 1.0 / 60.0
const FLOOR_Y := 180.0

@export var match_state: int = MatchState.State.READY

var tick_accumulator := 0.0
var fighters_by_player: Dictionary = {}
var input_router: InputRouter

func _ready() -> void:
    input_router = InputRouter.new()
    _spawn_fighters()
    match_state = MatchState.State.FIGHT
    print("Project Aurora loaded.")

func _spawn_fighters() -> void:
    for player_id in ["P1", "P2"]:
        var fighter_instance = FighterScene.instantiate()
        var fighter_name := "Captain America" if player_id == "P1" else "Batman"
        var spawn_x := -180.0 if player_id == "P1" else 180.0
        var color := Color(0.82, 0.20, 0.20, 1.0) if player_id == "P1" else Color(0.10, 0.40, 1.0, 1.0)
        fighter_instance.initialize(fighter_name, Vector2(spawn_x, 0.0), color)
        add_child(fighter_instance)
        fighters_by_player[player_id] = fighter_instance

func _process(delta: float) -> void:
    if match_state == MatchState.State.PAUSED or match_state == MatchState.State.FINISHED:
        return

    tick_accumulator += delta
    while tick_accumulator >= TICK_RATE:
        _fixed_tick()
        tick_accumulator -= TICK_RATE

func _fixed_tick() -> void:
    input_router.update_state_from_keyboard()

    for player_id in ["P1", "P2"]:
        var fighter = fighters_by_player.get(player_id)
        if fighter == null:
            continue
        var actions = input_router.read_actions(player_id)
        fighter.update(actions, TICK_RATE)

    _resolve_match_state()

func _resolve_match_state() -> void:
    var active = 0
    for fighter in fighters_by_player.values():
        if fighter.stocks > 0:
            active += 1
    if active <= 1:
        match_state = MatchState.State.FINISHED
        var winner = ""
        for fighter in fighters_by_player.values():
            if fighter.stocks > 0:
                winner = fighter.fighter_name
                break
        print("Match finished. Winner: %s" % winner)

func _unhandled_input(event: InputEvent) -> void:
    input_router.handle_event(event)

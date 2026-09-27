extends Node2D
class_name Game

const MatchState = preload("res://scripts/core/MatchState.gd")
const Fighter = preload("res://scripts/core/Fighter.gd")
const InputRouter = preload("res://scripts/input/InputRouter.gd")

@export var player_names: Array[String] = ["Captain America", "Batman"]
@export var match_state: int = MatchState.State.READY

var fighters: Array[Fighter] = []
var input_router: InputRouter
var stage_name := "Aegis Rooftop"
var tick_count := 0

func _ready() -> void:
    input_router = InputRouter.new()
    _initialize_fighters()
    _start_match()
    print("Project Aurora loaded. Match ready: %s" % stage_name)

func _initialize_fighters() -> void:
    fighters.clear()
    fighters.append(Fighter.new("Captain America", Vector2(-180.0, 0.0), Color(0.8, 0.2, 0.2, 1.0)))
    fighters.append(Fighter.new("Batman", Vector2(180.0, 0.0), Color(0.1, 0.4, 1.0, 1.0)))

func _start_match() -> void:
    match_state = MatchState.State.FIGHT
    for fighter in fighters:
        fighter.reset_to_spawn()

func _process(_delta: float) -> void:
    if match_state == MatchState.State.PAUSED:
        return

    tick_count += 1
    for fighter in fighters:
        var actions: Dictionary = input_router.read_actions(fighter.name)
        fighter.update(actions, _delta)

    _resolve_match_state()

func _resolve_match_state() -> void:
    var active_fighters := 0
    for fighter in fighters:
        if fighter.stocks > 0:
            active_fighters += 1

    if active_fighters <= 1:
        match_state = MatchState.State.FINISHED
        print("Match finished. Winner: %s" % fighters.filter(func(item): return item.stocks > 0)[0].name)

func _input(event: InputEvent) -> void:
    input_router.handle_event(event)

func _unhandled_input(event: InputEvent) -> void:
    input_router.handle_event(event)

extends Node2D
## Main scene controller: loads validated content, owns the fixed-step loop, and keeps
## presentation in sync with the authoritative MatchSimulation.
##
## Controls: Esc pauses/resumes, R restarts, F3 toggles debug hitboxes and blast zones.

const DataLoader = preload("res://scripts/core/DataLoader.gd")
const InputRouter = preload("res://scripts/input/InputRouter.gd")
const MatchSimulation = preload("res://scripts/core/MatchSimulation.gd")
const MatchState = preload("res://scripts/core/MatchState.gd")
const FighterScene = preload("res://scenes/characters/Fighter.tscn")

var simulation = null
var input_router = InputRouter.new()
var fighter_views: Array = []
var load_errors := PackedStringArray()
var show_debug := false

@onready var stage_view: Node2D = $Stage
@onready var fighters_root: Node2D = $Fighters
@onready var status_label: Label = $HUD/Status


func _ready() -> void:
	var content := DataLoader.load_match_content()
	load_errors = content["errors"]
	if not load_errors.is_empty():
		for error in load_errors:
			push_error(error)
		status_label.text = "Content failed validation:\n" + "\n".join(load_errors)
		return
	simulation = MatchSimulation.new()
	simulation.setup(content["stage"], content["characters"])
	stage_view.configure(content["stage"])
	for fighter in simulation.fighters:
		var view := FighterScene.instantiate()
		fighters_root.add_child(view)
		view.bind(fighter)
		fighter_views.append(view)
	simulation.start()
	print("Project Aurora loaded: %d fighters on %s." % [simulation.fighters.size(), content["stage"]["display_name"]])
	_refresh()


func _physics_process(_delta: float) -> void:
	# physics/common/physics_ticks_per_second is 60; the simulation always advances by
	# exactly one fixed tick, independent of render frame rate.
	if simulation == null:
		return
	simulation.step(input_router.sample_commands(simulation.fighters.size()))
	_refresh()


func _unhandled_input(event: InputEvent) -> void:
	if simulation == null or not (event is InputEventKey) or not event.pressed or event.echo:
		return
	match event.physical_keycode:
		KEY_ESCAPE:
			simulation.toggle_pause()
		KEY_R:
			simulation.restart()
		KEY_F3:
			show_debug = not show_debug
			stage_view.set_debug(show_debug)
		_:
			return
	_refresh()


func _refresh() -> void:
	for view in fighter_views:
		view.show_hitboxes = show_debug
		view.sync()
	var lines := PackedStringArray()
	for fighter in simulation.fighters:
		lines.append("%s  %d%%  stocks %d" % [fighter.display_name, int(round(fighter.damage)), fighter.stocks])
	match simulation.state:
		MatchState.State.PAUSED:
			lines.append("PAUSED (Esc to resume)")
		MatchState.State.FINISHED:
			if simulation.winner == MatchState.DRAW:
				lines.append("Draw! Press R to restart.")
			else:
				lines.append("%s wins! Press R to restart." % simulation.fighters[simulation.winner].display_name)
	if show_debug:
		lines.append("tick %d" % simulation.tick)
	status_label.text = "\n".join(lines)

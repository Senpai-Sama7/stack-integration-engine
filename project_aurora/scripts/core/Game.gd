extends Node2D

const FighterScene = preload("res://scenes/fighters/Fighter.tscn")
const Fighter = preload("res://scripts/core/Fighter.gd")
const InputRouter = preload("res://scripts/input/InputRouter.gd")
const MatchState = preload("res://scripts/core/MatchState.gd")

const PLAYER_ORDER := ["P1", "P2"]
const TICK_DELTA := 1.0 / 60.0
const BLAST_LEFT := -640.0
const BLAST_RIGHT := 640.0
const BLAST_TOP := -200.0
const BLAST_BOTTOM := 500.0

@export var match_state: int = MatchState.State.READY
@export var winner_name: String = ""

var fighters_by_player: Dictionary = {}
var input_router: InputRouter
var initialized: bool = false

func _ready() -> void:
	initialize_match()

func initialize_match() -> void:
	if initialized:
		return
	input_router = InputRouter.new()
	_spawn_fighters()
	winner_name = ""
	match_state = MatchState.State.FIGHT
	initialized = true

func _spawn_fighters() -> void:
	if not fighters_by_player.is_empty():
		return

	var spawn_definitions := {
		"P1": {
			"name": "Captain America",
			"spawn": Vector2(-180.0, 0.0),
			"color": Color(0.82, 0.20, 0.20, 1.0),
		},
		"P2": {
			"name": "Batman",
			"spawn": Vector2(180.0, 0.0),
			"color": Color(0.10, 0.40, 1.0, 1.0),
		},
	}

	for player_id in PLAYER_ORDER:
		var fighter_instance: Fighter = FighterScene.instantiate()
		var def = spawn_definitions[player_id]
		fighter_instance.initialize(player_id, def["name"], def["spawn"], def["color"], 3)
		add_child(fighter_instance)
		fighters_by_player[player_id] = fighter_instance

func _physics_process(_delta: float) -> void:
	simulate_tick({}, true, true)

func simulate_tick(actions_by_player: Dictionary = {}, use_keyboard: bool = false, use_physics: bool = false) -> void:
	if match_state == MatchState.State.PAUSED or match_state == MatchState.State.FINISHED:
		return
	if use_keyboard:
		input_router.update_state_from_keyboard()

	for player_id in PLAYER_ORDER:
		var fighter: Fighter = fighters_by_player.get(player_id)
		if fighter == null:
			continue
		var actions := _default_actions()
		if actions_by_player.has(player_id):
			actions = _merge_actions(actions_by_player[player_id])
		else:
			actions = _merge_actions(input_router.read_actions(player_id))
		fighter.simulate(actions, TICK_DELTA, use_physics)

	_resolve_combat_contacts()
	_resolve_blast_zone_losses()
	_update_match_state()

func _resolve_combat_contacts() -> void:
	for attacker_id in PLAYER_ORDER:
		var attacker: Fighter = fighters_by_player.get(attacker_id)
		if attacker == null or attacker.is_eliminated or not attacker.is_attack_active():
			continue
		var hitbox := attacker.get_active_hitbox_rect()
		for target_id in PLAYER_ORDER:
			if target_id == attacker_id:
				continue
			var target: Fighter = fighters_by_player.get(target_id)
			if target == null or target.is_eliminated:
				continue
			if not attacker.can_hit_target(target.fighter_id):
				continue
			if not hitbox.intersects(target.get_hurtbox_rect()):
				continue
			var hit_payload := attacker.build_hit_payload()
			if target.receive_hit(hit_payload):
				attacker.register_hit_target(target.fighter_id)

func _resolve_blast_zone_losses() -> void:
	for player_id in PLAYER_ORDER:
		var fighter: Fighter = fighters_by_player.get(player_id)
		if fighter == null or fighter.is_eliminated:
			continue
		var out_of_bounds := (
			fighter.global_position.x < BLAST_LEFT
			or fighter.global_position.x > BLAST_RIGHT
			or fighter.global_position.y < BLAST_TOP
			or fighter.global_position.y > BLAST_BOTTOM
		)
		if out_of_bounds:
			fighter.lose_stock()

func _update_match_state() -> void:
	var remaining: Array[Fighter] = []
	for player_id in PLAYER_ORDER:
		var fighter: Fighter = fighters_by_player.get(player_id)
		if fighter != null and fighter.stocks > 0:
			remaining.append(fighter)

	if remaining.size() > 1:
		match_state = MatchState.State.FIGHT
		winner_name = ""
		return

	match_state = MatchState.State.FINISHED
	if remaining.size() == 1:
		winner_name = remaining[0].fighter_name
		print("Match finished. Winner: %s" % winner_name)
	else:
		winner_name = ""
		print("Match finished. Tie.")

func get_fighter(player_id: String) -> Fighter:
	return fighters_by_player.get(player_id)

func _merge_actions(source: Dictionary) -> Dictionary:
	var merged := _default_actions()
	for key in merged.keys():
		merged[key] = bool(source.get(key, false))
	return merged

func _default_actions() -> Dictionary:
	return {
		"left": false,
		"right": false,
		"jump": false,
		"light": false,
		"heavy": false,
		"special": false,
		"shield": false,
	}

func _unhandled_input(event: InputEvent) -> void:
	if input_router != null:
		input_router.handle_event(event)

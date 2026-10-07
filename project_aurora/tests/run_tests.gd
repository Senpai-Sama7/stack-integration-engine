extends SceneTree
## Deterministic headless test suite.
##
##   godot --headless --path . -s res://tests/run_tests.gd
##
## Every `test_*` method must return `true` when it finishes; a script error that
## aborts a test returns null and is reported as a failure, never as a pass. The exit
## code is non-zero when any test fails or when no tests ran.

const AttackData = preload("res://scripts/combat/AttackData.gd")
const DataLoader = preload("res://scripts/core/DataLoader.gd")
const FighterState = preload("res://scripts/core/FighterState.gd")
const InputRouter = preload("res://scripts/input/InputRouter.gd")
const KnockbackModel = preload("res://scripts/combat/KnockbackModel.gd")
const MatchSimulation = preload("res://scripts/core/MatchSimulation.gd")
const MatchState = preload("res://scripts/core/MatchState.gd")

const TICK := 1.0 / 60.0

var _failures := PackedStringArray()


func _initialize() -> void:
	# Nodes added to the tree are only readied once the main loop runs, so the suite
	# starts on the first processed frame instead of inside _initialize.
	process_frame.connect(_run_all, CONNECT_ONE_SHOT)


func _run_all() -> void:
	var names := []
	for method in get_method_list():
		if String(method["name"]).begins_with("test_"):
			names.append(method["name"])
	names.sort()
	var passed := 0
	var failed := 0
	for test_name in names:
		_failures = PackedStringArray()
		var finished: Variant = call(test_name)
		if finished != true:
			_failures.append("test aborted before completion (script error)")
		if _failures.is_empty():
			passed += 1
			print("PASS %s" % test_name)
		else:
			failed += 1
			print("FAIL %s" % test_name)
			for failure in _failures:
				print("    %s" % failure)
	print("%d passed, %d failed" % [passed, failed])
	quit(1 if failed > 0 or passed == 0 else 0)


# --- helpers -----------------------------------------------------------------------


func _check(condition: bool, message: String) -> void:
	if not condition:
		_failures.append(message)


func _content() -> Dictionary:
	return DataLoader.load_match_content()


func _character(overrides: Dictionary = {}) -> Dictionary:
	var character: Dictionary = DataLoader.load_json(DataLoader.CHARACTER_PATHS[0])["data"].duplicate(true)
	for key in overrides:
		character["stats"][key] = overrides[key]
	return character


func _flat_stage(width: float = 4000.0, ground_y: float = 0.0) -> Dictionary:
	return {
		"platforms": [{"x": 0.0, "y": ground_y, "width": width, "height": 20.0, "type": "ground"}],
		"blast_zones": {"left": -3000.0, "right": 3000.0, "top": -3000.0, "bottom": ground_y + 3000.0},
		"spawn_points": [{"x": 0.0, "y": ground_y}, {"x": 40.0, "y": ground_y}],
		"respawn_invulnerability_ticks": 90,
	}


func _command(buttons: Array = []) -> Dictionary:
	var command := InputRouter.neutral_command()
	for button in buttons:
		command[button] = true
	return command


func _fighter(stage: Dictionary, at: Vector2 = Vector2.ZERO, overrides: Dictionary = {}):
	var fighter := FighterState.new()
	fighter.configure(0, _character(overrides))
	fighter.spawn(at)
	return fighter


func _settle(fighter, stage: Dictionary, ticks: int = 6) -> void:
	for _i in ticks:
		fighter.step(_command(), stage["platforms"], TICK)


func _match(stage: Dictionary, characters: Array = []):
	var simulation := MatchSimulation.new()
	simulation.setup(stage, characters if not characters.is_empty() else [_character(), _character()])
	simulation.start()
	return simulation


func _neutral_commands(count: int = 2) -> Array:
	var commands := []
	for _i in count:
		commands.append(_command())
	return commands


# --- content -----------------------------------------------------------------------


func test_shipped_content_is_valid() -> bool:
	var content := _content()
	_check(content["errors"].is_empty(), "shipped content errors: %s" % [content["errors"]])
	_check(content["characters"].size() == 2, "expected two fighters")
	for character in content["characters"]:
		for attack in character["attacks"].values():
			var normalized := AttackData.normalize(attack)
			_check(normalized["hitbox"] is Rect2, "hitbox normalises to Rect2")
	return true


func test_validation_rejects_broken_content() -> bool:
	var stage: Dictionary = _content()["stage"].duplicate(true)
	stage["blast_zones"]["left"] = -300.0
	var stage_errors := DataLoader.validate_stage(stage, "stage")
	_check("\n".join(stage_errors).contains("blast zone"), "floor beyond a blast zone is rejected")

	var floating: Dictionary = _content()["stage"].duplicate(true)
	floating["spawn_points"][0] = {"x": -600.0, "y": 0.0}
	_check(
		"\n".join(DataLoader.validate_stage(floating, "stage")).contains("no platform"),
		"spawn point without support is rejected"
	)

	var character := _character()
	character["stats"].erase("run_speed")
	character["attacks"]["light"]["damage"] = -1.0
	var character_errors := "\n".join(DataLoader.validate_character(character, "c"))
	_check(character_errors.contains("run_speed"), "missing stat is rejected")
	_check(character_errors.contains("damage must not be negative"), "negative damage is rejected")

	var missing := DataLoader.load_match_content("res://data/stages/missing.json")
	_check("\n".join(missing["errors"]).contains("missing data file"), "missing file is reported")
	return true


# --- movement ----------------------------------------------------------------------


func test_fighter_rests_stably_on_ground() -> bool:
	var stage := _flat_stage()
	var fighter = _fighter(stage)
	_settle(fighter, stage)
	for _i in 120:
		fighter.step(_command(), stage["platforms"], TICK)
		_check(fighter.grounded, "fighter stays grounded")
	_check(fighter.position == Vector2.ZERO, "position unchanged at rest: %s" % fighter.position)
	_check(fighter.velocity == Vector2.ZERO, "no drift at rest")
	return true


func test_ground_acceleration_caps_at_run_speed_and_decelerates() -> bool:
	var stage := _flat_stage()
	var fighter = _fighter(stage)
	_settle(fighter, stage)
	var max_speed := 0.0
	for _i in 30:
		fighter.step(_command(["right"]), stage["platforms"], TICK)
		max_speed = maxf(max_speed, fighter.velocity.x)
	_check(is_equal_approx(fighter.velocity.x, fighter.run_speed), "reaches run speed")
	_check(max_speed <= fighter.run_speed, "never exceeds run speed")
	_check(fighter.facing == 1, "faces movement direction")
	var stop_ticks := 0
	while fighter.velocity.x > 0.0 and stop_ticks < 60:
		fighter.step(_command(), stage["platforms"], TICK)
		stop_ticks += 1
	var expected := int(ceil(fighter.run_speed / (FighterState.GROUND_DECELERATION * TICK)))
	_check(stop_ticks == expected, "stops in %d ticks, took %d" % [expected, stop_ticks])
	return true


func test_jump_is_deterministic_with_one_air_jump() -> bool:
	var stage := _flat_stage()
	var apexes := []
	for _run in 2:
		var fighter = _fighter(stage)
		_settle(fighter, stage)
		var apex := 0.0
		for _i in 20:
			fighter.step(_command(["jump"]), stage["platforms"], TICK)
			apex = minf(apex, fighter.position.y)
		apexes.append(apex)
	_check(apexes[0] == apexes[1], "identical jumps reach identical apexes")
	_check(apexes[0] < -60.0, "jump leaves the ground meaningfully: %s" % apexes[0])

	var jumper = _fighter(stage)
	_settle(jumper, stage)
	jumper.step(_command(["jump"]), stage["platforms"], TICK)
	jumper.step(_command(), stage["platforms"], TICK)
	jumper.step(_command(["jump"]), stage["platforms"], TICK)
	_check(jumper.air_jumps_remaining == 0, "air jump consumed")
	_check(
		is_equal_approx(jumper.velocity.y, -jumper.jump_impulse + FighterState.GRAVITY * TICK),
		"air jump resets vertical velocity"
	)
	jumper.step(_command(), stage["platforms"], TICK)
	var before: float = jumper.velocity.y
	jumper.step(_command(["jump"]), stage["platforms"], TICK)
	_check(
		is_equal_approx(jumper.velocity.y, before + FighterState.GRAVITY * TICK),
		"no third jump without air jumps"
	)
	return true


func test_early_release_shortens_the_jump() -> bool:
	var stage := _flat_stage()
	var held = _fighter(stage)
	var tapped = _fighter(stage)
	_settle(held, stage)
	_settle(tapped, stage)
	var held_apex := 0.0
	var tapped_apex := 0.0
	for tick in 40:
		held.step(_command(["jump"]), stage["platforms"], TICK)
		tapped.step(_command(["jump"] if tick == 0 else []), stage["platforms"], TICK)
		held_apex = minf(held_apex, held.position.y)
		tapped_apex = minf(tapped_apex, tapped.position.y)
	_check(tapped_apex > held_apex, "short hop (%s) is lower than full jump (%s)" % [tapped_apex, held_apex])
	return true


func _walk_off_then_jump(delay: int) -> int:
	var stage := _flat_stage(200.0)
	var fighter = _fighter(stage, Vector2(90.0, 0.0))
	_settle(fighter, stage)
	var guard := 0
	while fighter.grounded and guard < 60:
		fighter.step(_command(["right"]), stage["platforms"], TICK)
		guard += 1
	for tick in range(1, delay):
		fighter.step(_command(), stage["platforms"], TICK)
	fighter.step(_command(["jump"]), stage["platforms"], TICK)
	_check(fighter.velocity.y < 0.0, "jump fires %d ticks after leaving the ledge" % delay)
	return fighter.air_jumps_remaining


func test_coyote_time_boundary() -> bool:
	for delay in range(1, 5):
		_check(_walk_off_then_jump(delay) == 1, "tick %d after the ledge is a ground jump" % delay)
	_check(_walk_off_then_jump(5) == 0, "tick 5 after the ledge spends the air jump")
	return true


func _buffered_jump_fires(press_before_landing: int) -> bool:
	var stage := _flat_stage()
	var probe = _fighter(stage, Vector2(0.0, -200.0), {"air_jumps": 0})
	var landing_tick := 0
	while not probe.grounded and landing_tick < 200:
		probe.step(_command(), stage["platforms"], TICK)
		landing_tick += 1
	var fighter = _fighter(stage, Vector2(0.0, -200.0), {"air_jumps": 0})
	for tick in range(1, landing_tick + 10):
		var buttons := ["jump"] if tick == landing_tick - press_before_landing else []
		fighter.step(_command(buttons), stage["platforms"], TICK)
		if tick > landing_tick and fighter.velocity.y < 0.0:
			return true
	return false


func test_input_buffer_boundary() -> bool:
	for offset in range(0, 6):
		_check(_buffered_jump_fires(offset), "jump pressed %d ticks before landing is buffered" % offset)
	_check(not _buffered_jump_fires(6), "jump pressed 6 ticks before landing has expired")
	return true


func test_landing_lock_blocks_control_for_two_ticks() -> bool:
	var stage := _flat_stage()
	var fighter = _fighter(stage, Vector2(0.0, -100.0))
	while not fighter.grounded:
		fighter.step(_command(), stage["platforms"], TICK)
	_check(fighter.landing_lock_ticks == FighterState.LANDING_LOCK_TICKS, "landing lock starts")
	for tick in FighterState.LANDING_LOCK_TICKS:
		fighter.step(_command(["right"]), stage["platforms"], TICK)
		_check(fighter.velocity.x == 0.0, "locked on tick %d after landing" % (tick + 1))
	fighter.step(_command(["right"]), stage["platforms"], TICK)
	_check(fighter.velocity.x > 0.0, "control returns after the lock")
	return true


func test_fall_speed_is_capped() -> bool:
	var stage := _flat_stage(4000.0, 20000.0)
	var fighter = _fighter(stage)
	for _i in 180:
		fighter.step(_command(), stage["platforms"], TICK)
		_check(fighter.velocity.y <= FighterState.MAX_FALL_SPEED, "fall speed capped")
	_check(fighter.velocity.y == FighterState.MAX_FALL_SPEED, "terminal velocity reached")
	return true


# --- combat ------------------------------------------------------------------------


func test_attack_phases_follow_data() -> bool:
	var stage := _flat_stage()
	var fighter = _fighter(stage)
	_settle(fighter, stage)
	var attack: Dictionary = fighter.attacks["light"]
	var phases := []
	fighter.step(_command(["light"]), stage["platforms"], TICK)
	phases.append(fighter.attack_phase())
	for _i in AttackData.total_ticks(attack):
		fighter.step(_command(), stage["platforms"], TICK)
		phases.append(fighter.attack_phase())
		_check(fighter.active_hitbox().has_area() == (phases[-1] == "active"), "hitbox only while active")
	_check(phases.count("startup") == attack["startup_ticks"], "startup ticks match data")
	_check(phases.count("active") == attack["active_ticks"], "active ticks match data")
	_check(phases.count("recovery") == attack["recovery_ticks"], "recovery ticks match data")
	_check(phases[-1] == "idle", "attack ends idle")
	return true


func _run_attack(simulation, attackers: Array, ticks: int = 30) -> void:
	for tick in ticks:
		var commands := _neutral_commands()
		if tick == 0:
			for index in attackers:
				commands[index] = _command(["light"])
		simulation.step(commands)


func _settled_match():
	var simulation = _match(_flat_stage())
	for _i in 6:
		simulation.step(_neutral_commands())
	return simulation


func test_hit_applies_damage_once_and_launches_away() -> bool:
	var simulation = _settled_match()
	var target = simulation.fighters[1]
	var attack: Dictionary = simulation.fighters[0].attacks["light"]
	var contacts := 0
	for tick in 30:
		var commands := _neutral_commands()
		if tick == 0:
			commands[0] = _command(["light"])
		simulation.step(commands)
		contacts += simulation.last_contacts.size()
		if simulation.last_contacts.size() == 1:
			_check(target.velocity.x > 0.0, "launched away from the attacker")
			_check(target.velocity.y < 0.0, "launched upward")
			_check(target.hitstun_ticks > 0, "hitstun applied")
	_check(contacts == 1, "one hit per target per attack, saw %d" % contacts)
	_check(is_equal_approx(target.damage, attack["damage"]), "damage %s applied once" % target.damage)
	return true


func test_hitstun_blocks_control_until_it_expires() -> bool:
	var simulation = _settled_match()
	var target = simulation.fighters[1]
	var hit := false
	var guard := 0
	while not hit and guard < 30:
		var commands := _neutral_commands()
		if guard == 0:
			commands[0] = _command(["light"])
		simulation.step(commands)
		hit = not simulation.last_contacts.is_empty()
		guard += 1
	_check(hit, "attack connected")
	var stun: int = target.hitstun_ticks
	for _i in stun:
		var commands := _neutral_commands()
		commands[1] = _command(["left"])
		simulation.step(commands)
		_check(target.facing == 1, "no turning during hitstun")
	var commands := _neutral_commands()
	commands[1] = _command(["left"])
	simulation.step(commands)
	_check(target.facing == -1, "control returns after hitstun")
	return true


func test_invulnerability_blocks_hits() -> bool:
	var simulation = _settled_match()
	simulation.fighters[1].invulnerable_ticks = 60
	_run_attack(simulation, [0])
	_check(simulation.fighters[1].damage == 0.0, "invulnerable target took no damage")
	return true


func test_simultaneous_attacks_trade() -> bool:
	var simulation = _settled_match()
	simulation.fighters[1].facing = -1
	_run_attack(simulation, [0, 1])
	_check(simulation.fighters[0].damage > 0.0, "first fighter was hit")
	_check(simulation.fighters[1].damage > 0.0, "second fighter was hit")
	return true


func test_knockback_scales_with_damage_and_weight() -> bool:
	var attack := AttackData.normalize(_character()["attacks"]["light"])
	_check(
		KnockbackModel.launch_speed(attack, 100.0, 1.0) > KnockbackModel.launch_speed(attack, 0.0, 1.0),
		"more damage launches further"
	)
	_check(
		KnockbackModel.launch_speed(attack, 50.0, 1.4) < KnockbackModel.launch_speed(attack, 50.0, 1.0),
		"heavier fighters launch less"
	)
	var left := KnockbackModel.launch_velocity(attack, 0.0, 1.0, -1)
	_check(left.x < 0.0, "launch follows attacker facing")
	return true


# --- stocks and match lifecycle ----------------------------------------------------


func test_blast_zone_costs_a_stock_and_respawns_protected() -> bool:
	var simulation = _settled_match()
	var fighter = simulation.fighters[1]
	fighter.position.x = simulation.stage["blast_zones"]["right"] + 1.0
	simulation.step(_neutral_commands())
	_check(fighter.stocks == fighter.max_stocks - 1, "stock lost")
	_check(fighter.position == simulation.spawn_point(1), "respawned at spawn point")
	_check(fighter.invulnerable_ticks == 90, "respawn invulnerability from stage data")
	_check(fighter.damage == 0.0, "damage reset on respawn")
	_check(simulation.state == MatchState.State.FIGHT, "match continues")
	return true


func test_last_stock_ends_match_with_winner() -> bool:
	var simulation = _settled_match()
	var loser = simulation.fighters[1]
	loser.stocks = 1
	loser.position.y = simulation.stage["blast_zones"]["bottom"] + 1.0
	simulation.step(_neutral_commands())
	_check(loser.eliminated, "fighter eliminated")
	_check(simulation.state == MatchState.State.FINISHED, "match finished")
	_check(simulation.winner == 0, "remaining fighter wins")
	var tick: int = simulation.tick
	simulation.step(_neutral_commands())
	_check(simulation.tick == tick, "finished match no longer advances")
	return true


func test_simultaneous_elimination_is_a_draw() -> bool:
	var simulation = _settled_match()
	for fighter in simulation.fighters:
		fighter.stocks = 1
		fighter.position.y = simulation.stage["blast_zones"]["bottom"] + 1.0
	simulation.step(_neutral_commands())
	_check(simulation.state == MatchState.State.FINISHED, "match finished")
	_check(simulation.winner == MatchState.DRAW, "result is a draw")
	return true


func test_pause_resume_and_restart() -> bool:
	var simulation = _match(_flat_stage())
	var original: Array = simulation.fighters.duplicate()
	for _i in 10:
		simulation.step(_neutral_commands())
	simulation.pause()
	for _i in 10:
		simulation.step(_neutral_commands())
	_check(simulation.tick == 10, "paused simulation does not advance")
	simulation.resume()
	simulation.step(_neutral_commands())
	_check(simulation.tick == 11, "resumed simulation advances")
	simulation.fighters[0].stocks = 1
	simulation.fighters[0].damage = 50.0
	simulation.restart()
	_check(simulation.tick == 0, "restart resets the clock")
	_check(simulation.state == MatchState.State.FIGHT, "restart begins a new fight")
	_check(simulation.fighters[0].stocks == simulation.fighters[0].max_stocks, "stocks restored")
	_check(simulation.fighters[0].damage == 0.0, "damage cleared")
	_check(simulation.fighters[0] == original[0], "fighter objects are reused")
	return true


func _scripted_match_digest() -> Array:
	var content := _content()
	var simulation := MatchSimulation.new()
	simulation.setup(content["stage"], content["characters"])
	simulation.start()
	var rng := RandomNumberGenerator.new()
	rng.seed = 20260927
	var digests := []
	for _tick in 900:
		var commands := []
		for _player in 2:
			var buttons := []
			for button in ["left", "right", "jump", "light", "heavy"]:
				if rng.randf() < 0.3:
					buttons.append(button)
			commands.append(_command(buttons))
		simulation.step(commands)
		digests.append(JSON.stringify(simulation.snapshot()).sha256_text())
	return [digests, simulation.snapshot()]


func test_identical_inputs_produce_identical_snapshots() -> bool:
	var first := _scripted_match_digest()
	var second := _scripted_match_digest()
	_check(first[0] == second[0], "per-tick snapshots diverged")
	var final: Dictionary = first[1]
	var activity := 0.0
	for fighter in final["fighters"]:
		activity += absf(fighter["damage"]) + absf(fighter["position"][0])
	_check(activity > 0.0, "scripted inputs exercised the simulation")
	return true


# --- integration -------------------------------------------------------------------


func test_input_router_defaults_to_neutral_commands() -> bool:
	var commands := InputRouter.new().sample_commands(2)
	_check(commands.size() == 2, "one command per player")
	for command in commands:
		_check(command.keys().size() == InputRouter.BUTTONS.size(), "every button present")
		_check(not command.values().has(true), "headless input is neutral")
	return true


func test_main_scene_boots_with_two_fighters() -> bool:
	var main_path := String(ProjectSettings.get_setting("application/run/main_scene"))
	var scene: PackedScene = load(main_path)
	_check(scene != null, "main scene loads: %s" % main_path)
	if scene == null:
		return true
	var main := scene.instantiate()
	root.add_child(main)
	_check(main.load_errors.is_empty(), "content loads without errors: %s" % [main.load_errors])
	_check(main.simulation != null, "simulation created")
	_check(main.fighter_views.size() == 2, "two fighter views spawned")
	_check(main.simulation.state == MatchState.State.FIGHT, "match starts in FIGHT")
	for _i in 120:
		main._physics_process(TICK)
	_check(main.simulation.tick == 120, "fixed-step loop advanced 120 ticks")
	for fighter in main.simulation.fighters:
		_check(fighter.grounded, "%s landed on the stage" % fighter.display_name)
	root.remove_child(main)
	main.free()
	return true

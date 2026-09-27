extends SceneTree

const Game = preload("res://scripts/core/Game.gd")
const MatchState = preload("res://scripts/core/MatchState.gd")
const FighterScript = preload("res://scripts/core/Fighter.gd")

func _init() -> void:
	var failures: Array[String] = []

	_check("attack phase timing", _test_attack_phase_timing(), failures)
	_check("one hit per target", _test_one_hit_per_target(), failures)
	_check("damage and knockback", _test_damage_and_knockback(), failures)
	_check("shield mitigation", _test_shield_mitigation(), failures)
	_check("hitstun recovery", _test_hitstun_recovery(), failures)
	_check("stock loss and respawn", _test_stock_loss_and_respawn(), failures)
	_check("winner completion", _test_match_winner_completion(), failures)
	_check("tie completion safety", _test_match_tie_completion(), failures)
	_check("deterministic repeated simulation", _test_deterministic_replay(), failures)

	if failures.is_empty():
		print("[PASS] Project Aurora deterministic combat tests passed.")
		quit(0)
		return

	for failure in failures:
		push_error(failure)
	quit(1)

func _check(test_name: String, error_message: String, failures: Array[String]) -> void:
	if error_message == "":
		print("[PASS] %s" % test_name)
	else:
		failures.append("[FAIL] %s: %s" % [test_name, error_message])

func _new_game() -> Node2D:
	var game = Game.new()
	game.initialize_match()
	return game

func _actions(overrides: Dictionary = {}) -> Dictionary:
	var base := {
		"left": false,
		"right": false,
		"jump": false,
		"light": false,
		"heavy": false,
		"special": false,
		"shield": false,
	}
	for key in overrides.keys():
		if base.has(key):
			base[key] = bool(overrides[key])
	return base

func _step(game: Node2D, p1: Dictionary = {}, p2: Dictionary = {}, ticks: int = 1) -> void:
	for _i in ticks:
		game.simulate_tick({
			"P1": _actions(p1),
			"P2": _actions(p2),
		}, false, false)

func _test_attack_phase_timing() -> String:
	var game = _new_game()
	var p1: FighterScript = game.get_fighter("P1")

	_step(game, {"light": true}, {}, 1)
	if p1.attack_phase != FighterScript.AttackPhase.STARTUP:
		return "light attack did not enter startup"

	_step(game, {}, {}, p1.attack_data["light"].startup_ticks)
	if p1.attack_phase != FighterScript.AttackPhase.ACTIVE:
		return "light attack did not enter active phase after startup"

	_step(game, {}, {}, p1.attack_data["light"].active_ticks)
	if p1.attack_phase != FighterScript.AttackPhase.RECOVERY:
		return "light attack did not enter recovery phase after active"

	_step(game, {}, {}, p1.attack_data["light"].recovery_ticks)
	if p1.attack_phase != FighterScript.AttackPhase.NONE:
		return "light attack did not fully recover"

	return ""

func _test_one_hit_per_target() -> String:
	var game = _new_game()
	var p1: FighterScript = game.get_fighter("P1")
	var p2: FighterScript = game.get_fighter("P2")
	p1.global_position = Vector2(0.0, 0.0)
	p2.global_position = Vector2(26.0, 0.0)

	_step(game, {"light": true}, {}, 3)
	var first_damage := p2.damage
	if first_damage <= 0.0:
		return "target took no damage on first hit"

	_step(game, {}, {}, 2)
	if not is_equal_approx(p2.damage, first_damage):
		return "target was hit more than once by one attack"
	return ""

func _test_damage_and_knockback() -> String:
	var game = _new_game()
	var p1: FighterScript = game.get_fighter("P1")
	var p2: FighterScript = game.get_fighter("P2")
	p1.global_position = Vector2(0.0, 0.0)
	p2.global_position = Vector2(24.0, 0.0)

	_step(game, {"heavy": true}, {}, 6)
	if p2.damage < 12.0:
		return "heavy attack damage not applied"
	if p2.velocity.x <= 0.0:
		return "heavy attack knockback not applied"
	if p2.hitstun_ticks <= 0:
		return "heavy attack did not inflict hitstun"
	return ""

func _test_shield_mitigation() -> String:
	var game = _new_game()
	var p1: FighterScript = game.get_fighter("P1")
	var p2: FighterScript = game.get_fighter("P2")
	p1.global_position = Vector2(0.0, 0.0)
	p2.global_position = Vector2(24.0, 0.0)

	_step(game, {}, {"shield": true}, 3)
	_step(game, {"light": true}, {"shield": true}, 4)
	if p2.damage != 0.0:
		return "shield did not mitigate eligible damage"
	if p2.hitstun_ticks <= 0:
		return "shielded hit should still create shield stun"
	return ""

func _test_hitstun_recovery() -> String:
	var game = _new_game()
	var p2: FighterScript = game.get_fighter("P2")
	p2.receive_hit({"damage": 3.0, "knockback": Vector2(100.0, -40.0), "hitstun_ticks": 8})
	if p2.hitstun_ticks <= 0:
		return "initial hitstun missing"
	_step(game, {}, {}, 10)
	if p2.hitstun_ticks != 0:
		return "hitstun did not recover"
	return ""

func _test_stock_loss_and_respawn() -> String:
	var game = _new_game()
	var p1: FighterScript = game.get_fighter("P1")
	p1.stocks = 2
	p1.damage = 45.0
	p1.global_position = Vector2(1000.0, 0.0)
	_step(game)
	if p1.stocks != 1:
		return "stock was not deducted"
	if p1.global_position != p1.spawn_position:
		return "fighter did not respawn at spawn position"
	if p1.damage != 0.0:
		return "respawn did not reset damage"

	p1.global_position = Vector2(1000.0, 0.0)
	_step(game)
	if p1.stocks != 0:
		return "final stock was not deducted"
	if not p1.is_eliminated:
		return "fighter should be eliminated at zero stocks"

	_step(game)
	if p1.stocks < 0:
		return "stocks dropped below zero"
	return ""

func _test_match_winner_completion() -> String:
	var game = _new_game()
	var p2: FighterScript = game.get_fighter("P2")
	p2.stocks = 0
	p2.is_eliminated = true
	_step(game)
	if game.match_state != MatchState.State.FINISHED:
		return "match did not finish with one remaining fighter"
	if game.winner_name == "":
		return "winner name missing"
	return ""

func _test_match_tie_completion() -> String:
	var game = _new_game()
	var p1: FighterScript = game.get_fighter("P1")
	var p2: FighterScript = game.get_fighter("P2")
	p1.stocks = 1
	p2.stocks = 1
	p1.global_position = Vector2(1000.0, 0.0)
	p2.global_position = Vector2(-1000.0, 0.0)
	_step(game)
	if game.match_state != MatchState.State.FINISHED:
		return "match did not finish after simultaneous elimination"
	if game.winner_name != "":
		return "tie should not assign winner"
	return ""

func _test_deterministic_replay() -> String:
	var snapshot_a := _run_replay_and_capture()
	var snapshot_b := _run_replay_and_capture()
	if snapshot_a != snapshot_b:
		return "repeated simulation with same inputs produced different outcomes"
	return ""

func _run_replay_and_capture() -> String:
	var game = _new_game()
	for tick in 120:
		var p1 := {}
		var p2 := {}
		if tick == 2:
			p1 = {"right": true}
		if tick == 3:
			p1 = {"light": true}
		if tick >= 6 and tick <= 12:
			p2 = {"shield": true}
		if tick == 30:
			p2 = {"heavy": true}
		if tick > 40 and tick < 55:
			p1 = {"left": true}
		_step(game, p1, p2, 1)

	var p1f: FighterScript = game.get_fighter("P1")
	var p2f: FighterScript = game.get_fighter("P2")
	return JSON.stringify({
		"p1": {
			"pos": [snapped(p1f.global_position.x, 0.001), snapped(p1f.global_position.y, 0.001)],
			"vel": [snapped(p1f.velocity.x, 0.001), snapped(p1f.velocity.y, 0.001)],
			"stocks": p1f.stocks,
			"damage": snapped(p1f.damage, 0.001),
		},
		"p2": {
			"pos": [snapped(p2f.global_position.x, 0.001), snapped(p2f.global_position.y, 0.001)],
			"vel": [snapped(p2f.velocity.x, 0.001), snapped(p2f.velocity.y, 0.001)],
			"stocks": p2f.stocks,
			"damage": snapped(p2f.damage, 0.001),
		},
		"winner": game.winner_name,
		"state": game.match_state,
	})

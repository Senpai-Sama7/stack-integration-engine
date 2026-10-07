extends RefCounted
## Authoritative fixed-step match simulation. Presentation reads `fighters` and
## `snapshot()`; it never mutates simulation state.
##
## Per-tick order (docs/design/TECHNICAL_ARCHITECTURE.md): commands, timers, movement and
## platform landing, attack phases, hit resolution in stable ID order, blast zones and
## stocks, then match completion.

const FighterState = preload("res://scripts/core/FighterState.gd")
const MatchState = preload("res://scripts/core/MatchState.gd")

const TICKS_PER_SECOND := 60
const TICK := 1.0 / TICKS_PER_SECOND

var state: int = MatchState.State.READY
var tick := 0
var winner := MatchState.NO_WINNER
var fighters: Array = []
var stage: Dictionary = {}
var _characters: Array = []
## Contacts applied during the most recent tick, as [attacker_id, target_id] pairs.
var last_contacts: Array = []


func setup(stage_data: Dictionary, characters: Array) -> void:
	stage = stage_data
	_characters = characters
	fighters.clear()
	for index in characters.size():
		var fighter := FighterState.new()
		fighter.configure(index, characters[index])
		fighters.append(fighter)
	_reset()


func start() -> void:
	if state == MatchState.State.READY:
		state = MatchState.State.FIGHT


func pause() -> void:
	if state == MatchState.State.FIGHT:
		state = MatchState.State.PAUSED


func resume() -> void:
	if state == MatchState.State.PAUSED:
		state = MatchState.State.FIGHT


func toggle_pause() -> void:
	if state == MatchState.State.PAUSED:
		resume()
	else:
		pause()


## Reset every fighter and start a fresh match, keeping the same fighter objects so
## presentation nodes stay bound.
func restart() -> void:
	for index in fighters.size():
		fighters[index].configure(index, _characters[index])
	_reset()
	start()


func step(commands: Array) -> void:
	if state != MatchState.State.FIGHT:
		return
	tick += 1
	var platforms: Array = stage["platforms"]
	for fighter in fighters:
		var command: Dictionary = commands[fighter.id] if fighter.id < commands.size() else {}
		fighter.step(command, platforms, TICK)
	_resolve_hits()
	_resolve_blast_zones()
	_resolve_match_end()


func snapshot() -> Dictionary:
	var fighter_snapshots := []
	for fighter in fighters:
		fighter_snapshots.append(fighter.snapshot())
	return {"tick": tick, "state": state, "winner": winner, "fighters": fighter_snapshots}


func spawn_point(index: int) -> Vector2:
	var point: Dictionary = stage["spawn_points"][index % stage["spawn_points"].size()]
	return Vector2(point["x"], point["y"])


func is_outside_blast_zone(fighter) -> bool:
	var zones: Dictionary = stage["blast_zones"]
	return (
		fighter.position.x < zones["left"]
		or fighter.position.x > zones["right"]
		or fighter.position.y < zones["top"]
		or fighter.position.y > zones["bottom"]
	)


func _reset() -> void:
	tick = 0
	winner = MatchState.NO_WINNER
	state = MatchState.State.READY
	last_contacts = []
	for fighter in fighters:
		fighter.spawn(spawn_point(fighter.id))


func _resolve_hits() -> void:
	# Collect every contact first so trades apply symmetrically, then apply them in
	# stable attacker/target ID order (never scene-tree order).
	last_contacts = []
	for attacker in fighters:
		if attacker.eliminated:
			continue
		var hitbox: Rect2 = attacker.active_hitbox()
		if not hitbox.has_area():
			continue
		for target in fighters:
			if target == attacker or target.eliminated or target.invulnerable:
				continue
			if target.id in attacker.attack_hit_targets:
				continue
			if hitbox.intersects(target.hurtbox()):
				last_contacts.append([attacker.id, target.id, attacker.current_attack(), attacker.facing])
	for contact in last_contacts:
		var attacker = fighters[contact[0]]
		var target = fighters[contact[1]]
		attacker.attack_hit_targets.append(target.id)
		target.receive_hit(contact[2], contact[3], attacker.damage_scale)
	for index in last_contacts.size():
		last_contacts[index] = [last_contacts[index][0], last_contacts[index][1]]


func _resolve_blast_zones() -> void:
	var respawn_ticks := int(stage.get("respawn_invulnerability_ticks", 90))
	for fighter in fighters:
		if fighter.eliminated or not is_outside_blast_zone(fighter):
			continue
		fighter.stocks -= 1
		if fighter.stocks > 0:
			fighter.spawn(spawn_point(fighter.id), respawn_ticks)
		else:
			fighter.eliminated = true
			fighter.velocity = Vector2.ZERO


func _resolve_match_end() -> void:
	var remaining := []
	for fighter in fighters:
		if not fighter.eliminated:
			remaining.append(fighter)
	if remaining.size() > 1:
		return
	state = MatchState.State.FINISHED
	winner = remaining[0].id if remaining.size() == 1 else MatchState.DRAW

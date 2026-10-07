extends RefCounted
## Deterministic simulation state for one fighter.
##
## Coordinates are pixels with +y pointing down (Godot's 2D convention). `position` is
## the bottom-centre of the body, so it sits exactly on a platform's top surface when
## grounded. No scene-tree or physics-server state is involved: identical command
## streams always produce identical states.
##
## Timer rule: a countdown timer set to N during tick t applies to ticks t+1 .. t+N.

const AttackData = preload("res://scripts/combat/AttackData.gd")
const KnockbackModel = preload("res://scripts/combat/KnockbackModel.gd")

# Baseline values from docs/design/MOVEMENT_SPEC.md; per-character values come from data.
const GRAVITY := 1450.0
const MAX_FALL_SPEED := 760.0
const GROUND_ACCELERATION := 2200.0
const GROUND_DECELERATION := 2600.0
const AIR_ACCELERATION := 950.0
const MAX_AIR_SPEED := 245.0
const JUMP_RELEASE_DAMPING := 0.5
const INPUT_BUFFER_TICKS := 6
const COYOTE_TICKS := 4
const LANDING_LOCK_TICKS := 2
const BODY_SIZE := Vector2(32.0, 52.0)
const ATTACK_BUTTONS := ["light", "heavy"]

var id := 0
var character_id := ""
var display_name := ""
var color := Color.WHITE
var weight := 1.0
var run_speed := 280.0
var jump_impulse := 540.0
var air_control := 1.0
var air_jumps := 1
var max_stocks := 3
var damage_scale := 1.0
var attacks: Dictionary = {}

var position := Vector2.ZERO
var velocity := Vector2.ZERO
var facing := 1
var grounded := false
var air_jumps_remaining := 0
var coyote_ticks := 0
var jump_buffer_ticks := 0
var jump_damped := true
var landing_lock_ticks := 0
var hitstun_ticks := 0
var invulnerable_ticks := 0
## Whether hits are ignored during the current tick (derived from invulnerable_ticks).
var invulnerable := false
var damage := 0.0
var stocks := 3
var eliminated := false
var attack_name := ""
var attack_tick := 0
var attack_hit_targets: Array[int] = []

var _held: Dictionary = {}


func configure(fighter_id: int, character: Dictionary) -> void:
	var stats: Dictionary = character["stats"]
	id = fighter_id
	character_id = String(character.get("id", character["name"]))
	display_name = String(character.get("display_name", character["name"]))
	color = Color.from_string(String(character.get("color", "#ffffff")), Color.WHITE)
	weight = float(stats["weight"])
	run_speed = float(stats["run_speed"])
	jump_impulse = float(stats["jump_force"])
	air_control = float(stats["air_control"])
	air_jumps = int(stats.get("air_jumps", 1))
	max_stocks = int(stats["stocks"])
	damage_scale = float(stats["damage_scale"])
	attacks = {}
	var raw_attacks: Dictionary = character.get("attacks", {})
	for attack_name_key in raw_attacks:
		attacks[attack_name_key] = AttackData.normalize(raw_attacks[attack_name_key])
	stocks = max_stocks
	eliminated = false


## Place the fighter at a spawn point with a clean slate and optional invulnerability.
func spawn(at: Vector2, invulnerability_ticks: int = 0) -> void:
	position = at
	velocity = Vector2.ZERO
	grounded = false
	air_jumps_remaining = air_jumps
	coyote_ticks = 0
	jump_buffer_ticks = 0
	jump_damped = true
	landing_lock_ticks = 0
	hitstun_ticks = 0
	invulnerable_ticks = invulnerability_ticks
	invulnerable = invulnerability_ticks > 0
	damage = 0.0
	attack_name = ""
	attack_tick = 0
	attack_hit_targets.clear()
	_held.clear()


## Advance one fixed tick: timers, jumping, movement, platform landing, attack phases.
func step(command: Dictionary, platforms: Array, delta: float) -> void:
	if eliminated:
		return
	var pressed := _pressed_edges(command)

	# Timers and state transitions (check-then-decrement; see the timer rule above).
	var in_hitstun := hitstun_ticks > 0
	var landing_locked := landing_lock_ticks > 0
	invulnerable = invulnerable_ticks > 0
	hitstun_ticks = maxi(hitstun_ticks - 1, 0)
	landing_lock_ticks = maxi(landing_lock_ticks - 1, 0)
	invulnerable_ticks = maxi(invulnerable_ticks - 1, 0)
	if attack_name != "":
		attack_tick += 1
		if attack_tick >= AttackData.total_ticks(attacks[attack_name]):
			attack_name = ""
			attack_tick = 0
	var movement_locked := in_hitstun or landing_locked or attack_name != ""

	# Jumping: buffered presses, coyote time, and air jumps.
	if pressed.has("jump"):
		jump_buffer_ticks = INPUT_BUFFER_TICKS
	if jump_buffer_ticks > 0 and not movement_locked:
		if grounded or coyote_ticks > 0:
			_jump()
		elif pressed.has("jump") and air_jumps_remaining > 0:
			air_jumps_remaining -= 1
			_jump()
	coyote_ticks = maxi(coyote_ticks - 1, 0)
	if (
		velocity.y < 0.0
		and not jump_damped
		and not bool(command.get("jump", false))
		and not in_hitstun
	):
		velocity.y *= JUMP_RELEASE_DAMPING
		jump_damped = true

	# Horizontal control.
	var direction := 0
	if not movement_locked:
		direction = int(bool(command.get("right", false))) - int(bool(command.get("left", false)))
		if direction != 0:
			facing = direction
	if grounded:
		var target := direction * run_speed
		var rate := GROUND_ACCELERATION if direction != 0 else GROUND_DECELERATION
		velocity.x = move_toward(velocity.x, target, rate * delta)
	elif direction != 0:
		var cap := minf(MAX_AIR_SPEED, run_speed)
		velocity.x = move_toward(velocity.x, direction * cap, AIR_ACCELERATION * air_control * delta)

	# Gravity, integration, and one-way platform landing.
	if not grounded:
		velocity.y = minf(velocity.y + GRAVITY * delta, MAX_FALL_SPEED)
	var previous_y := position.y
	position += velocity * delta
	var surface := _landing_surface(previous_y, platforms) if velocity.y >= 0.0 else INF
	if surface != INF:
		position.y = surface
		velocity.y = 0.0
		if not grounded:
			_land()
	else:
		if grounded:
			grounded = false
			coyote_ticks = COYOTE_TICKS
		if jump_buffer_ticks > 0:
			jump_buffer_ticks -= 1

	# Attack start (only when free to act).
	if attack_name == "" and not in_hitstun and not landing_locked:
		for button in ATTACK_BUTTONS:
			if pressed.has(button) and attacks.has(button):
				attack_name = button
				attack_tick = 0
				attack_hit_targets.clear()
				break


func receive_hit(attack: Dictionary, attacker_facing: int, attacker_damage_scale: float) -> void:
	damage += attack["damage"] * attacker_damage_scale
	var speed := KnockbackModel.launch_speed(attack, damage, weight)
	velocity = KnockbackModel.launch_velocity(attack, damage, weight, attacker_facing)
	hitstun_ticks = KnockbackModel.hitstun_ticks(attack, speed)
	grounded = false
	jump_damped = true
	attack_name = ""
	attack_tick = 0


func current_attack() -> Dictionary:
	return attacks.get(attack_name, {})


func attack_phase() -> String:
	if attack_name == "":
		return "idle"
	return AttackData.phase(attacks[attack_name], attack_tick)


## World-space hitbox while the current attack is active; an empty rect otherwise.
func active_hitbox() -> Rect2:
	if attack_phase() != "active":
		return Rect2()
	var local: Rect2 = attacks[attack_name]["hitbox"]
	var left := position.x + (local.position.x if facing > 0 else -local.position.x - local.size.x)
	return Rect2(left, position.y + local.position.y, local.size.x, local.size.y)


func hurtbox() -> Rect2:
	return Rect2(position.x - BODY_SIZE.x / 2.0, position.y - BODY_SIZE.y, BODY_SIZE.x, BODY_SIZE.y)


func snapshot() -> Dictionary:
	return {
		"id": id,
		"position": [position.x, position.y],
		"velocity": [velocity.x, velocity.y],
		"facing": facing,
		"grounded": grounded,
		"damage": damage,
		"stocks": stocks,
		"eliminated": eliminated,
		"attack": attack_name,
		"attack_tick": attack_tick,
		"hitstun_ticks": hitstun_ticks,
		"invulnerable_ticks": invulnerable_ticks,
	}


func _jump() -> void:
	velocity.y = -jump_impulse
	grounded = false
	coyote_ticks = 0
	jump_buffer_ticks = 0
	jump_damped = false


func _land() -> void:
	grounded = true
	air_jumps_remaining = air_jumps
	landing_lock_ticks = LANDING_LOCK_TICKS
	jump_damped = true


func _landing_surface(previous_y: float, platforms: Array) -> float:
	var best := INF
	for platform in platforms:
		var top: float = platform["y"]
		var half_width: float = platform["width"] / 2.0
		if (
			position.x >= platform["x"] - half_width
			and position.x <= platform["x"] + half_width
			and previous_y <= top
			and position.y >= top
		):
			best = minf(best, top)
	return best


func _pressed_edges(command: Dictionary) -> Dictionary:
	var pressed := {}
	for button in ["jump", "light", "heavy", "special", "shield"]:
		var down := bool(command.get(button, false))
		if down and not bool(_held.get(button, false)):
			pressed[button] = true
		_held[button] = down
	return pressed

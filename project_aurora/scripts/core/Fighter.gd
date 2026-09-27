extends CharacterBody2D
class_name Fighter

const AttackData = preload("res://scripts/combat/AttackData.gd")

const GRAVITY := 1550.0
const MOVE_SPEED := 220.0
const AIR_ACCELERATION := 1500.0
const GROUND_ACCELERATION := 2400.0
const JUMP_FORCE := 540.0
const HURTBOX_SIZE := Vector2(32.0, 52.0)
const SHIELD_STARTUP_TICKS := 2
const SHIELD_RECOVERY_TICKS := 4
const SHIELD_DAMAGE_SCALE := 0.0
const SHIELD_KNOCKBACK_SCALE := 0.22
const SHIELD_HITSTUN_TICKS := 4

enum AttackPhase {
	NONE,
	STARTUP,
	ACTIVE,
	RECOVERY,
}

enum ShieldState {
	INACTIVE,
	STARTUP,
	ACTIVE,
	RECOVERY,
}

@export var fighter_id: String = ""
@export var fighter_name: String = "Fighter"
@export var color: Color = Color.WHITE
@export var stocks: int = 3
@export var damage: float = 0.0
@export var invulnerable_ticks: int = 0
@export var hitstun_ticks: int = 0

var max_stocks: int = 3
var spawn_position: Vector2 = Vector2.ZERO
var facing: int = 1
var is_grounded: bool = false
var is_eliminated: bool = false

var attack_data: Dictionary = AttackData.default_attack_map()
var attack_name: StringName = &""
var attack_phase: int = AttackPhase.NONE
var attack_ticks_remaining: int = 0
var attack_hit_targets: Dictionary = {}

var shield_state: int = ShieldState.INACTIVE
var shield_ticks_remaining: int = 0

var _previous_actions: Dictionary = {
	"left": false,
	"right": false,
	"jump": false,
	"light": false,
	"heavy": false,
	"special": false,
	"shield": false,
}

func initialize(id_value: String, name_value: String, start_position: Vector2, tint: Color, initial_stocks: int = 3) -> void:
	fighter_id = id_value
	fighter_name = name_value
	color = tint
	spawn_position = start_position
	max_stocks = max(0, initial_stocks)
	stocks = max_stocks
	respawn(true)
	if has_node("Body"):
		$Body.color = color

func simulate(actions: Dictionary, delta: float, use_physics: bool = true) -> void:
	if is_eliminated:
		_previous_actions = actions.duplicate(true)
		return

	_tick_status_effects()
	_update_shield_state(actions)
	_update_attack_state(actions)
	_update_movement(actions, delta, use_physics)

	_previous_actions = actions.duplicate(true)

func _tick_status_effects() -> void:
	if hitstun_ticks > 0:
		hitstun_ticks -= 1
	if invulnerable_ticks > 0:
		invulnerable_ticks -= 1

func _update_movement(actions: Dictionary, delta: float, use_physics: bool) -> void:
	var move_input := 0.0
	if hitstun_ticks == 0 and shield_state != ShieldState.ACTIVE and shield_state != ShieldState.STARTUP:
		if actions.get("left", false):
			move_input -= 1.0
		if actions.get("right", false):
			move_input += 1.0

	if move_input != 0.0:
		facing = 1 if move_input > 0.0 else -1

	var accel := AIR_ACCELERATION
	if is_on_floor() or is_grounded:
		accel = GROUND_ACCELERATION

	velocity.x = move_toward(velocity.x, move_input * MOVE_SPEED, accel * delta)

	if hitstun_ticks == 0 and _is_just_pressed(actions, "jump") and (is_on_floor() or is_grounded):
		velocity.y = -JUMP_FORCE
		is_grounded = false

	velocity.y += GRAVITY * delta

	if use_physics and is_inside_tree():
		move_and_slide()
	else:
		global_position += velocity * delta
		if global_position.y >= spawn_position.y:
			global_position.y = spawn_position.y
			velocity.y = 0.0
			is_grounded = true

	if is_on_floor():
		is_grounded = true
		if velocity.y > 0.0:
			velocity.y = 0.0
	elif use_physics:
		is_grounded = false

func _update_attack_state(actions: Dictionary) -> void:
	if hitstun_ticks == 0 and shield_state == ShieldState.INACTIVE and attack_phase == AttackPhase.NONE:
		if _is_just_pressed(actions, "light"):
			_start_attack("light")
			return
		if _is_just_pressed(actions, "heavy"):
			_start_attack("heavy")
			return
		if _is_just_pressed(actions, "special"):
			_start_attack("special")
			return

	if attack_phase == AttackPhase.NONE:
		return

	attack_ticks_remaining -= 1
	if attack_ticks_remaining > 0:
		return

	match attack_phase:
		AttackPhase.STARTUP:
			attack_phase = AttackPhase.ACTIVE
			attack_ticks_remaining = _current_attack().active_ticks
		AttackPhase.ACTIVE:
			attack_phase = AttackPhase.RECOVERY
			attack_ticks_remaining = _current_attack().recovery_ticks
		AttackPhase.RECOVERY:
			_clear_attack_state()

func _update_shield_state(actions: Dictionary) -> void:
	var wants_shield := actions.get("shield", false)

	match shield_state:
		ShieldState.INACTIVE:
			if wants_shield and hitstun_ticks == 0 and attack_phase == AttackPhase.NONE:
				shield_state = ShieldState.STARTUP
				shield_ticks_remaining = SHIELD_STARTUP_TICKS
		ShieldState.STARTUP:
			if not wants_shield:
				shield_state = ShieldState.RECOVERY
				shield_ticks_remaining = SHIELD_RECOVERY_TICKS
			else:
				shield_ticks_remaining -= 1
				if shield_ticks_remaining <= 0:
					shield_state = ShieldState.ACTIVE
		ShieldState.ACTIVE:
			if not wants_shield:
				shield_state = ShieldState.RECOVERY
				shield_ticks_remaining = SHIELD_RECOVERY_TICKS
		ShieldState.RECOVERY:
			shield_ticks_remaining -= 1
			if shield_ticks_remaining <= 0:
				shield_state = ShieldState.INACTIVE

func _start_attack(next_attack: StringName) -> void:
	if not attack_data.has(next_attack):
		return
	attack_name = next_attack
	attack_phase = AttackPhase.STARTUP
	attack_ticks_remaining = _current_attack().startup_ticks
	attack_hit_targets.clear()

func _clear_attack_state() -> void:
	attack_name = &""
	attack_phase = AttackPhase.NONE
	attack_ticks_remaining = 0
	attack_hit_targets.clear()

func _current_attack() -> AttackData:
	return attack_data[attack_name]

func is_attack_active() -> bool:
	return attack_phase == AttackPhase.ACTIVE and not is_eliminated

func get_hurtbox_rect() -> Rect2:
	var origin := global_position - (HURTBOX_SIZE * 0.5)
	return Rect2(origin, HURTBOX_SIZE)

func get_active_hitbox_rect() -> Rect2:
	if not is_attack_active():
		return Rect2()
	var attack := _current_attack()
	var world_center := global_position + Vector2(attack.hitbox_offset.x * facing, attack.hitbox_offset.y)
	return Rect2(world_center - (attack.hitbox_size * 0.5), attack.hitbox_size)

func can_hit_target(target_id: String) -> bool:
	if not is_attack_active() or target_id == "":
		return false
	var attack := _current_attack()
	if attack.one_hit_per_target and attack_hit_targets.has(target_id):
		return false
	return true

func register_hit_target(target_id: String) -> void:
	if target_id != "":
		attack_hit_targets[target_id] = true

func build_hit_payload() -> Dictionary:
	if not is_attack_active():
		return {}
	var attack := _current_attack()
	return {
		"attack_id": String(attack.attack_id),
		"damage": attack.damage,
		"knockback": Vector2(attack.knockback.x * facing, attack.knockback.y),
		"hitstun_ticks": attack.hitstun_ticks,
	}

func receive_hit(hit_payload: Dictionary) -> bool:
	if is_eliminated or invulnerable_ticks > 0:
		return false

	var incoming_damage := float(hit_payload.get("damage", 0.0))
	var incoming_knockback: Vector2 = hit_payload.get("knockback", Vector2.ZERO)
	var incoming_hitstun := int(hit_payload.get("hitstun_ticks", 0))

	if shield_state == ShieldState.ACTIVE:
		damage += incoming_damage * SHIELD_DAMAGE_SCALE
		velocity += incoming_knockback * SHIELD_KNOCKBACK_SCALE
		hitstun_ticks = max(hitstun_ticks, SHIELD_HITSTUN_TICKS)
		invulnerable_ticks = 1
		return true

	damage += incoming_damage
	var damage_scale := 1.0 + (damage * 0.01)
	velocity += incoming_knockback * damage_scale
	hitstun_ticks = max(hitstun_ticks, incoming_hitstun)
	invulnerable_ticks = 4
	return true

func lose_stock() -> void:
	if stocks <= 0:
		return
	stocks = max(stocks - 1, 0)
	if stocks == 0:
		is_eliminated = true
		velocity = Vector2.ZERO
		hitstun_ticks = 0
		invulnerable_ticks = 0
		_clear_attack_state()
		shield_state = ShieldState.INACTIVE
		shield_ticks_remaining = 0
		return
	respawn(false)

func respawn(is_initial_spawn: bool = false) -> void:
	global_position = spawn_position
	velocity = Vector2.ZERO
	damage = 0.0
	hitstun_ticks = 0
	_clear_attack_state()
	shield_state = ShieldState.INACTIVE
	shield_ticks_remaining = 0
	is_eliminated = false
	is_grounded = true
	invulnerable_ticks = 0 if is_initial_spawn else 60

func _is_just_pressed(actions: Dictionary, action_name: String) -> bool:
	var now := bool(actions.get(action_name, false))
	var before := bool(_previous_actions.get(action_name, false))
	return now and not before

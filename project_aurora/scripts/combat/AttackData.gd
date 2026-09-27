extends RefCounted
class_name AttackData

var attack_id: StringName
var startup_ticks: int
var active_ticks: int
var recovery_ticks: int
var damage: float
var knockback: Vector2
var hitstun_ticks: int
var hitbox_size: Vector2
var hitbox_offset: Vector2
var one_hit_per_target: bool

func _init(
	id_value: StringName,
	startup_value: int,
	active_value: int,
	recovery_value: int,
	damage_value: float,
	knockback_value: Vector2,
	hitstun_value: int,
	hitbox_size_value: Vector2,
	hitbox_offset_value: Vector2,
	one_hit_per_target_value: bool = true
) -> void:
	attack_id = id_value
	startup_ticks = startup_value
	active_ticks = active_value
	recovery_ticks = recovery_value
	damage = damage_value
	knockback = knockback_value
	hitstun_ticks = hitstun_value
	hitbox_size = hitbox_size_value
	hitbox_offset = hitbox_offset_value
	one_hit_per_target = one_hit_per_target_value

static func default_attack_map() -> Dictionary:
	return {
		"light": AttackData.new("light", 2, 2, 4, 6.0, Vector2(260.0, -130.0), 12, Vector2(42.0, 26.0), Vector2(28.0, -4.0), true),
		"heavy": AttackData.new("heavy", 4, 3, 7, 12.0, Vector2(380.0, -180.0), 18, Vector2(54.0, 34.0), Vector2(34.0, -6.0), true),
		"special": AttackData.new("special", 6, 4, 10, 16.0, Vector2(470.0, -210.0), 24, Vector2(66.0, 36.0), Vector2(40.0, -8.0), true),
	}

extends RefCounted
## The single place that turns an attack payload into launch velocity and hitstun.
## See docs/design/DECISIONS.md (DEC-008) for the provisional formula.

const MAX_HITSTUN_TICKS := 120


static func launch_speed(attack: Dictionary, target_damage: float, target_weight: float) -> float:
	return (attack["base_knockback"] + attack["knockback_growth"] * target_damage) / maxf(
		target_weight, 0.1
	)


static func launch_velocity(
	attack: Dictionary, target_damage: float, target_weight: float, attacker_facing: int
) -> Vector2:
	var speed := launch_speed(attack, target_damage, target_weight)
	var angle := deg_to_rad(attack["angle_degrees"])
	return Vector2(cos(angle) * attacker_facing, -sin(angle)) * speed


static func hitstun_ticks(attack: Dictionary, speed: float) -> int:
	return clampi(int(round(speed / 60.0 * attack["hitstun_multiplier"])), 1, MAX_HITSTUN_TICKS)

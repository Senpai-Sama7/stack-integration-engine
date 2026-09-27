extends RefCounted
class_name Fighter

const ATTACK_NAMES := ["light", "heavy", "special"]

var name: String
var color: Color
var position: Vector2 = Vector2.ZERO
var velocity: Vector2 = Vector2.ZERO
var facing := 1.0
var stocks := 3
var damage := 0.0
var is_grounded := true
var is_hitstunned := false
var invulnerable_ticks := 0
var attack_queue: Array = []

func _init(fighter_name: String, spawn_position: Vector2, fighter_color: Color) -> void:
    name = fighter_name
    position = spawn_position
    color = fighter_color

func reset_to_spawn() -> void:
    position = Vector2(position.x, 0.0)
    velocity = Vector2.ZERO
    damage = 0.0
    is_grounded = true
    is_hitstunned = false
    invulnerable_ticks = 0
    attack_queue.clear()

func update(actions: Dictionary, _delta: float) -> void:
    if is_hitstunned:
        return

    if actions.get("move_left", false):
        velocity.x = -220.0
        facing = -1.0
    elif actions.get("move_right", false):
        velocity.x = 220.0
        facing = 1.0
    else:
        velocity.x = move_toward(velocity.x, 0.0, 240.0)

    if actions.get("jump", false) and is_grounded:
        velocity.y = -540.0
        is_grounded = false

    if actions.get("light_attack", false):
        attack_queue.append("light")

    if actions.get("heavy_attack", false):
        attack_queue.append("heavy")

    if actions.get("special", false):
        attack_queue.append("special")

    if not is_grounded:
        velocity.y += 1550.0 * _delta

    position += velocity * _delta
    if position.y >= 180.0:
        position.y = 180.0
        velocity.y = 0.0
        is_grounded = true

func take_damage(amount: float, knockback: Vector2) -> void:
    if invulnerable_ticks > 0:
        return
    damage += amount
    velocity += knockback
    is_hitstunned = true
    invulnerable_ticks = 12

func resolve_stock_loss() -> void:
    if position.y > 500.0:
        stocks -= 1
        damage = 0.0
        position = Vector2(position.x * -0.5, 0.0)
        velocity = Vector2.ZERO
        is_hitstunned = false
        invulnerable_ticks = 30

func _process_tick() -> void:
    if invulnerable_ticks > 0:
        invulnerable_ticks -= 1
    if is_hitstunned and invulnerable_ticks <= 0:
        is_hitstunned = false

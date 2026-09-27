extends CharacterBody2D
class_name Fighter

const GRAVITY := 1550.0
const MOVE_SPEED := 220.0
const JUMP_FORCE := 540.0
const FLOOR_Y := 180.0

@export var fighter_name: String = "Fighter"
@export var color: Color = Color.WHITE
@export var stocks: int = 3
@export var damage: float = 0.0
@export var invulnerable_ticks: int = 0
@export var hitstun_ticks: int = 0

var facing: int = 1
var is_grounded: bool = true

func initialize(name_value: String, spawn_position: Vector2, tint: Color) -> void:
    fighter_name = name_value
    color = tint
    global_position = spawn_position
    _draw_body()

func _draw_body() -> void:
    if has_node("Body"):
        $Body.color = color

func update(actions: Dictionary, delta: float) -> void:
    if hitstun_ticks > 0:
        hitstun_ticks -= 1
    if invulnerable_ticks > 0:
        invulnerable_ticks -= 1

    var move_input := 0.0
    if actions.get("left", false):
        move_input -= 1.0
    if actions.get("right", false):
        move_input += 1.0
    if move_input != 0.0:
        facing = 1 if move_input > 0.0 else -1

    var target_velocity_x := move_input * MOVE_SPEED
    velocity.x = move_toward(velocity.x, target_velocity_x, 2400.0 * delta)

    if is_grounded and actions.get("jump", false):
        velocity.y = -JUMP_FORCE
        is_grounded = false

    if not is_grounded:
        velocity.y += GRAVITY * delta

    move_and_slide()

    if is_on_floor():
        velocity.y = 0.0
        is_grounded = true

    if global_position.y >= FLOOR_Y:
        global_position.y = FLOOR_Y
        velocity.y = 0.0
        is_grounded = true

    if global_position.y > 430.0:
        resolve_stock_loss()

func resolve_stock_loss() -> void:
    if stocks <= 0:
        return
    stocks -= 1
    damage = 0.0
    velocity = Vector2.ZERO
    is_grounded = true
    invulnerable_ticks = 30
    hitstun_ticks = 0
    global_position = Vector2(-180.0 if fighter_name == "Captain America" else 180.0, 0.0)

func take_damage(amount: float, knockback: Vector2) -> void:
    if invulnerable_ticks > 0:
        return
    damage += amount
    velocity += knockback
    hitstun_ticks = 8
    invulnerable_ticks = 12

func _draw() -> void:
    draw_rect(Rect2(-16, -26, 32, 52), color)

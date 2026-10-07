extends Node2D
## Presentation for one fighter. Reads simulation state; never writes it.

var fighter = null
var show_hitboxes := false

@onready var body: Polygon2D = $Body
@onready var label: Label = $Name


func bind(state) -> void:
	fighter = state
	body.color = state.color
	label.text = state.display_name
	sync()


func sync() -> void:
	if fighter == null:
		return
	visible = not fighter.eliminated
	position = fighter.position
	body.scale.x = fighter.facing
	# Flash while invulnerable so respawn protection is visible.
	body.modulate.a = 0.45 if fighter.invulnerable_ticks > 0 and (fighter.invulnerable_ticks / 6) % 2 == 0 else 1.0
	queue_redraw()


func _draw() -> void:
	if fighter == null or not show_hitboxes:
		return
	var hurtbox: Rect2 = fighter.hurtbox()
	draw_rect(Rect2(hurtbox.position - fighter.position, hurtbox.size), Color(0.3, 1.0, 0.4, 0.8), false, 1.0)
	var hitbox: Rect2 = fighter.active_hitbox()
	if hitbox.has_area():
		draw_rect(Rect2(hitbox.position - fighter.position, hitbox.size), Color(1.0, 0.2, 0.2, 0.55))

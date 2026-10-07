extends Node2D
## Draws stage geometry from validated stage data. Collision lives in the simulation.

const GROUND_COLOR := Color(0.22, 0.23, 0.28)
const PLATFORM_COLOR := Color(0.30, 0.34, 0.42)

var stage: Dictionary = {}
var show_debug := false


func configure(stage_data: Dictionary) -> void:
	stage = stage_data
	queue_redraw()


func set_debug(enabled: bool) -> void:
	show_debug = enabled
	queue_redraw()


func _draw() -> void:
	for platform in stage.get("platforms", []):
		var rect := Rect2(
			platform["x"] - platform["width"] / 2.0, platform["y"], platform["width"], platform["height"]
		)
		draw_rect(rect, GROUND_COLOR if platform["type"] == "ground" else PLATFORM_COLOR)
	if show_debug and stage.has("blast_zones"):
		var zones: Dictionary = stage["blast_zones"]
		draw_rect(
			Rect2(zones["left"], zones["top"], zones["right"] - zones["left"], zones["bottom"] - zones["top"]),
			Color(1.0, 0.5, 0.2, 0.9),
			false,
			2.0
		)

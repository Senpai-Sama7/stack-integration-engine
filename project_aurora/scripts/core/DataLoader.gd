extends RefCounted
## Loads JSON content data and validates it before any simulation uses it.
## Every function returns errors instead of raising, so callers can fail loudly.

const AttackData = preload("res://scripts/combat/AttackData.gd")

const STAGE_PATH := "res://data/stages/aegis_rooftop.json"
const CHARACTER_PATHS := [
	"res://data/characters/captain_america.json",
	"res://data/characters/batman.json",
]
const PLATFORM_TYPES := ["ground", "platform"]


static func load_json(path: String) -> Dictionary:
	var result := {"data": {}, "errors": PackedStringArray()}
	if not FileAccess.file_exists(path):
		result["errors"].append("missing data file: %s" % path)
		return result
	var json := JSON.new()
	var status := json.parse(FileAccess.get_file_as_string(path))
	if status != OK:
		result["errors"].append(
			"%s: invalid JSON at line %d: %s"
			% [path, json.get_error_line(), json.get_error_message()]
		)
		return result
	if typeof(json.data) != TYPE_DICTIONARY:
		result["errors"].append("%s: top-level value must be an object" % path)
		return result
	result["data"] = json.data
	return result


## Load and validate the stage and every fighter for one match.
static func load_match_content(
	stage_path: String = STAGE_PATH, character_paths: Array = CHARACTER_PATHS
) -> Dictionary:
	var errors := PackedStringArray()
	var stage_result := load_json(stage_path)
	errors.append_array(stage_result["errors"])
	if stage_result["errors"].is_empty():
		errors.append_array(validate_stage(stage_result["data"], stage_path))
	var characters := []
	for path in character_paths:
		var character_result := load_json(path)
		errors.append_array(character_result["errors"])
		if character_result["errors"].is_empty():
			errors.append_array(validate_character(character_result["data"], path))
			characters.append(character_result["data"])
	if characters.size() < 2 and errors.is_empty():
		errors.append("a match needs at least two fighters")
	var spawn_points: Array = stage_result["data"].get("spawn_points", [])
	if errors.is_empty() and spawn_points.size() < characters.size():
		errors.append("%s: fewer spawn points than fighters" % stage_path)
	return {"stage": stage_result["data"], "characters": characters, "errors": errors}


static func validate_character(data: Dictionary, label: String) -> PackedStringArray:
	var errors := PackedStringArray()
	if typeof(data.get("name")) != TYPE_STRING or String(data.get("name")).is_empty():
		errors.append("%s: name must be a non-empty string" % label)
	if data.has("color") and typeof(data["color"]) != TYPE_STRING:
		errors.append("%s: color must be a string such as \"#d13434\"" % label)
	var stats: Variant = data.get("stats")
	if typeof(stats) != TYPE_DICTIONARY:
		errors.append("%s: stats must be an object" % label)
		return errors
	for key in ["weight", "run_speed", "jump_force", "damage_scale"]:
		if not _positive(stats.get(key)):
			errors.append("%s: stats.%s must be a positive number" % [label, key])
	if not _is_number(stats.get("air_control")) or not (0.0 < float(stats.get("air_control")) and float(stats.get("air_control")) <= 1.0):
		errors.append("%s: stats.air_control must be in (0, 1]" % label)
	if not _whole(stats.get("stocks")) or int(stats.get("stocks")) < 1:
		errors.append("%s: stats.stocks must be a whole number of at least 1" % label)
	if stats.has("air_jumps") and (not _whole(stats["air_jumps"]) or int(stats["air_jumps"]) < 0):
		errors.append("%s: stats.air_jumps must be a non-negative whole number" % label)
	var attacks: Variant = data.get("attacks", {})
	if typeof(attacks) != TYPE_DICTIONARY:
		errors.append("%s: attacks must be an object" % label)
	else:
		for attack_name in attacks:
			errors.append_array(
				AttackData.validate(attacks[attack_name], "%s: attacks.%s" % [label, attack_name])
			)
	return errors


static func validate_stage(data: Dictionary, label: String) -> PackedStringArray:
	var errors := PackedStringArray()
	var zones: Variant = data.get("blast_zones")
	var zones_valid := typeof(zones) == TYPE_DICTIONARY
	if zones_valid:
		for key in ["left", "right", "top", "bottom"]:
			if not _is_number(zones.get(key)):
				zones_valid = false
				errors.append("%s: blast_zones.%s must be a number" % [label, key])
		if zones_valid and (zones["left"] >= zones["right"] or zones["top"] >= zones["bottom"]):
			zones_valid = false
			errors.append("%s: blast zones must satisfy left < right and top < bottom" % label)
	else:
		errors.append("%s: blast_zones must be an object" % label)
	var platforms: Variant = data.get("platforms")
	if typeof(platforms) != TYPE_ARRAY or platforms.is_empty():
		errors.append("%s: platforms must be a non-empty array" % label)
		platforms = []
	var grounds := 0
	for index in platforms.size():
		var platform: Variant = platforms[index]
		var where := "%s: platforms[%d]" % [label, index]
		if typeof(platform) != TYPE_DICTIONARY:
			errors.append("%s must be an object" % where)
			continue
		var shape_valid := true
		for key in ["x", "y"]:
			if not _is_number(platform.get(key)):
				shape_valid = false
				errors.append("%s.%s must be a number" % [where, key])
		for key in ["width", "height"]:
			if not _positive(platform.get(key)):
				shape_valid = false
				errors.append("%s.%s must be a positive number" % [where, key])
		if not platform.get("type") in PLATFORM_TYPES:
			errors.append("%s.type must be one of %s" % [where, PLATFORM_TYPES])
		elif platform["type"] == "ground":
			grounds += 1
		if shape_valid and zones_valid:
			var half: float = platform["width"] / 2.0
			if (
				platform["x"] - half <= zones["left"]
				or platform["x"] + half >= zones["right"]
				or platform["y"] <= zones["top"]
				or platform["y"] + platform["height"] >= zones["bottom"]
			):
				errors.append("%s lies on or beyond a blast zone" % where)
	if grounds == 0 and not platforms.is_empty():
		errors.append("%s: at least one ground platform is required" % label)
	var spawns: Variant = data.get("spawn_points")
	if typeof(spawns) != TYPE_ARRAY or spawns.size() < 2:
		errors.append("%s: at least two spawn_points are required" % label)
	elif zones_valid:
		for index in spawns.size():
			var point: Variant = spawns[index]
			if typeof(point) != TYPE_DICTIONARY or not _is_number(point.get("x")) or not _is_number(point.get("y")):
				errors.append("%s: spawn_points[%d] must have numeric x and y" % [label, index])
				continue
			if not (zones["left"] < point["x"] and point["x"] < zones["right"] and zones["top"] < point["y"] and point["y"] < zones["bottom"]):
				errors.append("%s: spawn_points[%d] is outside the blast zones" % [label, index])
			elif not _has_support_below(point, platforms):
				errors.append("%s: spawn_points[%d] has no platform beneath it" % [label, index])
	if data.has("respawn_invulnerability_ticks") and (
		not _whole(data["respawn_invulnerability_ticks"]) or int(data["respawn_invulnerability_ticks"]) < 0
	):
		errors.append("%s: respawn_invulnerability_ticks must be a non-negative whole number" % label)
	return errors


static func _has_support_below(point: Dictionary, platforms: Array) -> bool:
	for platform in platforms:
		if typeof(platform) != TYPE_DICTIONARY or not _positive(platform.get("width")):
			continue
		var half: float = platform["width"] / 2.0
		if platform["x"] - half <= point["x"] and point["x"] <= platform["x"] + half and point["y"] <= platform["y"]:
			return true
	return false


static func _is_number(value: Variant) -> bool:
	return typeof(value) == TYPE_INT or typeof(value) == TYPE_FLOAT


static func _positive(value: Variant) -> bool:
	return _is_number(value) and float(value) > 0.0


static func _whole(value: Variant) -> bool:
	return _is_number(value) and float(value) == floor(float(value))

extends RefCounted
## Validation and normalisation for data-driven attack definitions.
##
## Attacks are plain dictionaries loaded from character data. `normalize` returns a
## typed copy, so simulation code never reads raw JSON numbers (which parse as floats).

const REQUIRED_TICKS := ["startup_ticks", "active_ticks", "recovery_ticks"]
const REQUIRED_NUMBERS := [
	"damage",
	"base_knockback",
	"knockback_growth",
	"angle_degrees",
	"hitstun_multiplier",
]
const HITBOX_KEYS := ["x", "y", "width", "height"]


static func validate(raw: Variant, label: String) -> PackedStringArray:
	var errors := PackedStringArray()
	if typeof(raw) != TYPE_DICTIONARY:
		errors.append("%s must be an object" % label)
		return errors
	if typeof(raw.get("id")) != TYPE_STRING or String(raw.get("id")).is_empty():
		errors.append("%s.id must be a non-empty string" % label)
	for key in REQUIRED_TICKS:
		if not _is_number(raw.get(key)) or float(raw.get(key)) != floor(float(raw.get(key))):
			errors.append("%s.%s must be a whole number" % [label, key])
		elif int(raw.get(key)) < (1 if key != "recovery_ticks" else 0):
			errors.append("%s.%s is out of range" % [label, key])
	for key in REQUIRED_NUMBERS:
		if not _is_number(raw.get(key)):
			errors.append("%s.%s must be a number" % [label, key])
		elif key != "angle_degrees" and float(raw.get(key)) < 0.0:
			errors.append("%s.%s must not be negative" % [label, key])
	var hitbox: Variant = raw.get("hitbox")
	if typeof(hitbox) != TYPE_DICTIONARY:
		errors.append("%s.hitbox must be an object" % label)
	else:
		for key in HITBOX_KEYS:
			if not _is_number(hitbox.get(key)):
				errors.append("%s.hitbox.%s must be a number" % [label, key])
		if _is_number(hitbox.get("width")) and float(hitbox.get("width")) <= 0.0:
			errors.append("%s.hitbox.width must be positive" % label)
		if _is_number(hitbox.get("height")) and float(hitbox.get("height")) <= 0.0:
			errors.append("%s.hitbox.height must be positive" % label)
	return errors


static func normalize(raw: Dictionary) -> Dictionary:
	var hitbox: Dictionary = raw["hitbox"]
	return {
		"id": String(raw["id"]),
		"startup_ticks": int(raw["startup_ticks"]),
		"active_ticks": int(raw["active_ticks"]),
		"recovery_ticks": int(raw["recovery_ticks"]),
		"damage": float(raw["damage"]),
		"base_knockback": float(raw["base_knockback"]),
		"knockback_growth": float(raw["knockback_growth"]),
		"angle_degrees": float(raw["angle_degrees"]),
		"hitstun_multiplier": float(raw["hitstun_multiplier"]),
		"hitbox": Rect2(
			float(hitbox["x"]), float(hitbox["y"]), float(hitbox["width"]), float(hitbox["height"])
		),
	}


static func total_ticks(attack: Dictionary) -> int:
	return attack["startup_ticks"] + attack["active_ticks"] + attack["recovery_ticks"]


## Phase name for a tick counted from the attack's first tick (0).
static func phase(attack: Dictionary, tick: int) -> String:
	if tick < attack["startup_ticks"]:
		return "startup"
	if tick < attack["startup_ticks"] + attack["active_ticks"]:
		return "active"
	if tick < total_ticks(attack):
		return "recovery"
	return "idle"


static func _is_number(value: Variant) -> bool:
	return typeof(value) == TYPE_INT or typeof(value) == TYPE_FLOAT

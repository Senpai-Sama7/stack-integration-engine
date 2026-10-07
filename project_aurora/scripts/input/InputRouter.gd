extends RefCounted
## Samples the keyboard once per simulation tick and converts it into per-player
## command dictionaries. Physical keycodes keep the layout stable across keyboard maps.

const BUTTONS := ["left", "right", "jump", "light", "heavy", "special", "shield"]

const BINDINGS := [
	{
		"left": KEY_A,
		"right": KEY_D,
		"jump": KEY_W,
		"light": KEY_J,
		"heavy": KEY_K,
		"special": KEY_L,
		"shield": KEY_S,
	},
	{
		"left": KEY_LEFT,
		"right": KEY_RIGHT,
		"jump": KEY_UP,
		"light": KEY_COMMA,
		"heavy": KEY_PERIOD,
		"special": KEY_SLASH,
		"shield": KEY_DOWN,
	},
]


static func neutral_command() -> Dictionary:
	var command := {}
	for button in BUTTONS:
		command[button] = false
	return command


func sample_commands(player_count: int) -> Array:
	var commands := []
	for player in player_count:
		var command := neutral_command()
		if player < BINDINGS.size():
			for button in BUTTONS:
				command[button] = Input.is_physical_key_pressed(BINDINGS[player][button])
		commands.append(command)
	return commands

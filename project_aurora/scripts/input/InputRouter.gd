extends RefCounted
class_name InputRouter

const EMPTY_ACTIONS := {
	"left": false,
	"right": false,
	"jump": false,
	"light": false,
	"heavy": false,
	"special": false,
	"shield": false,
}

var state: Dictionary = {
	"P1": EMPTY_ACTIONS.duplicate(true),
	"P2": EMPTY_ACTIONS.duplicate(true),
}

func handle_event(event: InputEvent) -> void:
	if not (event is InputEventKey):
		return
	if event.is_echo():
		return

	var key := event.physical_keycode
	var pressed := event.pressed
	_apply_key("P1", key, pressed)
	_apply_key("P2", key, pressed)

func update_state_from_keyboard() -> void:
	state["P1"] = {
		"left": Input.is_key_pressed(KEY_A),
		"right": Input.is_key_pressed(KEY_D),
		"jump": Input.is_key_pressed(KEY_W),
		"light": Input.is_key_pressed(KEY_J),
		"heavy": Input.is_key_pressed(KEY_K),
		"special": Input.is_key_pressed(KEY_L),
		"shield": Input.is_key_pressed(KEY_S),
	}
	state["P2"] = {
		"left": Input.is_key_pressed(KEY_LEFT),
		"right": Input.is_key_pressed(KEY_RIGHT),
		"jump": Input.is_key_pressed(KEY_UP),
		"light": Input.is_key_pressed(KEY_COMMA),
		"heavy": Input.is_key_pressed(KEY_PERIOD),
		"special": Input.is_key_pressed(KEY_SLASH),
		"shield": Input.is_key_pressed(KEY_DOWN),
	}

func read_actions(player_id: String) -> Dictionary:
	if not state.has(player_id):
		return EMPTY_ACTIONS.duplicate(true)
	return state[player_id].duplicate(true)

func _apply_key(player_id: String, key: Key, pressed: bool) -> void:
	if player_id == "P1":
		match key:
			KEY_A:
				state[player_id]["left"] = pressed
			KEY_D:
				state[player_id]["right"] = pressed
			KEY_W:
				state[player_id]["jump"] = pressed
			KEY_J:
				state[player_id]["light"] = pressed
			KEY_K:
				state[player_id]["heavy"] = pressed
			KEY_L:
				state[player_id]["special"] = pressed
			KEY_S:
				state[player_id]["shield"] = pressed
	elif player_id == "P2":
		match key:
			KEY_LEFT:
				state[player_id]["left"] = pressed
			KEY_RIGHT:
				state[player_id]["right"] = pressed
			KEY_UP:
				state[player_id]["jump"] = pressed
			KEY_COMMA:
				state[player_id]["light"] = pressed
			KEY_PERIOD:
				state[player_id]["heavy"] = pressed
			KEY_SLASH:
				state[player_id]["special"] = pressed
			KEY_DOWN:
				state[player_id]["shield"] = pressed

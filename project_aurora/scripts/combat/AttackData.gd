extends RefCounted
class_name InputRouter

var input_state: Dictionary = {
    "Captain America": {
        "move_left": false,
        "move_right": false,
        "jump": false,
        "light_attack": false,
        "heavy_attack": false,
        "special": false,
        "shield": false,
    },
    "Batman": {
        "move_left": false,
        "move_right": false,
        "jump": false,
        "light_attack": false,
        "heavy_attack": false,
        "special": false,
        "shield": false,
    },
}

func handle_event(event: InputEvent) -> void:
    if event is InputEventKey:
        var key := event.physical_keycode
        var pressed := event.pressed

        match key:
            KEY_A:
                input_state["Captain America"]["move_left"] = pressed
            KEY_D:
                input_state["Captain America"]["move_right"] = pressed
            KEY_W:
                input_state["Captain America"]["jump"] = pressed
            KEY_J:
                input_state["Captain America"]["light_attack"] = pressed
            KEY_K:
                input_state["Captain America"]["heavy_attack"] = pressed
            KEY_L:
                input_state["Captain America"]["special"] = pressed
            KEY_S:
                input_state["Captain America"]["shield"] = pressed

            KEY_LEFT:
                input_state["Batman"]["move_left"] = pressed
            KEY_RIGHT:
                input_state["Batman"]["move_right"] = pressed
            KEY_UP:
                input_state["Batman"]["jump"] = pressed
            KEY_COMMA:
                input_state["Batman"]["light_attack"] = pressed
            KEY_PERIOD:
                input_state["Batman"]["heavy_attack"] = pressed
            KEY_SLASH:
                input_state["Batman"]["special"] = pressed
            KEY_DOWN:
                input_state["Batman"]["shield"] = pressed

func read_actions(fighter_name: String) -> Dictionary:
    if input_state.has(fighter_name):
        return input_state[fighter_name]
    return {}

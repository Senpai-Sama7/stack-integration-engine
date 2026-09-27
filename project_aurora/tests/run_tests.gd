extends SceneTree

func _initialize() -> void:
    var game_script = load("res://scripts/core/Game.gd")
    assert(game_script != null)

    var state_script = load("res://scripts/core/MatchState.gd")
    assert(state_script != null)

    var attack_data = load("res://scripts/combat/AttackData.gd").new("light_test", 8.0, 260.0)
    assert(attack_data.damage == 8.0)
    assert(attack_data.knockback == 260.0)

    var fighter = load("res://scripts/core/Fighter.gd").new("Test Fighter", Vector2.ZERO, Color(1.0, 1.0, 1.0, 1.0))
    fighter.take_damage(10.0, Vector2(240.0, -120.0))
    assert(fighter.damage == 10.0)

    print("Project Aurora smoke test passed.")
    quit()

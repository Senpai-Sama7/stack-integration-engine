extends SceneTree
## Headless project validation gate.
##
##   godot --headless --path . -s res://tools/validate_project.gd
##
## `godot --editor --quit` exits 0 even when scenes and scripts fail to parse, so it
## cannot gate anything. This script loads every script and scene, instantiates every
## scene, validates content data, and boots the main scene; any problem exits 1.

const DataLoader = preload("res://scripts/core/DataLoader.gd")

const EXTENSIONS := ["gd", "tscn", "tres"]


func _initialize() -> void:
	# Booting the main scene needs a running main loop (_ready is deferred until then).
	process_frame.connect(_validate, CONNECT_ONE_SHOT)


func _validate() -> void:
	var problems := PackedStringArray()
	var paths := _collect("res://")
	for path in paths:
		# Scenes load even when an ext_resource is missing (the node silently loses
		# it), so every declared dependency must exist on its own.
		for dependency in ResourceLoader.get_dependencies(path):
			var dependency_path := _dependency_path(dependency)
			if not dependency_path.is_empty() and not ResourceLoader.exists(dependency_path):
				problems.append("%s references missing %s" % [path, dependency_path])
		if path.get_extension() == "gd":
			# Compile a fresh copy: a cached script can look valid after a failed parse.
			var probe := GDScript.new()
			probe.source_code = FileAccess.get_file_as_string(path)
			if probe.reload() != OK:
				problems.append("script failed to compile: %s" % path)
			continue
		var resource := ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_REUSE)
		if resource == null:
			problems.append("failed to load %s" % path)
		elif resource is PackedScene:
			var instance: Node = resource.instantiate()
			if instance == null:
				problems.append("scene cannot be instantiated: %s" % path)
			else:
				instance.free()
	problems.append_array(DataLoader.load_match_content()["errors"])
	problems.append_array(_boot_main_scene())
	if problems.is_empty():
		print("project validation passed: %d resources" % paths.size())
		quit(0)
		return
	for problem in problems:
		printerr("validation error: %s" % problem)
	printerr("project validation failed: %d problem(s)" % problems.size())
	quit(1)


func _boot_main_scene() -> PackedStringArray:
	var problems := PackedStringArray()
	var main_path := String(ProjectSettings.get_setting("application/run/main_scene", ""))
	if main_path.is_empty() or not ResourceLoader.exists(main_path):
		problems.append("application/run/main_scene is missing: %s" % main_path)
		return problems
	var scene: PackedScene = load(main_path)
	if scene == null:
		problems.append("main scene failed to load: %s" % main_path)
		return problems
	var main := scene.instantiate()
	root.add_child(main)
	if not ("load_errors" in main and "simulation" in main):
		problems.append("main scene root is missing its game controller script")
	elif not main.load_errors.is_empty():
		problems.append_array(main.load_errors)
	elif main.simulation == null:
		problems.append("main scene did not create a simulation")
	else:
		for _i in 60:
			main._physics_process(1.0 / 60.0)
		if main.simulation.tick != 60:
			problems.append("main loop advanced %d of 60 ticks" % main.simulation.tick)
	root.remove_child(main)
	main.free()
	return problems


static func _dependency_path(dependency: String) -> String:
	for part in dependency.split("::"):
		if part.begins_with("res://"):
			return part
	return ""


func _collect(directory: String) -> PackedStringArray:
	var found := PackedStringArray()
	var access := DirAccess.open(directory)
	if access == null:
		return found
	access.include_hidden = false
	for child in access.get_directories():
		if not child.begins_with("."):
			found.append_array(_collect(directory.path_join(child)))
	for file in access.get_files():
		if file.get_extension() in EXTENSIONS:
			found.append(directory.path_join(file))
	found.sort()
	return found

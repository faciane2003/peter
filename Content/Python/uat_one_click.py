import unreal
import json
import os
import time
import random
import math

# ============================================================
# CONFIG
# ============================================================
DELTA_X_CM = 100.0
DUPLICATE_UP_FEET = 10.0
TAG_TO_ADD = "AUTO_EDIT"
LOG_FILE_NAME = "uat_script.log"
LOG_SNAPSHOT_NAME = "uat_log_snapshot.txt"

BLUE_NAME = "M_UAT_Blue"
RED_NAME  = "M_UAT_Red"
MATERIAL_PATH = "/Game/UAT_Materials"
CONVERT_TO_SPHERE = True
PLANE_MESH_PATH = "/Engine/BasicShapes/Plane.Plane"
SPHERE_MESH_PATH = "/Engine/BasicShapes/Sphere.Sphere"
CUBE_MESH_PATH = "/Engine/BasicShapes/Cube.Cube"

CREATE_TRIANGLES = True
TRIANGLE_COUNT = 20
TRIANGLE_MIN_SIZE_CM = 30.0
TRIANGLE_MAX_SIZE_CM = 120.0

CREATE_GRASS_FIELD = True
GRASS_ROWS = 12
GRASS_COLS = 12
GRASS_SPACING_CM = 80.0
GRASS_BLADE_SCALE = 0.25

LIFELIKE_GRASS_ROWS = 24
LIFELIKE_GRASS_COLS = 24
LIFELIKE_GRASS_SPACING_CM = 45.0
LIFELIKE_GRASS_SCALE_MIN = 0.25
LIFELIKE_GRASS_SCALE_MAX = 0.45
LIFELIKE_GRASS_WIND_SPEED = 0.6
LIFELIKE_GRASS_WIND_STRENGTH = 6.0

CREATE_SPHERE_CIRCLE = True
SPHERE_COUNT = 30
SPHERE_RADIUS_CM = 400.0
SPHERE_SCALE = 0.6

CREATE_ROTATING_CUBE = False

# Quick command override (set to None to use normal flow)
COMMAND = "diagnostic_solar_system"
CUBE_SCALE = 3.0
CUBE_ROTATION_RATE = unreal.Rotator(0.0, 45.0, 0.0)
CUBE_ROTATE_IN_EDITOR = True
CUBE_ROTATE_DEG_PER_SEC = 45.0

# ============================================================
# HELPERS
# ============================================================
_rotating_cubes = []
_rotate_tick_handle = None

def ts():
    return time.strftime("%Y%m%d_%H%M%S")

def log(msg):
    unreal.log(f"[UAT] {msg}")
    _append_log_line(msg)

def automation_dir():
    d = os.path.join(unreal.Paths.project_saved_dir(), "Automation")
    os.makedirs(d, exist_ok=True)
    return d

def actor_sub():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

def _log_file_path():
    return os.path.join(automation_dir(), LOG_FILE_NAME)

def _log_snapshot_path():
    return os.path.join(automation_dir(), LOG_SNAPSHOT_NAME)

def _append_log_line(msg):
    try:
        with open(_log_file_path(), "a", encoding="utf-8") as f:
            f.write(f"{ts()} {msg}\n")
    except Exception as exc:
        unreal.log_warning(f"[UAT] Failed to write log file: {exc}")

def write_log_marker(marker="Manual log marker"):
    _append_log_line(f"[MARKER] {marker}")

def snapshot_log_to_file():
    try:
        src = _log_file_path()
        if not os.path.exists(src):
            _append_log_line("[INFO] Log file missing; creating new log.")
        with open(src, "r", encoding="utf-8") as f:
            content = f.read()
        with open(_log_snapshot_path(), "w", encoding="utf-8") as out:
            out.write(content)
    except Exception as exc:
        unreal.log_warning(f"[UAT] Failed to snapshot log: {exc}")

def log_diagnostic_state(tag):
    try:
        world = unreal.EditorLevelLibrary.get_editor_world()
        level_name = world.get_name() if world else "None"
        actor_count = len(unreal.EditorLevelLibrary.get_all_level_actors())
        log(f"{tag}: level={level_name} actors={actor_count}")
    except Exception as exc:
        unreal.log_warning(f"[UAT] Failed to read diagnostic state: {exc}")

def run_command_once(command_name):
    """Temporarily set COMMAND, run main(), then restore."""
    global COMMAND
    prev = COMMAND
    try:
        COMMAND = command_name
        main()
    finally:
        COMMAND = prev

def _stop_rotate_tick():
    global _rotate_tick_handle
    if _rotate_tick_handle is not None:
        unreal.unregister_slate_post_tick_callback(_rotate_tick_handle)
        _rotate_tick_handle = None

def _rotate_tick(delta_seconds):
    global _rotating_cubes
    if not _rotating_cubes:
        _stop_rotate_tick()
        return

    alive = []
    for actor in _rotating_cubes:
        if not unreal.SystemLibrary.is_valid(actor):
            continue
        rot = actor.get_actor_rotation()
        rot.yaw += CUBE_ROTATE_DEG_PER_SEC * delta_seconds
        actor.set_actor_rotation(rot, teleport_physics=True)
        alive.append(actor)

    _rotating_cubes = alive
    if not _rotating_cubes:
        _stop_rotate_tick()

# ============================================================
# MATERIALS (STABLE UE5 IMPLEMENTATION)
# ============================================================
def ensure_material(name, color):
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    mat_path = f"{MATERIAL_PATH}/{name}"

    if unreal.EditorAssetLibrary.does_asset_exist(mat_path):
        return unreal.EditorAssetLibrary.load_asset(mat_path)

    unreal.EditorAssetLibrary.make_directory(MATERIAL_PATH)

    material = asset_tools.create_asset(
        asset_name=name,
        package_path=MATERIAL_PATH,
        asset_class=unreal.Material,
        factory=unreal.MaterialFactoryNew()
    )

    # Constant color node (safe across UE 5.x)
    expr = unreal.MaterialEditingLibrary.create_material_expression(
        material,
        unreal.MaterialExpressionConstant3Vector
    )
    expr.constant = color

    unreal.MaterialEditingLibrary.connect_material_property(
        expr,
        "",
        unreal.MaterialProperty.MP_BASE_COLOR
    )

    unreal.MaterialEditingLibrary.recompile_material(material)
    unreal.EditorAssetLibrary.save_asset(mat_path)

    log(f"Created material {mat_path}")
    return material

def ensure_lifelike_grass_material(name="M_UAT_Grass_Lifelike"):
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    mat_path = f"{MATERIAL_PATH}/{name}"

    if unreal.EditorAssetLibrary.does_asset_exist(mat_path):
        return unreal.EditorAssetLibrary.load_asset(mat_path)

    unreal.EditorAssetLibrary.make_directory(MATERIAL_PATH)

    material = asset_tools.create_asset(
        asset_name=name,
        package_path=MATERIAL_PATH,
        asset_class=unreal.Material,
        factory=unreal.MaterialFactoryNew()
    )
    material.set_editor_property("two_sided", True)

    color_a = unreal.MaterialEditingLibrary.create_material_expression(
        material,
        unreal.MaterialExpressionConstant3Vector
    )
    color_a.constant = unreal.LinearColor(0.08, 0.35, 0.08, 1.0)

    color_b = unreal.MaterialEditingLibrary.create_material_expression(
        material,
        unreal.MaterialExpressionConstant3Vector
    )
    color_b.constant = unreal.LinearColor(0.12, 0.50, 0.12, 1.0)

    per_instance = unreal.MaterialEditingLibrary.create_material_expression(
        material,
        unreal.MaterialExpressionPerInstanceRandom
    )

    lerp = unreal.MaterialEditingLibrary.create_material_expression(
        material,
        unreal.MaterialExpressionLinearInterpolate
    )
    unreal.MaterialEditingLibrary.connect_material_expressions(color_a, "", lerp, "A")
    unreal.MaterialEditingLibrary.connect_material_expressions(color_b, "", lerp, "B")
    unreal.MaterialEditingLibrary.connect_material_expressions(per_instance, "", lerp, "Alpha")

    unreal.MaterialEditingLibrary.connect_material_property(
        lerp,
        "",
        unreal.MaterialProperty.MP_BASE_COLOR
    )

    time = unreal.MaterialEditingLibrary.create_material_expression(
        material,
        unreal.MaterialExpressionTime
    )
    speed = unreal.MaterialEditingLibrary.create_material_expression(
        material,
        unreal.MaterialExpressionConstant
    )
    speed.r = LIFELIKE_GRASS_WIND_SPEED

    time_scaled = unreal.MaterialEditingLibrary.create_material_expression(
        material,
        unreal.MaterialExpressionMultiply
    )
    unreal.MaterialEditingLibrary.connect_material_expressions(time, "", time_scaled, "A")
    unreal.MaterialEditingLibrary.connect_material_expressions(speed, "", time_scaled, "B")

    sine = unreal.MaterialEditingLibrary.create_material_expression(
        material,
        unreal.MaterialExpressionSine
    )
    unreal.MaterialEditingLibrary.connect_material_expressions(time_scaled, "", sine, "Input")

    amp = unreal.MaterialEditingLibrary.create_material_expression(
        material,
        unreal.MaterialExpressionConstant
    )
    amp.r = LIFELIKE_GRASS_WIND_STRENGTH

    sway = unreal.MaterialEditingLibrary.create_material_expression(
        material,
        unreal.MaterialExpressionMultiply
    )
    unreal.MaterialEditingLibrary.connect_material_expressions(sine, "", sway, "A")
    unreal.MaterialEditingLibrary.connect_material_expressions(amp, "", sway, "B")

    normal_ws = unreal.MaterialEditingLibrary.create_material_expression(
        material,
        unreal.MaterialExpressionVertexNormalWS
    )
    wpo = unreal.MaterialEditingLibrary.create_material_expression(
        material,
        unreal.MaterialExpressionMultiply
    )
    unreal.MaterialEditingLibrary.connect_material_expressions(normal_ws, "", wpo, "A")
    unreal.MaterialEditingLibrary.connect_material_expressions(sway, "", wpo, "B")

    unreal.MaterialEditingLibrary.connect_material_property(
        wpo,
        "",
        unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET
    )

    unreal.MaterialEditingLibrary.recompile_material(material)
    unreal.EditorAssetLibrary.save_asset(mat_path)
    log(f"Created lifelike grass material {mat_path}")
    return material

def set_actor_material(actor, material):
    for comp in actor.get_components_by_class(unreal.MeshComponent):
        for i in range(comp.get_num_materials()):
            comp.set_material(i, material)

def set_actor_static_mesh(actor, mesh):
    for comp in actor.get_components_by_class(unreal.StaticMeshComponent):
        comp.set_static_mesh(mesh)

def spawn_triangle(location, size_cm, material=None):
    cls = getattr(unreal, "ProceduralMeshActor", None)
    if not cls:
        unreal.log_error("[UAT] ProceduralMeshActor not available.")
        return None

    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(cls, location)
    comp = actor.get_component_by_class(unreal.ProceduralMeshComponent)
    if not comp:
        unreal.log_error("[UAT] ProceduralMeshComponent not found on actor.")
        return actor

    v0 = unreal.Vector(0.0, 0.0, 0.0)
    v1 = unreal.Vector(size_cm, 0.0, 0.0)
    v2 = unreal.Vector(0.0, size_cm * 0.6, 0.0)
    verts = [v0, v1, v2]
    tris = [0, 1, 2]
    normals = [unreal.Vector(0.0, 0.0, 1.0)] * 3
    uvs = [unreal.Vector2D(0.0, 0.0), unreal.Vector2D(1.0, 0.0), unreal.Vector2D(0.0, 1.0)]
    tangents = [unreal.ProcMeshTangent(1.0, 0.0, 0.0)] * 3
    colors = [unreal.LinearColor(1.0, 1.0, 1.0, 1.0)] * 3

    comp.create_mesh_section(0, verts, tris, normals, uvs, colors, tangents, True)
    if material:
        comp.set_material(0, material)

    return actor

def spawn_grass_field(center, material=None):
    plane = unreal.EditorAssetLibrary.load_asset(PLANE_MESH_PATH)
    if not plane:
        unreal.log_error(f"[UAT] Plane mesh not found: {PLANE_MESH_PATH}")
        return

    start_x = center.x - (GRASS_ROWS - 1) * GRASS_SPACING_CM * 0.5
    start_y = center.y - (GRASS_COLS - 1) * GRASS_SPACING_CM * 0.5

    for r in range(GRASS_ROWS):
        for c in range(GRASS_COLS):
            loc = unreal.Vector(
                start_x + r * GRASS_SPACING_CM,
                start_y + c * GRASS_SPACING_CM,
                center.z
            )
            actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, loc)
            comp = actor.get_component_by_class(unreal.StaticMeshComponent)
            comp.set_static_mesh(plane)
            if material:
                comp.set_material(0, material)

            yaw = random.uniform(0.0, 360.0)
            pitch = random.uniform(70.0, 90.0)
            actor.set_actor_rotation(unreal.Rotator(pitch, yaw, 0.0), teleport_physics=True)
            actor.set_actor_scale3d(unreal.Vector(GRASS_BLADE_SCALE, GRASS_BLADE_SCALE, GRASS_BLADE_SCALE))

def spawn_grass_field_instanced(center, material=None, rows=12, cols=12, spacing_cm=80.0):
    plane = unreal.EditorAssetLibrary.load_asset(PLANE_MESH_PATH)
    if not plane:
        unreal.log_error(f"[UAT] Plane mesh not found: {PLANE_MESH_PATH}")
        return

    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.InstancedStaticMeshActor, center)
    comp = actor.get_component_by_class(unreal.InstancedStaticMeshComponent)
    comp.set_static_mesh(plane)
    if material:
        comp.set_material(0, material)

    start_x = center.x - (rows - 1) * spacing_cm * 0.5
    start_y = center.y - (cols - 1) * spacing_cm * 0.5

    for r in range(rows):
        for c in range(cols):
            loc = unreal.Vector(
                start_x + r * spacing_cm,
                start_y + c * spacing_cm,
                center.z
            )
            yaw = random.uniform(0.0, 360.0)
            pitch = random.uniform(70.0, 90.0)
            scale = random.uniform(LIFELIKE_GRASS_SCALE_MIN, LIFELIKE_GRASS_SCALE_MAX)
            rot = unreal.Rotator(pitch, yaw, 0.0)
            scl = unreal.Vector(scale, scale, scale)
            comp.add_instance(unreal.Transform(loc, rot, scl))

def spawn_blue_sphere(center, radius_scale=1.0):
    sphere = unreal.EditorAssetLibrary.load_asset(SPHERE_MESH_PATH)
    if not sphere:
        unreal.log_error(f"[UAT] Sphere mesh not found: {SPHERE_MESH_PATH}")
        return
    blue_mat = ensure_material(
        BLUE_NAME,
        unreal.LinearColor(0.0, 0.0, 1.0, 1.0)
    )
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, center)
    comp = actor.get_component_by_class(unreal.StaticMeshComponent)
    comp.set_static_mesh(sphere)
    comp.set_material(0, blue_mat)
    actor.set_actor_scale3d(unreal.Vector(radius_scale, radius_scale, radius_scale))

def build_solar_system(origin):
    spawn_colored_sphere(origin, 6.0, unreal.LinearColor(1.0, 0.85, 0.2, 1.0), "Sun")

    planets = [
        ("Mercury", 300.0, 0.6, unreal.LinearColor(0.6, 0.6, 0.6, 1.0)),
        ("Venus",   500.0, 0.9, unreal.LinearColor(0.9, 0.7, 0.4, 1.0)),
        ("Earth",   700.0, 1.0, unreal.LinearColor(0.2, 0.4, 1.0, 1.0)),
        ("Mars",    900.0, 0.8, unreal.LinearColor(0.8, 0.3, 0.2, 1.0)),
        ("Jupiter", 1300.0, 3.0, unreal.LinearColor(0.9, 0.7, 0.5, 1.0)),
        ("Saturn",  1700.0, 2.6, unreal.LinearColor(0.9, 0.8, 0.6, 1.0)),
        ("Uranus",  2100.0, 2.2, unreal.LinearColor(0.6, 0.8, 0.9, 1.0)),
        ("Neptune", 2500.0, 2.1, unreal.LinearColor(0.3, 0.4, 0.9, 1.0)),
    ]

    for name, dist, scale, color in planets:
        loc = unreal.Vector(origin.x + dist, origin.y, origin.z)
        spawn_colored_sphere(loc, scale, color, name)

    spawn_colored_sphere(
        unreal.Vector(origin.x + 760.0, origin.y + 120.0, origin.z),
        0.25,
        unreal.LinearColor(0.7, 0.7, 0.7, 1.0),
        "Moon"
    )

def focus_view_on_origin(origin):
    try:
        cam_loc = origin + unreal.Vector(-1500.0, -1500.0, 800.0)
        cam_rot = unreal.MathLibrary.find_look_at_rotation(cam_loc, origin)
        unreal.EditorLevelLibrary.set_level_viewport_camera_info(cam_loc, cam_rot)
        log("Moved viewport camera to solar system")
    except Exception as exc:
        unreal.log_warning(f"[UAT] Failed to set viewport camera: {exc}")

def spawn_colored_sphere(center, radius_scale, color, label=None):
    sphere = unreal.EditorAssetLibrary.load_asset(SPHERE_MESH_PATH)
    if not sphere:
        unreal.log_error(f"[UAT] Sphere mesh not found: {SPHERE_MESH_PATH}")
        return None

    mat_name = f"M_UAT_{label}" if label else f"M_UAT_Sphere_{int(color.r*255)}_{int(color.g*255)}_{int(color.b*255)}"
    mat = ensure_material(mat_name, color)

    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, center)
    comp = actor.get_component_by_class(unreal.StaticMeshComponent)
    comp.set_static_mesh(sphere)
    comp.set_material(0, mat)
    actor.set_actor_scale3d(unreal.Vector(radius_scale, radius_scale, radius_scale))
    if label:
        actor.set_actor_label(label)
    return actor

def clear_shape_actors():
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    for actor in actors:
        try:
            has_mesh = bool(actor.get_components_by_class(unreal.StaticMeshComponent))
            has_instanced = bool(actor.get_components_by_class(unreal.InstancedStaticMeshComponent))
            has_proc = bool(actor.get_components_by_class(unreal.ProceduralMeshComponent))
        except Exception:
            continue
        if has_mesh or has_instanced or has_proc:
            actor_sub().destroy_actor(actor)

def write_log_paths():
    try:
        path_info = f"log_file={_log_file_path()}\nsnapshot_file={_log_snapshot_path()}\n"
        out_path = os.path.join(automation_dir(), "uat_log_paths.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(path_info)
    except Exception as exc:
        unreal.log_warning(f"[UAT] Failed to write log paths: {exc}")

def spawn_sphere_circle(center):
    sphere = unreal.EditorAssetLibrary.load_asset(SPHERE_MESH_PATH)
    if not sphere:
        unreal.log_error(f"[UAT] Sphere mesh not found: {SPHERE_MESH_PATH}")
        return

    for i in range(SPHERE_COUNT):
        angle = (i / float(SPHERE_COUNT)) * 360.0
        rad = math.radians(angle)
        loc = unreal.Vector(
            center.x + math.cos(rad) * SPHERE_RADIUS_CM,
            center.y + math.sin(rad) * SPHERE_RADIUS_CM,
            center.z
        )
        actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, loc)
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(sphere)
        actor.set_actor_scale3d(unreal.Vector(SPHERE_SCALE, SPHERE_SCALE, SPHERE_SCALE))

def spawn_rotating_cube(center):
    global _rotating_cubes, _rotate_tick_handle
    cube = unreal.EditorAssetLibrary.load_asset(CUBE_MESH_PATH)
    if not cube:
        unreal.log_error(f"[UAT] Cube mesh not found: {CUBE_MESH_PATH}")
        return

    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, center)
    comp = actor.get_component_by_class(unreal.StaticMeshComponent)
    comp.set_static_mesh(cube)
    actor.set_actor_scale3d(unreal.Vector(CUBE_SCALE, CUBE_SCALE, CUBE_SCALE))

    _rotating_cubes.append(actor)

    if CUBE_ROTATE_IN_EDITOR and _rotate_tick_handle is None:
        _rotate_tick_handle = unreal.register_slate_post_tick_callback(_rotate_tick)

def spawn_three_cones(center, spacing_cm=200.0):
    cone = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cone.Cone")
    if not cone:
        unreal.log_error("[UAT] Cone mesh not found: /Engine/BasicShapes/Cone.Cone")
        return

    for i in range(3):
        loc = unreal.Vector(center.x + (i * spacing_cm), center.y, center.z)
        actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, loc)
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(cone)

def spawn_three_rotating_cubes(center, spacing_cm=200.0):
    for i in range(3):
        loc = unreal.Vector(center.x + (i * spacing_cm), center.y, center.z)
        spawn_rotating_cube(loc)

def spawn_primitive_row(center, spacing_cm=250.0):
    assets = [
        ("/Engine/BasicShapes/Cube.Cube", "Cube"),
        ("/Engine/BasicShapes/Sphere.Sphere", "Sphere"),
        ("/Engine/BasicShapes/Cone.Cone", "Cone"),
        ("/Engine/BasicShapes/Cylinder.Cylinder", "Cylinder"),
        ("/Engine/BasicShapes/Plane.Plane", "Plane"),
    ]

    start_x = center.x - ((len(assets) - 1) * spacing_cm * 0.5)
    for i, (path, label) in enumerate(assets):
        mesh = unreal.EditorAssetLibrary.load_asset(path)
        if not mesh:
            unreal.log_error(f"[UAT] Missing primitive mesh: {path}")
            continue
        loc = unreal.Vector(start_x + (i * spacing_cm), center.y, center.z)
        actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, loc)
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(mesh)
        actor.set_actor_label(f"UAT_{label}")

# ============================================================
# EXPORT
# ============================================================
def export_selected(selected):
    data = {
        "timestamp": ts(),
        "actors": []
    }

    for a in selected:
        t = a.get_actor_transform()
        data["actors"].append({
            "id": a.get_path_name(),
            "transform": {
                "location": {
                    "x": float(t.translation.x),
                    "y": float(t.translation.y),
                    "z": float(t.translation.z),
                }
            },
            "tags": [str(tag) for tag in (a.tags or [])]
        })

    out = automation_dir()
    path = os.path.join(out, f"export_{ts()}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    log(f"Exported {len(data['actors'])} actor(s)")
    return data

# ============================================================
# MAIN
# ============================================================
def main():
    selected = list(actor_sub().get_selected_level_actors() or [])
    export_data = export_selected(selected) if selected else None
    center = selected[0].get_actor_location() if selected else unreal.Vector(0.0, 0.0, 0.0)

    if COMMAND == "add_three_cones":
        spawn_three_cones(center)
        log("Added three cones")
        return

    if COMMAND == "add_three_rotating_cubes":
        spawn_three_rotating_cubes(center)
        log("Added three rotating cubes")
        return

    if COMMAND == "add_one_each_primitive":
        spawn_primitive_row(center)
        log("Added one of each primitive shape")
        return

    if COMMAND == "add_blue_sphere":
        spawn_blue_sphere(center + unreal.Vector(0.0, 0.0, 100.0), radius_scale=1.0)
        log("Added blue sphere")
        return

    if COMMAND == "create_solar_system":
        clear_shape_actors()
        origin = unreal.Vector(0.0, 0.0, 0.0)
        build_solar_system(origin)
        log("Created solar system scene")
        return

    if COMMAND == "write_log_marker":
        write_log_marker("User-requested marker")
        log("Wrote log marker")
        return

    if COMMAND == "snapshot_log":
        snapshot_log_to_file()
        log("Wrote log snapshot file")
        return

    if COMMAND == "log_marker_and_snapshot":
        write_log_marker("User-requested marker")
        snapshot_log_to_file()
        log("Wrote log marker and snapshot file")
        return

    if COMMAND == "write_log_paths":
        write_log_paths()
        log("Wrote log path info file")
        return

    if COMMAND == "diagnostic_solar_system":
        write_log_marker("diagnostic_solar_system start")
        write_log_paths()
        log_diagnostic_state("Before")
        clear_shape_actors()
        origin = unreal.Vector(0.0, 0.0, 0.0)
        build_solar_system(origin)
        log("Created solar system scene")
        focus_view_on_origin(origin)
        log_diagnostic_state("After")
        snapshot_log_to_file()
        return

    if COMMAND == "spawn_grass_field":
        spawn_grass_field(center + unreal.Vector(0.0, 0.0, -5.0), None)
        log("Spawned grass field")
        return

    if COMMAND == "spawn_lifelike_grass_field":
        grass_mat = ensure_lifelike_grass_material()
        spawn_grass_field_instanced(
            center + unreal.Vector(0.0, 0.0, -5.0),
            grass_mat,
            rows=LIFELIKE_GRASS_ROWS,
            cols=LIFELIKE_GRASS_COLS,
            spacing_cm=LIFELIKE_GRASS_SPACING_CM
        )
        spawn_blue_sphere(center + unreal.Vector(0.0, 0.0, 200.0), radius_scale=1.5)
        log("Spawned lifelike instanced grass field and blue sphere")
        return

    if selected and CONVERT_TO_SPHERE:
        sphere = unreal.EditorAssetLibrary.load_asset(SPHERE_MESH_PATH)
        if not sphere:
            unreal.log_error(f"[UAT] Sphere mesh not found: {SPHERE_MESH_PATH}")
            return
        for actor in selected:
            set_actor_static_mesh(actor, sphere)
        log("Converted selected static meshes to spheres")

    # ---- Materials (UPDATED COLOR CALLS) ----
    blue_mat = ensure_material(
        BLUE_NAME,
        unreal.LinearColor(0.0, 0.0, 1.0, 1.0)
    )
    red_mat = ensure_material(
        RED_NAME,
        unreal.LinearColor(1.0, 0.0, 0.0, 1.0)
    )
    tri_mat = ensure_material(
        "M_UAT_Triangle",
        unreal.LinearColor(1.0, 1.0, 0.2, 1.0)
    )
    grass_mat = ensure_material(
        "M_UAT_Grass",
        unreal.LinearColor(0.1, 0.6, 0.1, 1.0)
    )

    # ---- Move + tag + BLUE original ----
    if selected:
        # ---- Move + tag + BLUE original ----
        for actor in selected:
            loc = actor.get_actor_location()
            loc.x += DELTA_X_CM
            actor.set_actor_location(loc, sweep=False, teleport=True)

            tags = [str(t) for t in (actor.tags or [])]
            if TAG_TO_ADD not in tags:
                tags.append(TAG_TO_ADD)
            actor.tags = [unreal.Name(t) for t in tags]

            set_actor_material(actor, blue_mat)

        # ---- Duplicate + move up + RED ----
        cm = DUPLICATE_UP_FEET * 30.48
        for actor in selected:
            dup = actor_sub().duplicate_actor(actor)
            if not dup:
                continue

            loc = dup.get_actor_location()
            loc.z += cm
            dup.set_actor_location(loc, sweep=False, teleport=True)
            set_actor_material(dup, red_mat)

    if CREATE_SPHERE_CIRCLE:
        spawn_sphere_circle(center)
        log(f"Spawned {SPHERE_COUNT} spheres in a circle")

    if CREATE_ROTATING_CUBE:
        spawn_rotating_cube(center)
        log("Spawned rotating cube at center")

    if CREATE_TRIANGLES:
        for _ in range(TRIANGLE_COUNT):
            size = random.uniform(TRIANGLE_MIN_SIZE_CM, TRIANGLE_MAX_SIZE_CM)
            offset = unreal.Vector(
                random.uniform(-300.0, 300.0),
                random.uniform(-300.0, 300.0),
                0.0
            )
            actor = spawn_triangle(center + offset, size, tri_mat)
            if actor:
                yaw = random.uniform(0.0, 360.0)
                actor.set_actor_rotation(unreal.Rotator(0.0, yaw, 0.0), teleport_physics=True)

        log(f"Spawned {TRIANGLE_COUNT} triangles")

    if CREATE_GRASS_FIELD:
        spawn_grass_field(center + unreal.Vector(0.0, 0.0, -5.0), grass_mat)
        log("Spawned grass field")

    log("Done: original = BLUE, duplicate = RED")

# ============================================================
if __name__ == "__main__":
    main()

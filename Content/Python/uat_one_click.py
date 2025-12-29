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
CODEX_LEVEL_DIR = "/Game/Codex_levels"
CONVERT_TO_SPHERE = True
PLANE_MESH_PATH = "/Engine/BasicShapes/Plane.Plane"
SPHERE_MESH_PATH = "/Engine/BasicShapes/Sphere.Sphere"
CUBE_MESH_PATH = "/Engine/BasicShapes/Cube.Cube"

CREATE_TRIANGLES = False
TRIANGLE_COUNT = 0
TRIANGLE_MIN_SIZE_CM = 30.0
TRIANGLE_MAX_SIZE_CM = 120.0

CREATE_GRASS_FIELD = False
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

CREATE_SPHERE_CIRCLE = False
SPHERE_COUNT = 0
SPHERE_RADIUS_CM = 400.0
SPHERE_SCALE = 0.6

CREATE_ROTATING_CUBE = False

# Quick command override (set to None to use normal flow)
COMMAND = None
CUBE_SCALE = 3.0
CUBE_ROTATION_RATE = unreal.Rotator(0.0, 45.0, 0.0)
CUBE_ROTATE_IN_EDITOR = True
CUBE_ROTATE_DEG_PER_SEC = 45.0

# ============================================================
# HELPERS
# ============================================================
_rotating_cubes = []
_rotate_tick_handle = None
_moving_actors = []
_move_tick_handle = None
_move_time_accum = 0.0
_move_debug_counter = 0
_MOVE_BOUNDS = unreal.Vector(3600.0, 3600.0, 1600.0)
_MOVE_Z_MIN = 80.0

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

def delete_codex_levels():
    try:
        # Avoid deleting the currently loaded Codex level to prevent editor asserts.
        current_world = unreal.EditorLevelLibrary.get_editor_world()
        current_path = current_world.get_path_name() if current_world else ""
        if current_path.startswith(f"{CODEX_LEVEL_DIR}/"):
            unreal.log_warning("[UAT] Skipping Codex level delete because the map is currently loaded.")
            return

        if unreal.EditorAssetLibrary.does_directory_exist(CODEX_LEVEL_DIR):
            unreal.EditorAssetLibrary.delete_directory(CODEX_LEVEL_DIR)
        unreal.EditorAssetLibrary.make_directory(CODEX_LEVEL_DIR)
        log("Cleared Codex levels directory")
    except Exception as exc:
        unreal.log_error(f"[UAT] Failed to clear Codex levels: {exc}")

def make_directory(path):
    unreal.EditorAssetLibrary.make_directory(path)

def set_directional_light(actor, intensity, color):
    comp = actor.get_component_by_class(unreal.DirectionalLightComponent)
    if comp:
        comp.set_editor_property("intensity", intensity)
        try:
            comp.set_light_color(color, True)
        except Exception:
            comp.set_editor_property("light_color", color.to_fcolor(True))

def set_light_color_safe(light_comp, color, use_srgb=True):
    try:
        if hasattr(light_comp, "set_light_color"):
            light_comp.set_light_color(color, use_srgb)
            return
        light_comp.set_editor_property("light_color", color.to_fcolor(use_srgb))
    except Exception:
        pass

def add_common_lighting(sun_color, sun_intensity, sky_intensity=1.0):
    sun = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0.0, 0.0, 400.0))
    sun.set_actor_rotation(unreal.Rotator(-45.0, 35.0, 0.0), teleport_physics=True)
    set_directional_light(sun, sun_intensity, sun_color)

    sky = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0.0, 0.0, 0.0))
    sky_comp = sky.get_component_by_class(unreal.SkyLightComponent)
    if sky_comp:
        try:
            sky_comp.set_editor_property("intensity", sky_intensity)
        except Exception:
            pass

    unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0.0, 0.0, 0.0))

def make_ground(material, scale=20.0, location=None):
    plane = unreal.EditorAssetLibrary.load_asset(PLANE_MESH_PATH)
    if not plane:
        unreal.log_error(f"[UAT] Plane mesh not found: {PLANE_MESH_PATH}")
        return None
    loc = location or unreal.Vector(0.0, 0.0, 0.0)
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, loc)
    comp = actor.get_component_by_class(unreal.StaticMeshComponent)
    comp.set_static_mesh(plane)
    comp.set_world_scale3d(unreal.Vector(scale, scale, 1.0))
    if material:
        comp.set_material(0, material)
    return actor

def create_level_with_builder(name, builder_fn):
    make_directory(CODEX_LEVEL_DIR)
    level_path = f"{CODEX_LEVEL_DIR}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(level_path):
        unreal.EditorAssetLibrary.delete_asset(level_path)
    level_world = unreal.EditorLevelLibrary.new_level(level_path)
    if not level_world:
        unreal.log_error(f"[UAT] Failed to create level {level_path}")
        return
    try:
        builder_fn()
    except Exception as exc:
        unreal.log_error(f"[UAT] Builder failed for {level_path}: {exc}")
        unreal.EditorLevelLibrary.save_current_level()
        return
    unreal.EditorLevelLibrary.save_current_level()
    actor_count = len(unreal.EditorLevelLibrary.get_all_level_actors() or [])
    log(f"Built level {level_path} (actors: {actor_count})")

def build_desert_level():
    sand = ensure_material("M_UAT_Sand", unreal.LinearColor(0.9, 0.7, 0.45, 1.0))
    add_common_lighting(unreal.LinearColor(1.0, 0.9, 0.75, 1.0), 10.0, sky_intensity=1.2)
    make_ground(sand, scale=24.0)
    # dunes: scattered scaled spheres
    for i in range(8):
        offset = unreal.Vector(random.uniform(-800.0, 800.0), random.uniform(-800.0, 800.0), -10.0)
        dune = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, offset)
        mesh = unreal.EditorAssetLibrary.load_asset(SPHERE_MESH_PATH)
        comp = dune.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(mesh)
        comp.set_material(0, sand)
        scale = random.uniform(3.0, 7.0)
        comp.set_world_scale3d(unreal.Vector(scale, scale, 0.8 * scale))
        dune.set_actor_label(f"Dune_{i}")

def build_forest_level():
    grass_mat = ensure_lifelike_grass_material()
    add_common_lighting(unreal.LinearColor(1.0, 0.98, 0.9, 1.0), 7.0, sky_intensity=1.5)
    make_ground(grass_mat, scale=18.0)
    center = unreal.Vector(0.0, 0.0, 0.0)
    spawn_grass_field_instanced(
        center + unreal.Vector(0.0, 0.0, -5.0),
        grass_mat,
        rows=28,
        cols=28,
        spacing_cm=LIFELIKE_GRASS_SPACING_CM
    )
    # scatter trees using cylinders + spheres as canopies
    trunk_mat = ensure_material("M_UAT_Trunk", unreal.LinearColor(0.25, 0.12, 0.06, 1.0))
    leaf_mat = ensure_material("M_UAT_Leaf", unreal.LinearColor(0.1, 0.4, 0.12, 1.0))
    cylinder = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cylinder.Cylinder")
    sphere = unreal.EditorAssetLibrary.load_asset(SPHERE_MESH_PATH)
    for i in range(20):
        loc = unreal.Vector(random.uniform(-900.0, 900.0), random.uniform(-900.0, 900.0), 0.0)
        trunk = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, loc)
        ccomp = trunk.get_component_by_class(unreal.StaticMeshComponent)
        ccomp.set_static_mesh(cylinder)
        ccomp.set_material(0, trunk_mat)
        ccomp.set_world_scale3d(unreal.Vector(0.3, 0.3, 4.0))
        canopy = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, loc + unreal.Vector(0.0, 0.0, 300.0))
        scomp = canopy.get_component_by_class(unreal.StaticMeshComponent)
        scomp.set_static_mesh(sphere)
        scomp.set_material(0, leaf_mat)
        scomp.set_world_scale3d(unreal.Vector(1.8, 1.8, 1.6))
        canopy.set_actor_label(f"Tree_{i}")

def build_neon_level():
    neon_floor = ensure_emissive_material("M_UAT_NeonFloor", unreal.LinearColor(0.05, 0.9, 0.8, 1.0), emissive_boost=8.0)
    neon_pillar = ensure_emissive_material("M_UAT_NeonPillar", unreal.LinearColor(0.8, 0.2, 1.0, 1.0), emissive_boost=12.0)
    add_common_lighting(unreal.LinearColor(0.6, 0.8, 1.0, 1.0), 4.0, sky_intensity=0.6)
    make_ground(neon_floor, scale=16.0)
    cylinder = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cylinder.Cylinder")
    positions = [
        unreal.Vector(400.0, 400.0, 0.0),
        unreal.Vector(-400.0, 400.0, 0.0),
        unreal.Vector(400.0, -400.0, 0.0),
        unreal.Vector(-400.0, -400.0, 0.0),
        unreal.Vector(0.0, 0.0, 0.0)
    ]
    for i, pos in enumerate(positions):
        pillar = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, pos)
        comp = pillar.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(cylinder)
        comp.set_material(0, neon_pillar)
        comp.set_world_scale3d(unreal.Vector(0.6, 0.6, 8.0))
        pillar.set_actor_label(f"NeonPillar_{i}")
        light = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.PointLight, pos + unreal.Vector(0.0, 0.0, 300.0))
        lcomp = light.get_component_by_class(unreal.PointLightComponent)
        if lcomp:
            lcomp.set_editor_property("intensity", 8000.0)
            lcomp.set_editor_property("light_color", unreal.LinearColor(0.8, 0.2, 1.0, 1.0))

def build_snow_level():
    snow = ensure_material("M_UAT_Snow", unreal.LinearColor(0.92, 0.95, 1.0, 1.0))
    add_common_lighting(unreal.LinearColor(0.8, 0.9, 1.0, 1.0), 7.0, sky_intensity=1.8)
    make_ground(snow, scale=18.0)
    cone = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cone.Cone")
    for i in range(16):
        loc = unreal.Vector(random.uniform(-900.0, 900.0), random.uniform(-900.0, 900.0), -10.0)
        ice = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, loc)
        comp = ice.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(cone)
        comp.set_material(0, snow)
        scale = random.uniform(2.0, 5.0)
        comp.set_world_scale3d(unreal.Vector(scale, scale, scale * 2.5))
        ice.set_actor_label(f"Ice_{i}")

def build_volcano_level():
    rock = ensure_material("M_UAT_Rock", unreal.LinearColor(0.15, 0.1, 0.1, 1.0))
    lava = ensure_emissive_material("M_UAT_Lava", unreal.LinearColor(1.0, 0.25, 0.05, 1.0), emissive_boost=10.0)
    add_common_lighting(unreal.LinearColor(1.0, 0.6, 0.4, 1.0), 6.0, sky_intensity=0.8)
    make_ground(rock, scale=18.0)
    # lava pools
    for i in range(5):
        loc = unreal.Vector(random.uniform(-700.0, 700.0), random.uniform(-700.0, 700.0), -5.0)
        pool = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, loc)
        comp = pool.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(unreal.EditorAssetLibrary.load_asset(PLANE_MESH_PATH))
        comp.set_world_scale3d(unreal.Vector(random.uniform(2.0, 4.0), random.uniform(2.0, 4.0), 1.0))
        comp.set_material(0, lava)
    # rocks
    sphere = unreal.EditorAssetLibrary.load_asset(SPHERE_MESH_PATH)
    for i in range(10):
        loc = unreal.Vector(random.uniform(-800.0, 800.0), random.uniform(-800.0, 800.0), 0.0)
        rock_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, loc)
        comp = rock_actor.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(sphere)
        comp.set_material(0, rock)
        scale = random.uniform(2.0, 5.0)
        comp.set_world_scale3d(unreal.Vector(scale, scale, scale))

def build_city_grid_level():
    pavement = ensure_material("M_UAT_Pavement", unreal.LinearColor(0.2, 0.2, 0.22, 1.0))
    glass = ensure_emissive_material("M_UAT_GlassGlow", unreal.LinearColor(0.2, 0.6, 1.0, 1.0), emissive_boost=6.0)
    add_common_lighting(unreal.LinearColor(1.0, 0.95, 0.85, 1.0), 8.0, sky_intensity=1.2)
    make_ground(pavement, scale=20.0)
    cube = unreal.EditorAssetLibrary.load_asset(CUBE_MESH_PATH)
    for x in range(-2, 3):
        for y in range(-2, 3):
            loc = unreal.Vector(x * 400.0, y * 400.0, 0.0)
            b = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, loc)
            comp = b.get_component_by_class(unreal.StaticMeshComponent)
            comp.set_static_mesh(cube)
            comp.set_world_scale3d(unreal.Vector(2.0, 2.0, random.uniform(4.0, 9.0)))
            comp.set_material(0, glass if (x + y) % 2 == 0 else pavement)
            b.set_actor_label(f"Tower_{x}_{y}")

def build_canyon_level():
    canyon = ensure_material("M_UAT_Canyon", unreal.LinearColor(0.55, 0.32, 0.2, 1.0))
    add_common_lighting(unreal.LinearColor(1.0, 0.8, 0.6, 1.0), 9.0, sky_intensity=1.1)
    make_ground(canyon, scale=22.0)
    cube = unreal.EditorAssetLibrary.load_asset(CUBE_MESH_PATH)
    for i in range(10):
        loc = unreal.Vector(random.uniform(-900.0, 900.0), random.uniform(-900.0, 900.0), -50.0)
        wall = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, loc)
        comp = wall.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(cube)
        comp.set_material(0, canyon)
        comp.set_world_scale3d(unreal.Vector(random.uniform(4.0, 12.0), random.uniform(1.5, 3.0), random.uniform(5.0, 10.0)))

def build_sky_islands_level():
    rock = ensure_material("M_UAT_IslandRock", unreal.LinearColor(0.3, 0.28, 0.26, 1.0))
    grass = ensure_material("M_UAT_IslandGrass", unreal.LinearColor(0.2, 0.6, 0.2, 1.0))
    add_common_lighting(unreal.LinearColor(0.9, 1.0, 1.0, 1.0), 8.0, sky_intensity=1.6)
    cube = unreal.EditorAssetLibrary.load_asset(CUBE_MESH_PATH)
    sphere = unreal.EditorAssetLibrary.load_asset(SPHERE_MESH_PATH)
    offsets = [
        unreal.Vector(0.0, 0.0, 0.0),
        unreal.Vector(800.0, 200.0, 300.0),
        unreal.Vector(-700.0, -300.0, 250.0),
        unreal.Vector(200.0, -900.0, 200.0)
    ]
    for i, off in enumerate(offsets):
        island = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, off)
        comp = island.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(cube)
        comp.set_material(0, rock)
        comp.set_world_scale3d(unreal.Vector(6.0, 6.0, 1.2))
        cap = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, off + unreal.Vector(0.0, 0.0, 150.0))
        scomp = cap.get_component_by_class(unreal.StaticMeshComponent)
        scomp.set_static_mesh(sphere)
        scomp.set_material(0, grass)
        scomp.set_world_scale3d(unreal.Vector(4.5, 4.5, 0.5))
        cap.set_actor_label(f"Island_{i}")
        light = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.PointLight, off + unreal.Vector(0.0, 0.0, 500.0))
        lcomp = light.get_component_by_class(unreal.PointLightComponent)
        if lcomp:
            lcomp.set_editor_property("intensity", 12000.0)
            lcomp.set_editor_property("light_color", unreal.LinearColor(0.9, 0.95, 1.0, 1.0))

def build_checker_level():
    dark = ensure_material("M_UAT_CheckDark", unreal.LinearColor(0.1, 0.1, 0.1, 1.0))
    light = ensure_material("M_UAT_CheckLight", unreal.LinearColor(0.9, 0.9, 0.9, 1.0))
    add_common_lighting(unreal.LinearColor(1.0, 1.0, 1.0, 1.0), 7.0, sky_intensity=1.5)
    plane = unreal.EditorAssetLibrary.load_asset(PLANE_MESH_PATH)
    size = 400.0
    for r in range(-3, 4):
        for c in range(-3, 4):
            tile = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(r * size, c * size, 0.0))
            comp = tile.get_component_by_class(unreal.StaticMeshComponent)
            comp.set_static_mesh(plane)
            comp.set_world_scale3d(unreal.Vector(1.5, 1.5, 1.0))
            comp.set_material(0, light if (r + c) % 2 == 0 else dark)

def build_ruins_level():
    stone = ensure_material("M_UAT_Stone", unreal.LinearColor(0.45, 0.45, 0.42, 1.0))
    moss = ensure_material("M_UAT_Moss", unreal.LinearColor(0.18, 0.35, 0.2, 1.0))
    add_common_lighting(unreal.LinearColor(1.0, 0.95, 0.9, 1.0), 8.0, sky_intensity=1.3)
    make_ground(moss, scale=20.0)
    cylinder = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cylinder.Cylinder")
    cube = unreal.EditorAssetLibrary.load_asset(CUBE_MESH_PATH)
    for i in range(12):
        loc = unreal.Vector(random.uniform(-800.0, 800.0), random.uniform(-800.0, 800.0), 0.0)
        col = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, loc)
        comp = col.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(cylinder)
        comp.set_material(0, stone)
        comp.set_world_scale3d(unreal.Vector(0.6, 0.6, random.uniform(3.0, 6.0)))
    for i in range(10):
        rubble = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(random.uniform(-700.0, 700.0), random.uniform(-700.0, 700.0), 0.0))
        comp = rubble.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(cube)
        comp.set_material(0, stone)
        comp.set_world_scale3d(unreal.Vector(random.uniform(0.8, 2.5), random.uniform(0.6, 2.0), random.uniform(0.3, 1.5)))

def build_chromatic_level():
    stripe_a = ensure_emissive_material("M_UAT_ChromaticA", unreal.LinearColor(1.0, 0.2, 0.4, 1.0), emissive_boost=8.0)
    stripe_b = ensure_emissive_material("M_UAT_ChromaticB", unreal.LinearColor(0.2, 0.6, 1.0, 1.0), emissive_boost=8.0)
    add_common_lighting(unreal.LinearColor(0.9, 0.9, 1.0, 1.0), 5.0, sky_intensity=0.8)
    plane = unreal.EditorAssetLibrary.load_asset(PLANE_MESH_PATH)
    for i in range(-5, 6):
        strip = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(i * 300.0, 0.0, 0.0))
        comp = strip.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(plane)
        comp.set_world_scale3d(unreal.Vector(1.0, 10.0, 1.0))
        comp.set_material(0, stripe_a if i % 2 == 0 else stripe_b)
        light = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.PointLight, unreal.Vector(i * 300.0, 0.0, 400.0))
        lcomp = light.get_component_by_class(unreal.PointLightComponent)
        if lcomp:
            lcomp.set_editor_property("intensity", 12000.0)

def build_crystal_level():
    crystal = ensure_emissive_material("M_UAT_Crystal", unreal.LinearColor(0.3, 0.9, 1.0, 1.0), emissive_boost=10.0)
    base = ensure_material("M_UAT_CrystalBase", unreal.LinearColor(0.05, 0.08, 0.1, 1.0))
    add_common_lighting(unreal.LinearColor(0.8, 0.9, 1.0, 1.0), 6.0, sky_intensity=1.0)
    make_ground(base, scale=18.0)
    cone = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cone.Cone")
    for i in range(18):
        loc = unreal.Vector(random.uniform(-800.0, 800.0), random.uniform(-800.0, 800.0), 0.0)
        c = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, loc)
        comp = c.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(cone)
        comp.set_material(0, crystal)
        scale = random.uniform(2.0, 6.0)
        comp.set_world_scale3d(unreal.Vector(scale * 0.6, scale * 0.6, scale * 2.5))
        c.set_actor_rotation(unreal.Rotator(-90.0, random.uniform(0.0, 360.0), 0.0), teleport_physics=True)

def build_industrial_level():
    metal = ensure_material("M_UAT_Metal", unreal.LinearColor(0.35, 0.37, 0.4, 1.0))
    accent = ensure_emissive_material("M_UAT_Accent", unreal.LinearColor(1.0, 0.6, 0.1, 1.0), emissive_boost=6.0)
    add_common_lighting(unreal.LinearColor(1.0, 0.95, 0.9, 1.0), 7.0, sky_intensity=1.0)
    make_ground(metal, scale=18.0)
    cylinder = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cylinder.Cylinder")
    cube = unreal.EditorAssetLibrary.load_asset(CUBE_MESH_PATH)
    for i in range(8):
        loc = unreal.Vector(i * 250.0 - 900.0, -600.0, 0.0)
        pipe = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, loc)
        comp = pipe.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(cylinder)
        comp.set_material(0, metal)
        comp.set_world_scale3d(unreal.Vector(0.8, 0.8, 6.0))
    for i in range(6):
        box = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(i * 300.0 - 750.0, 400.0, 0.0))
        comp = box.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(cube)
        comp.set_material(0, metal if i % 2 == 0 else accent)
        comp.set_world_scale3d(unreal.Vector(2.0, 2.0, random.uniform(2.0, 5.0)))

def build_scifi_landscape_level():
    log("Scifi build: start")
    try:
        _stop_move_tick()
        _moving_actors.clear()
        global _move_time_accum, _move_debug_counter
        _move_time_accum = 0.0
        _move_debug_counter = 0
        _build_scifi_landscape_level_impl()
    except Exception as exc:
        unreal.log_error(f"[UAT] Scifi build failed: {exc}")
        return

def _ensure_move_tick():
    global _move_tick_handle
    if _move_tick_handle is None:
        log("Registering move tick")
        _move_tick_handle = unreal.register_slate_post_tick_callback(_move_tick)

def _push_moving(actor, velocity, meta=None):
    global _moving_actors
    if actor is None:
        return
    vel = unreal.Vector(velocity.x, velocity.y, velocity.z)
    _moving_actors.append((actor, vel, meta))
    _ensure_move_tick()

def _spawn_moving_actor(mesh, material, start, velocity, scale, label, meta=None):
    if not mesh:
        unreal.log_error(f"[UAT] Missing mesh for {label}")
        return None
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, start)
    comp = actor.get_component_by_class(unreal.StaticMeshComponent)
    comp.set_static_mesh(mesh)
    comp.set_world_scale3d(scale)
    if material:
        comp.set_material(0, material)
    actor.set_actor_label(label)
    _push_moving(actor, velocity, meta)
    return actor

def _spawn_moving_light(start, velocity, intensity, color_a, color_b=None, hue_speed=0.5, attenuation=1800.0, label=None):
    light = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.PointLight, start)
    lcomp = light.get_component_by_class(unreal.PointLightComponent)
    if lcomp:
        lcomp.set_editor_property("intensity", intensity)
        lcomp.set_editor_property("attenuation_radius", attenuation)
        set_light_color_safe(lcomp, color_a)
    meta = {
        "light_comp": lcomp,
        "base_intensity": intensity,
        "color_a": color_a,
        "color_b": color_b or color_a,
        "phase": random.uniform(0.0, math.pi * 2.0),
        "hue_speed": hue_speed,
    }
    if label:
        light.set_actor_label(label)
    _push_moving(light, velocity, meta)
    return light

def _spawn_text_label(location, text, color=unreal.LinearColor(1.0, 1.0, 1.0, 1.0), size=48.0):
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.TextRenderActor, location)
    comp = actor.get_component_by_class(unreal.TextRenderComponent)
    if comp:
        comp.set_editor_property("text", text)
        comp.set_editor_property("text_render_color", color.to_fcolor(True))
        comp.set_editor_property("horizontal_alignment", unreal.HorizTextAligment.HTA_CENTER)
        comp.set_editor_property("vertical_alignment", unreal.VertTextAligment.VTA_TextCenter)
        comp.set_editor_property("world_size", size)
    return actor

def _find_actor_by_label(label):
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        if actor and actor.get_actor_label() == label:
            return actor
    return None

def _set_folder(actor, folder_name):
    try:
        actor.set_folder_path(unreal.Name(folder_name))
    except Exception:
        pass

def _spawn_reference_showcase(base_loc, cyan, magenta, base_mat):
    """Place representative assets with labels for quick visual selection."""
    plane = unreal.EditorAssetLibrary.load_asset(PLANE_MESH_PATH)
    cube = unreal.EditorAssetLibrary.load_asset(CUBE_MESH_PATH)
    sphere = unreal.EditorAssetLibrary.load_asset(SPHERE_MESH_PATH)

    if not plane or not cube or not sphere:
        unreal.log_warning("[UAT] Showcase skipped; missing primitive mesh")
        return

    car_mat = ensure_emissive_material("M_UAT_Scifi_Car", unreal.LinearColor(0.1, 0.8, 1.0, 1.0), emissive_boost=14.0)
    drone_mat = ensure_emissive_material("M_UAT_Scifi_Drone", unreal.LinearColor(0.0, 0.9, 0.8, 1.0), emissive_boost=10.0)

    # Ground pad
    pad = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, base_loc)
    pcomp = pad.get_component_by_class(unreal.StaticMeshComponent)
    pcomp.set_static_mesh(plane)
    pcomp.set_world_scale3d(unreal.Vector(6.0, 6.0, 1.0))
    pcomp.set_material(0, base_mat)
    pad.set_actor_label("Showcase_Pad")

    offsets = {
        "Tower": unreal.Vector(-350.0, -200.0, 0.0),
        "Sign": unreal.Vector(0.0, -200.0, 0.0),
        "Bridge": unreal.Vector(350.0, -200.0, 0.0),
        "Car": unreal.Vector(-200.0, 200.0, 0.0),
        "Drone": unreal.Vector(0.0, 200.0, 0.0),
        "Roaming Light": unreal.Vector(200.0, 200.0, 0.0),
    }

    # Tower sample
    tpos = base_loc + offsets["Tower"]
    tower = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, tpos)
    tcomp = tower.get_component_by_class(unreal.StaticMeshComponent)
    tcomp.set_static_mesh(cube)
    tcomp.set_material(0, base_mat)
    tcomp.set_world_scale3d(unreal.Vector(1.2, 1.0, 8.0))
    strip = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, tpos + unreal.Vector(0.0, 90.0, 300.0))
    scomp = strip.get_component_by_class(unreal.StaticMeshComponent)
    scomp.set_static_mesh(cube)
    scomp.set_material(0, cyan)
    scomp.set_world_scale3d(unreal.Vector(0.12, 0.35, 4.0))
    _spawn_text_label(tpos + unreal.Vector(0.0, 0.0, 500.0), "Tower")

    # Sign sample
    spos = base_loc + offsets["Sign"]
    sign = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, spos)
    sc = sign.get_component_by_class(unreal.StaticMeshComponent)
    sc.set_static_mesh(plane)
    sc.set_world_scale3d(unreal.Vector(1.8, 0.2, 1.0))
    sc.set_material(0, magenta)
    sign.set_actor_rotation(unreal.Rotator(0.0, 20.0, 0.0), teleport_physics=True)
    _spawn_text_label(spos + unreal.Vector(0.0, 0.0, 220.0), "Sign / Billboard", color=unreal.LinearColor(1.0, 0.2, 0.8, 1.0))

    # Bridge sample
    bpos = base_loc + offsets["Bridge"]
    bridge = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, bpos)
    bcomp = bridge.get_component_by_class(unreal.StaticMeshComponent)
    bcomp.set_static_mesh(plane)
    bcomp.set_material(0, base_mat)
    bcomp.set_world_scale3d(unreal.Vector(3.2, 0.5, 0.2))
    rail = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, bpos + unreal.Vector(0.0, 0.0, 40.0))
    rcomp = rail.get_component_by_class(unreal.StaticMeshComponent)
    rcomp.set_static_mesh(plane)
    rcomp.set_material(0, cyan)
    rcomp.set_world_scale3d(unreal.Vector(3.2, 0.08, 0.1))
    _spawn_text_label(bpos + unreal.Vector(0.0, 0.0, 180.0), "Bridge / Highway")

    # Car sample (moving)
    car_pos = base_loc + offsets["Car"]
    car_vel = unreal.Vector(260.0, 0.0, 0.0)
    _spawn_moving_actor(plane, car_mat, car_pos, car_vel, unreal.Vector(0.9, 2.6, 0.32), "Showcase_Car")
    _spawn_moving_light(car_pos + unreal.Vector(0.0, 0.0, 40.0), car_vel, 5200.0, unreal.LinearColor(0.2, 0.9, 1.0, 1.0), unreal.LinearColor(1.0, 0.3, 0.2, 1.0), hue_speed=0.7, attenuation=1000.0, label="Showcase_CarLight")
    _spawn_text_label(car_pos + unreal.Vector(0.0, 0.0, 200.0), "Car (moving)")

    # Drone sample (moving)
    drone_pos = base_loc + offsets["Drone"] + unreal.Vector(0.0, 0.0, 120.0)
    drone_vel = unreal.Vector(-160.0, 120.0, 40.0)
    _spawn_moving_actor(sphere, drone_mat, drone_pos, drone_vel, unreal.Vector(0.55, 0.55, 0.55), "Showcase_Drone")
    _spawn_moving_light(drone_pos + unreal.Vector(0.0, 0.0, 70.0), drone_vel, 4500.0, unreal.LinearColor(0.0, 0.9, 0.8, 1.0), unreal.LinearColor(1.0, 0.25, 0.7, 1.0), hue_speed=1.0, attenuation=800.0, label="Showcase_DroneLight")
    _spawn_text_label(drone_pos + unreal.Vector(0.0, 0.0, 180.0), "Drone (moving)")

    # Roaming light sample (moving)
    rl_pos = base_loc + offsets["Roaming Light"] + unreal.Vector(0.0, 0.0, 80.0)
    rl_vel = unreal.Vector(120.0, -160.0, 30.0)
    _spawn_moving_light(rl_pos, rl_vel, 4200.0, unreal.LinearColor(0.05, 0.8, 1.0, 1.0), unreal.LinearColor(1.0, 0.2, 0.65, 1.0), hue_speed=0.8, attenuation=1100.0, label="Showcase_RoamLight")
    _spawn_text_label(rl_pos + unreal.Vector(0.0, 0.0, 160.0), "Roaming Light (moving)")

def spawn_debug_showcase():
    """Spawn a car, drone, and roaming light in front of the viewport with labels to verify movement."""
    global _moving_actors
    _stop_move_tick()
    _moving_actors.clear()

    cam_loc = unreal.Vector(0.0, 0.0, 200.0)
    cam_rot = unreal.Rotator(0.0, 0.0, 0.0)
    try:
        loc_out = unreal.Vector()
        rot_out = unreal.Rotator()
        fov = 0.0
        unreal.EditorLevelLibrary.get_level_viewport_camera_info(loc_out, rot_out, fov)
        cam_loc = loc_out
        cam_rot = rot_out
    except Exception:
        pass

    forward = cam_rot.get_forward_vector()
    right = cam_rot.get_right_vector()
    up = unreal.Vector(0.0, 0.0, 1.0)
    base = cam_loc + forward * 800.0 + up * 50.0

    # Car
    car_pos = base + right * -200.0
    car_vel = unreal.Vector(400.0, 0.0, 0.0)
    car_mat = ensure_emissive_material("M_UAT_Scifi_Car", unreal.LinearColor(0.1, 0.8, 1.0, 1.0), emissive_boost=14.0)
    plane = unreal.EditorAssetLibrary.load_asset(PLANE_MESH_PATH)
    _spawn_moving_actor(plane, car_mat, car_pos, car_vel, unreal.Vector(0.9, 2.8, 0.35), "Debug_Car")
    _spawn_moving_light(car_pos + unreal.Vector(0.0, 0.0, 40.0), car_vel, 6000.0, unreal.LinearColor(0.2, 0.9, 1.0, 1.0), unreal.LinearColor(1.0, 0.3, 0.2, 1.0), hue_speed=0.8, attenuation=1200.0, label="Debug_CarLight")
    _spawn_text_label(car_pos + unreal.Vector(0.0, 0.0, 200.0), "Car")

    # Drone
    drone_pos = base + right * 0.0 + up * 150.0
    drone_vel = unreal.Vector(-220.0, 120.0, 60.0)
    drone_mat = ensure_emissive_material("M_UAT_Scifi_Drone", unreal.LinearColor(0.0, 0.9, 0.8, 1.0), emissive_boost=10.0)
    sphere = unreal.EditorAssetLibrary.load_asset(SPHERE_MESH_PATH)
    _spawn_moving_actor(sphere, drone_mat, drone_pos, drone_vel, unreal.Vector(0.6, 0.6, 0.6), "Debug_Drone")
    _spawn_moving_light(drone_pos + unreal.Vector(0.0, 0.0, 70.0), drone_vel, 5200.0, unreal.LinearColor(0.0, 0.9, 0.8, 1.0), unreal.LinearColor(1.0, 0.2, 0.7, 1.0), hue_speed=1.0, attenuation=900.0, label="Debug_DroneLight")
    _spawn_text_label(drone_pos + unreal.Vector(0.0, 0.0, 200.0), "Drone")

    # Roaming light
    roam_pos = base + right * 200.0 + up * 80.0
    roam_vel = unreal.Vector(150.0, -180.0, 40.0)
    _spawn_moving_light(roam_pos, roam_vel, 4800.0, unreal.LinearColor(0.05, 0.8, 1.0, 1.0), unreal.LinearColor(1.0, 0.2, 0.65, 1.0), hue_speed=0.7, attenuation=1200.0, label="Debug_RoamLight")
    _spawn_text_label(roam_pos + unreal.Vector(0.0, 0.0, 200.0), "Roaming Light")

    log(f"Debug showcase spawned. Moving actors={len(_moving_actors)}")

def stop_motion():
    """Clear moving actors and stop move tick."""
    global _moving_actors
    _moving_actors.clear()
    _stop_move_tick()
    log("Stopped move tick and cleared moving actors")

def spawn_marker_near_camera():
    """Spawn a large red sphere marker near the current viewport camera."""
    sphere = unreal.EditorAssetLibrary.load_asset(SPHERE_MESH_PATH)
    red_mat = ensure_emissive_material("M_UAT_Test_Red", unreal.LinearColor(1.0, 0.1, 0.1, 1.0), emissive_boost=6.0)
    cam_loc = unreal.Vector(0.0, 0.0, 200.0)
    cam_rot = unreal.Rotator(0.0, 0.0, 0.0)
    try:
        loc_out = unreal.Vector()
        rot_out = unreal.Rotator()
        fov = 0.0
        unreal.EditorLevelLibrary.get_level_viewport_camera_info(loc_out, rot_out, fov)
        cam_loc = loc_out
        cam_rot = rot_out
    except Exception:
        pass

    forward = cam_rot.get_forward_vector()
    spawn_loc = cam_loc + forward * 600.0 + unreal.Vector(0.0, 0.0, 80.0)
    marker = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, spawn_loc)
    comp = marker.get_component_by_class(unreal.StaticMeshComponent)
    if sphere:
        comp.set_static_mesh(sphere)
    comp.set_world_scale3d(unreal.Vector(2.5, 2.5, 2.5))
    if red_mat:
        comp.set_material(0, red_mat)
    marker.set_actor_label("Line_Marker_RedBall")
    _set_folder(marker, "Showcase")
    _spawn_text_label(spawn_loc + unreal.Vector(0.0, 0.0, 220.0), "Marker")
    log(f"Spawned marker at {spawn_loc}")

def setup_overview_plane():
    """Decorate ov_plane and overview_cube*/ov_text* with labels and lights."""
    cyan = ensure_emissive_material("M_UAT_Scifi_Cyan", unreal.LinearColor(0.0, 0.75, 1.0, 1.0), emissive_boost=12.0)
    magenta = ensure_emissive_material("M_UAT_Scifi_Magenta", unreal.LinearColor(1.0, 0.1, 0.65, 1.0), emissive_boost=12.0)
    base_mat = ensure_material("M_UAT_Scifi_Base", unreal.LinearColor(0.05, 0.08, 0.12, 1.0))

    plane_actor = _find_actor_by_label("ov_plane")
    if plane_actor:
        comp = plane_actor.get_component_by_class(unreal.StaticMeshComponent)
        if comp:
            comp.set_material(0, base_mat)

    labels = [
        "Tower", "Sign / Billboard", "Bridge / Highway", "Car",
        "Drone", "Roaming Light", "Showcase", "Placeholder"
    ]
    text_color = unreal.LinearColor(1.0, 0.95, 0.8, 1.0)

    for i in range(8):
        cube = _find_actor_by_label(f"overview_cube{i+1}")
        text = _find_actor_by_label(f"ov_text{i+1}")
        label = labels[i] if i < len(labels) else f"Item {i+1}"
        if cube:
            ccomp = cube.get_component_by_class(unreal.StaticMeshComponent)
            if ccomp:
                mat = cyan if i % 2 == 0 else magenta
                ccomp.set_material(0, mat)
            loc = cube.get_actor_location()
            light = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.PointLight, loc + unreal.Vector(0.0, 0.0, 120.0))
            lcomp = light.get_component_by_class(unreal.PointLightComponent)
            if lcomp:
                lcomp.set_editor_property("intensity", 4200.0)
                lcomp.set_editor_property("attenuation_radius", 900.0)
                set_light_color_safe(lcomp, unreal.LinearColor(1.0, 0.8, 0.6, 1.0))
            if text:
                tcomp = text.get_component_by_class(unreal.TextRenderComponent)
                if tcomp:
                    tcomp.set_editor_property("text", label)
                    tcomp.set_editor_property("text_render_color", text_color.to_fcolor(True))
                    tcomp.set_editor_property("world_size", 48.0)
                text.set_actor_location(loc + unreal.Vector(0.0, 0.0, 220.0), teleport=True)
            else:
                _spawn_text_label(loc + unreal.Vector(0.0, 0.0, 220.0), label, color=text_color, size=48.0)

    log("Overview plane decorated with labels, lights, and materials.")

def spawn_asset_line(base_loc, step=unreal.Vector(0.0, 400.0, 0.0)):
    """Place one static sample of each major asset type with labels (no animation)."""
    plane = unreal.EditorAssetLibrary.load_asset(PLANE_MESH_PATH)
    cube = unreal.EditorAssetLibrary.load_asset(CUBE_MESH_PATH)
    sphere = unreal.EditorAssetLibrary.load_asset(SPHERE_MESH_PATH)
    base_mat = ensure_material("M_UAT_Scifi_Base", unreal.LinearColor(0.05, 0.08, 0.12, 1.0))
    cyan = ensure_emissive_material("M_UAT_Scifi_Cyan", unreal.LinearColor(0.0, 0.75, 1.0, 1.0), emissive_boost=12.0)
    magenta = ensure_emissive_material("M_UAT_Scifi_Magenta", unreal.LinearColor(1.0, 0.1, 0.65, 1.0), emissive_boost=12.0)
    car_mat = ensure_emissive_material("M_UAT_Scifi_Car", unreal.LinearColor(0.1, 0.8, 1.0, 1.0), emissive_boost=14.0)
    drone_mat = ensure_emissive_material("M_UAT_Scifi_Drone", unreal.LinearColor(0.0, 0.9, 0.8, 1.0), emissive_boost=10.0)

    items = [
        ("Tower", cube, base_mat, unreal.Vector(1.6, 1.2, 9.0)),
        ("Bridge / Highway", plane, base_mat, unreal.Vector(3.2, 0.5, 0.2)),
        ("Sign / Billboard", plane, magenta, unreal.Vector(1.8, 0.2, 1.0)),
        ("Car", plane, car_mat, unreal.Vector(0.9, 2.6, 0.32)),
        ("Drone", sphere, drone_mat, unreal.Vector(0.55, 0.55, 0.55)),
        ("Light", None, None, None),
    ]

    for idx, (label, mesh, mat, scale) in enumerate(items):
        pos = base_loc + step * idx
        if label == "Light":
            light = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.PointLight, pos + unreal.Vector(0.0, 0.0, 140.0))
            lcomp = light.get_component_by_class(unreal.PointLightComponent)
            if lcomp:
                lcomp.set_editor_property("intensity", 4200.0)
                lcomp.set_editor_property("attenuation_radius", 900.0)
                set_light_color_safe(lcomp, unreal.LinearColor(0.8, 0.7, 0.6, 1.0))
            light.set_actor_label("Line_Light")
            _set_folder(light, "Showcase")
            _spawn_text_label(pos + unreal.Vector(0.0, 0.0, 240.0), label)
            continue
        if not mesh:
            continue
        actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, pos)
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(mesh)
        if scale:
            comp.set_world_scale3d(scale)
        if mat:
            comp.set_material(0, mat)
        actor.set_actor_label(f"Line_{label.replace(' ', '')}")
        _set_folder(actor, "Showcase")
        _spawn_text_label(pos + unreal.Vector(0.0, 0.0, 240.0), label)

    # Big red ball marker at start of line
    marker_pos = base_loc + unreal.Vector(-220.0, 0.0, 120.0)
    red_mat = ensure_emissive_material("M_UAT_Test_Red", unreal.LinearColor(1.0, 0.1, 0.1, 1.0), emissive_boost=6.0)
    marker = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, marker_pos)
    mcomp = marker.get_component_by_class(unreal.StaticMeshComponent)
    if sphere:
        mcomp.set_static_mesh(sphere)
    mcomp.set_world_scale3d(unreal.Vector(2.5, 2.5, 2.5))
    if red_mat:
        mcomp.set_material(0, red_mat)
    marker.set_actor_label("Line_Marker_RedBall")
    _set_folder(marker, "Showcase")
    _spawn_text_label(marker_pos + unreal.Vector(0.0, 0.0, 220.0), "Marker")

    log(f"Asset line spawned at {base_loc} with {len(items)} items.")

def organize_outliner():
    """Group scene actors into Outliner folders and parent vehicle lights."""
    actors = list(unreal.EditorLevelLibrary.get_all_level_actors() or [])
    label_map = {a.get_actor_label(): a for a in actors if a}

    def attach_light(light_label_prefix, target_label_prefix):
        for label, actor in label_map.items():
            if not label.startswith(light_label_prefix):
                continue
            suffix = label.removeprefix(light_label_prefix)
            target_label = f"{target_label_prefix}{suffix}"
            target = label_map.get(target_label)
            if target:
                try:
                    actor.attach_to_actor(target, unreal.AttachmentTransformRules.keep_world_transform)
                except Exception:
                    pass

    for actor in actors:
        if not actor:
            continue
        label = actor.get_actor_label()
        lname = label.lower()

        if lname.startswith("water") or "ground" in lname or "plane" in lname:
            _set_folder(actor, "Environment")
        elif isinstance(actor, unreal.DirectionalLight) or isinstance(actor, unreal.SkyLight) or isinstance(actor, unreal.ExponentialHeightFog):
            _set_folder(actor, "Environment")
        elif lname.startswith("scifitower") or "tower" in lname:
            _set_folder(actor, "Buildings")
        elif lname.startswith("bridge") or lname.startswith("highway"):
            _set_folder(actor, "Bridges_And_Highways")
        elif "sign" in lname or "billboard" in lname:
            _set_folder(actor, "Signs_And_Billboards")
        elif lname.startswith("car"):
            _set_folder(actor, "Vehicles")
        elif "drone" in lname:
            _set_folder(actor, "Drones")
        elif "movinglight" in lname or "glow" in lname:
            _set_folder(actor, "FX_Lights")
        elif lname.startswith("showcase") or lname.startswith("ov_") or lname.startswith("overview_"):
            _set_folder(actor, "Showcase")
        elif lname.startswith("debug") or lname.startswith("test"):
            _set_folder(actor, "Debug")
        else:
            # fallback buckets
            cls_name = actor.get_class().get_name().lower()
            if (
                isinstance(actor, unreal.PointLight)
                or isinstance(actor, unreal.SpotLight)
                or isinstance(actor, unreal.RectLight)
                or "light" in cls_name
            ):
                _set_folder(actor, "Misc_Lights")
            elif isinstance(actor, unreal.StaticMeshActor):
                _set_folder(actor, "Misc_StaticMesh")
            else:
                _set_folder(actor, "Misc_Uncategorized")

    attach_light("CarLight_", "Car_")
    attach_light("DroneLight_", "Drone_")

    log("Organized Outliner folders and parented vehicle lights.")

def lights_showcase_only():
    """Turn off all point/spot/rect lights except the lineup/showcase lights."""
    actors = list(unreal.EditorLevelLibrary.get_all_level_actors() or [])
    kept = 0
    off = 0
    for actor in actors:
        if not actor:
            continue
        label = actor.get_actor_label()
        cls = actor.get_class()
        cname = cls.get_name().lower() if cls else ""
        is_light = (
            isinstance(actor, unreal.PointLight) or
            isinstance(actor, unreal.SpotLight) or
            isinstance(actor, unreal.RectLight) or
            "light" in cname
        )
        if not is_light:
            continue
        keep = label.startswith("Line_") or label.startswith("Showcase_") or label.startswith("Debug_")
        comp = None
        if isinstance(actor, unreal.PointLight):
            comp = actor.get_component_by_class(unreal.PointLightComponent)
        elif isinstance(actor, unreal.SpotLight):
            comp = actor.get_component_by_class(unreal.SpotLightComponent)
        elif isinstance(actor, unreal.RectLight):
            comp = actor.get_component_by_class(unreal.RectLightComponent)
        if keep:
            kept += 1
            continue
        if comp:
            try:
                comp.set_editor_property("intensity", 0.0)
                comp.set_editor_property("visibility", False)
            except Exception:
                pass
        off += 1
    log(f"Lights limited to showcase: kept={kept}, turned_off={off}")

def _build_scifi_landscape_level_impl():
    towers_spawned = 0
    bridges_spawned = 0
    highways_spawned = 0
    signs_spawned = 0
    cars_spawned = 0
    drones_spawned = 0
    moving_lights_spawned = 0

    base = ensure_material("M_UAT_Scifi_Base", unreal.LinearColor(0.05, 0.08, 0.12, 1.0))
    cyan = ensure_emissive_material("M_UAT_Scifi_Cyan", unreal.LinearColor(0.0, 0.75, 1.0, 1.0), emissive_boost=12.0)
    red = ensure_emissive_material("M_UAT_Scifi_Red", unreal.LinearColor(1.0, 0.25, 0.1, 1.0), emissive_boost=10.0)
    magenta = ensure_emissive_material("M_UAT_Scifi_Magenta", unreal.LinearColor(1.0, 0.1, 0.65, 1.0), emissive_boost=12.0)
    cube = unreal.EditorAssetLibrary.load_asset(CUBE_MESH_PATH)
    plane = unreal.EditorAssetLibrary.load_asset(PLANE_MESH_PATH)
    sphere = unreal.EditorAssetLibrary.load_asset(SPHERE_MESH_PATH)
    if not cube or not plane or not sphere:
        unreal.log_error("[UAT] Missing cube/plane/sphere mesh; aborting build_scifi_landscape_level")
        return

    add_common_lighting(unreal.LinearColor(0.28, 0.55, 1.0, 1.0), 4.0, sky_intensity=1.0)
    make_ground(base, scale=95.0)

    # water plane under base for subtle reflections
    water = ensure_emissive_material("M_UAT_Scifi_Water", unreal.LinearColor(0.02, 0.15, 0.25, 1.0), emissive_boost=2.5)
    water_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0.0, 0.0, -10.0))
    wcomp = water_actor.get_component_by_class(unreal.StaticMeshComponent)
    wcomp.set_static_mesh(plane)
    wcomp.set_world_scale3d(unreal.Vector(85.0, 85.0, 1.0))
    wcomp.set_material(0, water)
    water_actor.set_actor_label("WaterPlane")

    # periphery billboards framing the skyline
    billboard_positions = [
        unreal.Vector(0.0, -2600.0, 420.0),
        unreal.Vector(-2600.0, 0.0, 440.0),
        unreal.Vector(2600.0, 0.0, 440.0),
        unreal.Vector(0.0, 2600.0, 460.0),
    ]
    for i, pos in enumerate(billboard_positions):
        bb = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, pos)
        comp = bb.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(plane)
        comp.set_world_scale3d(unreal.Vector(14.0, 0.6, 9.0))
        comp.set_material(0, magenta if i % 2 == 0 else cyan)
        bb.set_actor_rotation(unreal.Rotator(0.0, 0.0 if i % 2 == 0 else 90.0, 0.0), teleport_physics=True)
        bb.set_actor_label(f"Billboard_{i}")

    # thicken fog (add new fog actor)
    fog = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0.0, 0.0, 0.0))
    fcomp = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
    if fcomp:
        fcomp.set_editor_property("fog_density", 0.07)
        fcomp.set_editor_property("fog_height_falloff", 0.015)

    def spawn_tower(pos, footprint, height, strips=3, hue_shift=False):
        nonlocal towers_spawned
        tower = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, pos)
        comp = tower.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(cube)
        comp.set_material(0, base)
        comp.set_world_scale3d(unreal.Vector(footprint.x, footprint.y, height))
        # cyan strips
        for i in range(strips):
            offset = (i - strips // 2) * footprint.x * 50.0
            strip = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, pos + unreal.Vector(offset, footprint.y * 80.0, height * 50.0))
            scomp = strip.get_component_by_class(unreal.StaticMeshComponent)
            scomp.set_static_mesh(cube)
            scomp.set_material(0, magenta if (hue_shift and i % 2 == 0) else cyan)
            scomp.set_world_scale3d(unreal.Vector(0.1, 0.4, height * 2.0))
        tower.set_actor_label(f"ScifiTower_{pos.x}_{pos.y}")
        towers_spawned += 1

    towers = [
        (unreal.Vector(0.0, 0.0, 0.0), unreal.Vector(2.6, 1.6, 32.0)),
        (unreal.Vector(1400.0, 300.0, 0.0), unreal.Vector(1.9, 1.3, 22.0)),
        (unreal.Vector(-1400.0, -500.0, 0.0), unreal.Vector(1.6, 1.4, 20.0)),
        (unreal.Vector(500.0, -1400.0, 0.0), unreal.Vector(1.4, 1.2, 18.0)),
        (unreal.Vector(-700.0, 1100.0, 0.0), unreal.Vector(1.6, 1.3, 18.0)),
        (unreal.Vector(1200.0, -1100.0, 0.0), unreal.Vector(1.3, 1.0, 16.0)),
        (unreal.Vector(-1700.0, 800.0, 0.0), unreal.Vector(1.3, 1.1, 16.5)),
    ]
    for pos, scale in towers:
        spawn_tower(pos, unreal.Vector(scale.x, scale.y, 1.0), scale.z, strips=3, hue_shift=True)

    # dense mid/foreground grid
    for gx in range(-4, 5):
        for gy in range(-4, 5):
            if abs(gx) <= 1 and abs(gy) <= 1:
                continue
            loc = unreal.Vector(gx * 520.0, gy * 520.0, 0.0)
            height = random.uniform(6.0, 13.0)
            footprint = unreal.Vector(random.uniform(0.7, 1.6), random.uniform(0.7, 1.6), 1.0)
            strips = 2 if random.random() > 0.35 else 1
            spawn_tower(loc, footprint, height, strips=strips, hue_shift=random.random() > 0.65)

    # distant horizon glow lights (lined perimeter)
    ring_radius = 3200.0
    ring_height = 720.0
    ring_count = 16
    for i in range(ring_count):
        ang = (360.0 / ring_count) * i
        rad = math.radians(ang)
        loc = unreal.Vector(math.cos(rad) * ring_radius, math.sin(rad) * ring_radius, ring_height)
        glow = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.PointLight, loc)
        lcomp = glow.get_component_by_class(unreal.PointLightComponent)
        if lcomp:
            lcomp.set_editor_property("intensity", 12000.0)
            set_light_color_safe(lcomp, unreal.LinearColor(0.05, 0.82, 1.0, 1.0))

    # elevated sky bridges
    bridges = [
        (unreal.Vector(0.0, 0.0, 620.0), unreal.Vector(22.0, 0.8, 0.25)),
        (unreal.Vector(-300.0, 500.0, 520.0), unreal.Vector(16.0, 0.7, 0.22)),
        (unreal.Vector(450.0, -650.0, 580.0), unreal.Vector(18.0, 0.7, 0.22)),
        (unreal.Vector(900.0, 0.0, 700.0), unreal.Vector(20.0, 0.7, 0.22)),
    ]
    for i, (pos, scale) in enumerate(bridges):
        bridge = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, pos)
        comp = bridge.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(plane)
        comp.set_material(0, base)
        comp.set_world_scale3d(scale)
        strip = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, pos + unreal.Vector(0.0, 0.0, 50.0))
        scomp = strip.get_component_by_class(unreal.StaticMeshComponent)
        scomp.set_static_mesh(plane)
        scomp.set_material(0, cyan)
        scomp.set_world_scale3d(unreal.Vector(scale.x, 0.08, 0.1))
        bridge.set_actor_label(f"Bridge_{i}")
        bridges_spawned += 1

    # mid/highways with magenta/cyan rails
    highways = [
        (unreal.Vector(0.0, -900.0, 450.0), unreal.Vector(30.0, 0.9, 0.25), 0.0, cyan),
        (unreal.Vector(-1200.0, 200.0, 520.0), unreal.Vector(26.0, 0.9, 0.25), 15.0, magenta),
        (unreal.Vector(300.0, 1200.0, 480.0), unreal.Vector(22.0, 0.9, 0.25), -20.0, cyan),
        (unreal.Vector(1100.0, -400.0, 550.0), unreal.Vector(24.0, 0.9, 0.25), 10.0, magenta),
    ]
    for idx, (pos, scl, yaw, mat) in enumerate(highways):
        road = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, pos)
        comp = road.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(plane)
        comp.set_material(0, mat)
        comp.set_world_scale3d(scl)
        road.set_actor_rotation(unreal.Rotator(0.0, yaw, 0.0), teleport_physics=True)
        road.set_actor_label(f"Highway_{idx}")
        highways_spawned += 1

    # neon signage at foreground
    sign = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(-1200.0, -200.0, 150.0))
    scomp = sign.get_component_by_class(unreal.StaticMeshComponent)
    scomp.set_static_mesh(plane)
    scomp.set_material(0, red)
    scomp.set_world_scale3d(unreal.Vector(1.5, 0.2, 1.0))
    sign.set_actor_rotation(unreal.Rotator(0.0, 20.0, 0.0), teleport_physics=True)

    # foggy mood lights (aligned inner ring)
    inner_ring_radius = 1200.0
    inner_ring_height = 520.0
    for i in range(10):
        ang = (360.0 / 10) * i
        rad = math.radians(ang)
        loc = unreal.Vector(math.cos(rad) * inner_ring_radius, math.sin(rad) * inner_ring_radius, inner_ring_height)
        light = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.PointLight, loc)
        lcomp = light.get_component_by_class(unreal.PointLightComponent)
        if lcomp:
            lcomp.set_editor_property("intensity", 5200.0)
            set_light_color_safe(lcomp, unreal.LinearColor(0.0, 0.75, 1.0, 1.0))

    # red accent lights (aligned quarter ring)
    for i in range(6):
        ang = 300.0 + (10.0 * i)
        rad = math.radians(ang)
        loc = unreal.Vector(math.cos(rad) * 1500.0, math.sin(rad) * 1500.0, 240.0)
        light = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.PointLight, loc)
        lcomp = light.get_component_by_class(unreal.PointLightComponent)
        if lcomp:
            lcomp.set_editor_property("intensity", 6000.0)
            lcomp.set_editor_property("light_color", unreal.LinearColor(1.0, 0.25, 0.1, 1.0))

    # denser fog
    fog = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0.0, 0.0, 0.0))
    fog_comp = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
    if fog_comp:
        fog_comp.set_editor_property("fog_density", 0.05)
        fog_comp.set_editor_property("fog_height_falloff", 0.02)

    # floating neon signs (cyan/magenta) with companion lights aligned on perimeter
    sign_radius = 2000.0
    sign_height = 680.0
    sign_count = 18
    for i in range(sign_count):
        ang = (360.0 / sign_count) * i
        rad = math.radians(ang)
        loc = unreal.Vector(math.cos(rad) * sign_radius, math.sin(rad) * sign_radius, sign_height + random.uniform(-120.0, 120.0))
        sign_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, loc)
        comp = sign_actor.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(plane)
        comp.set_material(0, magenta if i % 2 == 0 else cyan)
        comp.set_world_scale3d(unreal.Vector(random.uniform(1.6, 3.4), 0.35, 1.0))
        sign_actor.set_actor_rotation(unreal.Rotator(0.0, ang + 90.0, random.uniform(-5.0, 5.0)), teleport_physics=True)
        sign_actor.set_actor_label(f"NeonSign_{i}")
        sign_light = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.PointLight, loc + unreal.Vector(0.0, 0.0, 160.0))
        lcomp = sign_light.get_component_by_class(unreal.PointLightComponent)
        if lcomp:
            lcomp.set_editor_property("intensity", 9000.0)
            set_light_color_safe(lcomp, unreal.LinearColor(1.0, 0.15, 0.6, 1.0) if i % 2 == 0 else unreal.LinearColor(0.0, 0.85, 1.0, 1.0))
        signs_spawned += 1

    # roaming lights weaving between towers
    for i in range(18):
        start = unreal.Vector(random.uniform(-1800.0, 1800.0), random.uniform(-1800.0, 1800.0), random.uniform(260.0, 980.0))
        vel = unreal.Vector(random.uniform(-260.0, 260.0), random.uniform(-260.0, 260.0), random.uniform(-120.0, 120.0))
        color_a = unreal.LinearColor(0.0, 0.8, 1.0, 1.0)
        color_b = unreal.LinearColor(1.0, 0.15, 0.65, 1.0)
        _spawn_moving_light(start, vel, random.uniform(6000.0, 10000.0), color_a, color_b, hue_speed=0.7, attenuation=1600.0, label=f"MovingLight_{i}")
        moving_lights_spawned += 1

    # flying cars with headlights
    car_mat = ensure_emissive_material("M_UAT_Scifi_Car", unreal.LinearColor(0.1, 0.8, 1.0, 1.0), emissive_boost=14.0)
    for i in range(40):
        start = unreal.Vector(-3600.0, random.uniform(-1800.0, 1800.0), random.uniform(320.0, 1200.0))
        vel = unreal.Vector(random.uniform(700.0, 1150.0), random.uniform(-160.0, 160.0), random.uniform(-70.0, 70.0))
        actor = _spawn_moving_actor(plane, car_mat, start, vel, unreal.Vector(0.9, 2.8, 0.35), f"Car_{i}")
        head_offset = unreal.Vector(0.0, 0.0, 40.0)
        _spawn_moving_light(start + head_offset, vel, random.uniform(5000.0, 9000.0), unreal.LinearColor(0.1, 0.9, 1.0, 1.0), unreal.LinearColor(1.0, 0.25, 0.1, 1.0), hue_speed=0.9, attenuation=1200.0, label=f"CarLight_{i}")
        if actor:
            cars_spawned += 1

    # drones with cyan/magenta glow
    drone_mat = ensure_emissive_material("M_UAT_Scifi_Drone", unreal.LinearColor(0.0, 0.9, 0.8, 1.0), emissive_boost=10.0)
    for i in range(28):
        start = unreal.Vector(random.uniform(-2200.0, 2200.0), random.uniform(-2200.0, 2200.0), random.uniform(520.0, 1400.0))
        vel = unreal.Vector(random.uniform(-260.0, 260.0), random.uniform(-260.0, 260.0), random.uniform(-90.0, 90.0))
        drone = _spawn_moving_actor(sphere, drone_mat, start, vel, unreal.Vector(0.5, 0.5, 0.5), f"Drone_{i}")
        _spawn_moving_light(start + unreal.Vector(0.0, 0.0, 70.0), vel, random.uniform(5000.0, 9000.0), unreal.LinearColor(0.0, 0.9, 0.8, 1.0), unreal.LinearColor(1.0, 0.2, 0.7, 1.0), hue_speed=1.1, attenuation=900.0, label=f"DroneLight_{i}")
        if drone:
            drones_spawned += 1

    # Reference showcase near origin for quick selection
    _spawn_reference_showcase(unreal.Vector(-800.0, -2600.0, 0.0), cyan, magenta, base)
    setup_overview_plane()
    spawn_asset_line(unreal.Vector(600.0, -1400.0, 20.0), step=unreal.Vector(0.0, 320.0, 0.0))

    # Reference showcase near origin for quick selection
    _spawn_reference_showcase(unreal.Vector(-800.0, -2600.0, 0.0), cyan, magenta, base)

    total_actors = len(unreal.EditorLevelLibrary.get_all_level_actors() or [])
    log(f"Scifi build summary: towers={towers_spawned}, bridges={bridges_spawned}, highways={highways_spawned}, signs={signs_spawned}, cars={cars_spawned}, drones={drones_spawned}, moving_lights={moving_lights_spawned}, total_actors={total_actors}")

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
        if actor is None:
            continue
        rot = actor.get_actor_rotation()
        rot.yaw += CUBE_ROTATE_DEG_PER_SEC * delta_seconds
        actor.set_actor_rotation(rot, teleport_physics=True)
        alive.append(actor)

    _rotating_cubes = alive
    if not _rotating_cubes:
        _stop_rotate_tick()

def _stop_move_tick():
    global _move_tick_handle
    if _move_tick_handle is not None:
        unreal.unregister_slate_post_tick_callback(_move_tick_handle)
        _move_tick_handle = None

def _move_tick(delta_seconds):
    global _moving_actors, _move_time_accum, _move_debug_counter
    if not _moving_actors:
        _stop_move_tick()
        return

    try:
        _move_time_accum += delta_seconds
        _move_debug_counter += 1
        alive = []
        for actor, vel, meta in _moving_actors:
            if actor is None:
                continue
            try:
                loc = actor.get_actor_location()
            except Exception:
                continue
            vel_mut = unreal.Vector(vel.x, vel.y, vel.z)
            loc += vel_mut * delta_seconds

            if abs(loc.x) > _MOVE_BOUNDS.x:
                vel_mut.x *= -1.0
                loc.x = max(min(loc.x, _MOVE_BOUNDS.x), -_MOVE_BOUNDS.x)
            if abs(loc.y) > _MOVE_BOUNDS.y:
                vel_mut.y *= -1.0
                loc.y = max(min(loc.y, _MOVE_BOUNDS.y), -_MOVE_BOUNDS.y)
            if loc.z < _MOVE_Z_MIN or loc.z > _MOVE_BOUNDS.z:
                vel_mut.z *= -1.0
                loc.z = min(max(loc.z, _MOVE_Z_MIN), _MOVE_BOUNDS.z)

            if random.random() < 0.02:
                vel_mut.x += random.uniform(-30.0, 30.0)
                vel_mut.y += random.uniform(-30.0, 30.0)
                vel_mut.z += random.uniform(-15.0, 15.0)

            try:
                actor.set_actor_location(loc, sweep=False, teleport=True)
            except Exception:
                continue

            if meta:
                lcomp = meta.get("light_comp")
                owner_valid = False
                if lcomp:
                    try:
                        owner = lcomp.get_owner()
                        owner_valid = owner is not None
                    except Exception:
                        owner_valid = False
                if lcomp and owner_valid:
                    base_intensity = meta.get("base_intensity", lcomp.get_editor_property("intensity"))
                    phase = meta.get("phase", 0.0)
                    hue_speed = meta.get("hue_speed", 0.5)
                    t = _move_time_accum + phase
                    osc = 0.65 + 0.45 * math.sin(t * 1.35)
                    try:
                        lcomp.set_editor_property("intensity", base_intensity * osc)
                    except Exception:
                        pass
                    color_a = meta.get("color_a")
                    color_b = meta.get("color_b", color_a)
                    if color_a and color_b:
                        blend = 0.5 + 0.5 * math.sin(t * hue_speed)
                        new_color = unreal.LinearColor(
                            color_a.r * (1.0 - blend) + color_b.r * blend,
                            color_a.g * (1.0 - blend) + color_b.g * blend,
                            color_a.b * (1.0 - blend) + color_b.b * blend,
                            1.0
                        )
                        set_light_color_safe(lcomp, new_color)

            alive.append((actor, vel_mut, meta))
        _moving_actors = alive
        if _move_debug_counter % 120 == 0:
            log(f"Move tick active: {len(_moving_actors)} actors")
        if not _moving_actors:
            _stop_move_tick()
    except Exception as exc:
        log(f"Move tick suppressed error: {exc}")

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

def ensure_emissive_material(name, color, emissive_boost=5.0):
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

    base = unreal.MaterialEditingLibrary.create_material_expression(
        material,
        unreal.MaterialExpressionConstant3Vector
    )
    base.constant = color
    unreal.MaterialEditingLibrary.connect_material_property(
        base, "", unreal.MaterialProperty.MP_BASE_COLOR
    )

    emissive = unreal.MaterialEditingLibrary.create_material_expression(
        material,
        unreal.MaterialExpressionMultiply
    )
    color_expr = unreal.MaterialEditingLibrary.create_material_expression(
        material,
        unreal.MaterialExpressionConstant3Vector
    )
    color_expr.constant = color
    boost_expr = unreal.MaterialEditingLibrary.create_material_expression(
        material,
        unreal.MaterialExpressionConstant
    )
    boost_expr.r = emissive_boost
    unreal.MaterialEditingLibrary.connect_material_expressions(color_expr, "", emissive, "A")
    unreal.MaterialEditingLibrary.connect_material_expressions(boost_expr, "", emissive, "B")
    unreal.MaterialEditingLibrary.connect_material_property(
        emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR
    )

    unreal.MaterialEditingLibrary.recompile_material(material)
    unreal.EditorAssetLibrary.save_asset(mat_path)
    log(f"Created emissive material {mat_path}")
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

def spawn_rotating_test_cube(location=None, scale=unreal.Vector(8.0, 8.0, 8.0)):
    """Spawn a large red cube and register it for rotation."""
    global _rotating_cubes, _rotate_tick_handle
    loc = location or unreal.Vector(0.0, 0.0, 1800.0)
    cube = unreal.EditorAssetLibrary.load_asset(CUBE_MESH_PATH)
    if not cube:
        unreal.log_error(f"[UAT] Cube mesh not found: {CUBE_MESH_PATH}")
        return None
    mat = ensure_emissive_material("M_UAT_Test_Red", unreal.LinearColor(1.0, 0.05, 0.05, 1.0), emissive_boost=6.0)
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, loc)
    comp = actor.get_component_by_class(unreal.StaticMeshComponent)
    comp.set_static_mesh(cube)
    comp.set_world_scale3d(scale)
    if mat:
        comp.set_material(0, mat)
    actor.set_actor_label("Test_Rotating_RedCube")
    _rotating_cubes.append(actor)
    if CUBE_ROTATE_IN_EDITOR and _rotate_tick_handle is None:
        _rotate_tick_handle = unreal.register_slate_post_tick_callback(_rotate_tick)
    return actor

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

    if COMMAND == "build_codex_levels":
        write_log_marker("build_codex_levels start")
        create_level_with_builder("Codex_Desert", build_desert_level)
        create_level_with_builder("Codex_Forest", build_forest_level)
        create_level_with_builder("Codex_Neon", build_neon_level)
        create_level_with_builder("Codex_Snow", build_snow_level)
        create_level_with_builder("Codex_Volcano", build_volcano_level)
        create_level_with_builder("Codex_CityGrid", build_city_grid_level)
        create_level_with_builder("Codex_Canyon", build_canyon_level)
        create_level_with_builder("Codex_SkyIslands", build_sky_islands_level)
        create_level_with_builder("Codex_Checker", build_checker_level)
        create_level_with_builder("Codex_Ruins", build_ruins_level)
        create_level_with_builder("Codex_Chromatic", build_chromatic_level)
        create_level_with_builder("Codex_Crystal", build_crystal_level)
        create_level_with_builder("Codex_Industrial", build_industrial_level)
        log("Built Codex levels in /Game/Codex_levels")
        snapshot_log_to_file()
        return

    if COMMAND == "build_codex_scifi_landscape":
        write_log_marker("build_codex_scifi_landscape start")
        delete_codex_levels()
        create_level_with_builder("Codex_Scifi_Landscape", build_scifi_landscape_level)
        log("Built Codex_Scifi_Landscape in /Game/Codex_levels")
        snapshot_log_to_file()
        return

    if COMMAND == "debug_move_tick":
        log(f"Move debug: handle={'set' if _move_tick_handle else 'none'}, actors={len(_moving_actors)}")
        if _moving_actors and _move_tick_handle is None:
            _ensure_move_tick()
            log("Move tick re-registered")
        snapshot_log_to_file()
        return

    if COMMAND == "spawn_debug_showcase":
        spawn_debug_showcase()
        snapshot_log_to_file()
        return

    if COMMAND == "stop_motion":
        stop_motion()
        snapshot_log_to_file()
        return

    if COMMAND == "organize_outliner":
        organize_outliner()
        snapshot_log_to_file()
        return

    if COMMAND == "lights_showcase_only":
        lights_showcase_only()
        snapshot_log_to_file()
        return

    if COMMAND == "spawn_marker":
        spawn_marker_near_camera()
        snapshot_log_to_file()
        return
    if COMMAND == "spawn_rotating_test_cube":
        spawn_rotating_test_cube()
        log("Spawned rotating test cube above city")
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

import unreal
import json
import os
import time
import random

# ============================================================
# CONFIG
# ============================================================
DELTA_X_CM = 100.0
DUPLICATE_UP_FEET = 10.0
TAG_TO_ADD = "AUTO_EDIT"

BLUE_NAME = "M_UAT_Blue"
RED_NAME  = "M_UAT_Red"
MATERIAL_PATH = "/Game/UAT_Materials"
SPHERE_MESH_PATH = "/Engine/BasicShapes/Sphere.Sphere"
CONVERT_TO_SPHERE = True
PLANE_MESH_PATH = "/Engine/BasicShapes/Plane.Plane"

CREATE_TRIANGLES = True
TRIANGLE_COUNT = 20
TRIANGLE_MIN_SIZE_CM = 30.0
TRIANGLE_MAX_SIZE_CM = 120.0

CREATE_GRASS_FIELD = True
GRASS_ROWS = 12
GRASS_COLS = 12
GRASS_SPACING_CM = 80.0
GRASS_BLADE_SCALE = 0.25

# ============================================================
# HELPERS
# ============================================================
def ts():
    return time.strftime("%Y%m%d_%H%M%S")

def log(msg):
    unreal.log(f"[UAT] {msg}")

def automation_dir():
    d = os.path.join(unreal.Paths.project_saved_dir(), "Automation")
    os.makedirs(d, exist_ok=True)
    return d

def actor_sub():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

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

# ============================================================
# EXPORT
# ============================================================
def export_selected():
    selected = list(actor_sub().get_selected_level_actors() or [])
    if not selected:
        unreal.log_error("[UAT] No actors selected.")
        return None, None

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
    return data, selected

# ============================================================
# MAIN
# ============================================================
def main():
    export_data, selected = export_selected()
    if not export_data:
        return

    if CONVERT_TO_SPHERE:
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

    center = selected[0].get_actor_location()

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

import unreal, json, os, time

def _out_dir():
    d = os.path.join(unreal.Paths.project_saved_dir(), "Automation")
    os.makedirs(d, exist_ok=True)
    return d

def export_selected():
    actors = list(unreal.EditorLevelLibrary.get_selected_level_actors() or [])
    if not actors:
        unreal.log_error("[UAT] No selected actors.")
        return None

    payload = {"timestamp": time.strftime("%Y%m%d_%H%M%S"), "actors": []}

    for a in actors:
        t = a.get_actor_transform()
        loc = t.translation
        rot = t.rotation.rotator()
        scl = t.scale3d
        payload["actors"].append({
            "id": a.get_path_name(),
            "label": a.get_actor_label(),
            "class": a.get_class().get_path_name(),
            "transform": {
                "location": {"x": loc.x, "y": loc.y, "z": loc.z},
                "rotation": {"pitch": rot.pitch, "yaw": rot.yaw, "roll": rot.roll},
                "scale": {"x": scl.x, "y": scl.y, "z": scl.z},
            },
            "tags": [str(tag) for tag in a.tags],
        })

    out_path = os.path.join(_out_dir(), f"export_{payload['timestamp']}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    unreal.log(f"[UAT] Exported {len(payload['actors'])} actor(s) -> {out_path}")
    return out_path

def validate_basic():
    unreal.log("[UAT] validate_basic() ran.")
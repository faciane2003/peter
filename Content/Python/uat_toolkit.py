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
            "tags": [str(tag) for tag in (a.tags or [])],
        })

    out_path = os.path.join(_out_dir(), f"export_{payload['timestamp']}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    unreal.log(f"[UAT] Exported {len(payload['actors'])} actor(s) -> {out_path}")
    return out_path

def validate_basic():
    unreal.log("[UAT] validate_basic() ran.")


def apply_from_json(path, dry_run=True, set_tags=True):
    if not os.path.exists(path):
        unreal.log_error(f"[UAT] JSON not found: {path}")
        return {"applied": 0, "missing": 0}

    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    by_path = {a.get_path_name(): a for a in actors}

    applied = 0
    missing = 0

    for item in payload.get("actors", []):
        actor = by_path.get(item.get("id"))
        if not actor:
            missing += 1
            continue

        loc = item.get("transform", {}).get("location")
        if loc:
            new_loc = unreal.Vector(
                float(loc.get("x", 0.0)),
                float(loc.get("y", 0.0)),
                float(loc.get("z", 0.0)),
            )
            if not dry_run:
                actor.set_actor_location(new_loc, sweep=False, teleport=True)

        if set_tags and "tags" in item and not dry_run:
            actor.tags = [unreal.Name(str(t)) for t in (item.get("tags") or [])]

        applied += 1

    unreal.log(f"[UAT] apply_from_json applied={applied} missing={missing} dry_run={dry_run}")
    return {"applied": applied, "missing": missing}

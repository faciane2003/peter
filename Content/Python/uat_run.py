# uat_run.py (bulletproof import)

import os
import importlib.util
import unreal

# Load uat_toolkit.py from the same folder as this file
folder = os.path.dirname(__file__)
toolkit_path = os.path.join(folder, "uat_toolkit.py")

if not os.path.exists(toolkit_path):
    unreal.log_error(f"[UAT] Missing file: {toolkit_path}")
    raise FileNotFoundError(toolkit_path)

spec = importlib.util.spec_from_file_location("uat_toolkit", toolkit_path)
uat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uat)

selected = unreal.EditorLevelLibrary.get_selected_level_actors()
if selected:
    uat.export_selected()
else:
    uat.validate_basic()

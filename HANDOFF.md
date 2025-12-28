Handoff Log (DevOps UE 5.6 Python automation)

Project:
  F:\Unreal Projects\DevOps\DevOps (UE 5.6)

Goal:
  Remote-control UE via Python; accept natural language commands by updating
  Content/Python/uat_one_click.py and running it.

Current flow:
  1) Start listener in UE Python console:
     import uat_listener
     uat_listener.start_listener()

  2) Remote run script:
     .\run_unreal_python_remote.ps1 -Script "F:\Unreal Projects\DevOps\DevOps\Content\Python\uat_one_click.py"

  Preferred pattern: write the requested action into uat_one_click.py (COMMAND),
  then run the script via the remote runner.

Files and what they do:
  - Content/Python/uat_one_click.py
    - Primary command runner.
    - COMMAND currently set to "diagnostic_solar_system".
    - Added solar system builder:
      - clear_shape_actors() removes StaticMeshActor / InstancedStaticMeshActor / ProceduralMeshActor.
      - spawn_colored_sphere() helper creates colored sphere with label.
    - Added file logging:
      - log() now appends to Saved/Automation/uat_script.log.
      - snapshot_log_to_file() writes Saved/Automation/uat_log_snapshot.txt.
      - write_log_marker() writes a marker line into the log.
    - Added COMMAND options:
      - "create_solar_system"
      - "diagnostic_solar_system" (logs before/after, snapshots, focuses viewport)
      - "write_log_marker"
      - "snapshot_log"
      - "log_marker_and_snapshot"
      - "add_blue_sphere" (still available)
      - "write_log_paths" (writes Saved/Automation/uat_log_paths.txt)
    - If COMMAND is set, main() executes it and returns early.
    - New helper: run_command_once(command_name) to invoke a COMMAND without changing the default.

  - Content/Python/uat_listener.py
    - Executes remote JSON payloads.
    - Uses unreal.PythonScriptLibrary.execute_python_command when available,
      falls back to execute_python_command_ex, then exec(...).

  - Content/Python/uat_toolkit.py
    - Added apply_from_json(path, dry_run=True, set_tags=True).
    - export_selected() uses (a.tags or []) to avoid None.

  - Content/Python/uat_menu.py
    - Registers a Tools > UAT Commands menu in the UE editor with buttons for common commands.
    - Run in UE Python console: import uat_menu; uat_menu.build_menu()
    - Buttons: create solar system, diagnostic solar system, add blue sphere, log marker + snapshot, write marker, snapshot log, write log paths, start/stop listener.
    - Uses run_command_once to call commands without changing global COMMAND.
    - If menu not visible, reload: import importlib, uat_menu; importlib.reload(uat_menu); uat_menu.build_menu()

  - run_unreal_python_remote.ps1
    - Builds JSON payload with ConvertTo-Json -Compress to support quotes/newlines.
    - Added open_epic_unreal.ps1 to launch Epic Launcher + Unreal Editor (defaults to DevOps project; supports overrides).

Last successful tests:
  - "add_blue_sphere" via COMMAND in uat_one_click.py.
  - Ran run_unreal_python_remote.ps1 -Script ..., blue sphere spawned.
  - "create_solar_system" added colored spheres (sun + planets + moon).

Known gotchas:
  - If commands fail, restart listener after edits:
      import uat_listener
      uat_listener.stop_listener()
      uat_listener.start_listener()

Log files:
  - Saved/Automation/uat_script.log (append-only)
  - Saved/Automation/uat_log_snapshot.txt (full snapshot)

Git status:
  - Latest commit: 6d49809
  - Pushed to origin/main and origin/main-backup.

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
    - COMMAND = "add_three_cones" currently enabled.
    - spawn_three_cones() helper added.
    - CREATE_ROTATING_CUBE = False.
    - If COMMAND is set, main() executes it and returns early.

  - Content/Python/uat_listener.py
    - Executes remote JSON payloads.
    - Uses unreal.PythonScriptLibrary.execute_python_command when available,
      falls back to execute_python_command_ex, then exec(...).

  - Content/Python/uat_toolkit.py
    - Added apply_from_json(path, dry_run=True, set_tags=True).
    - export_selected() uses (a.tags or []) to avoid None.

  - run_unreal_python_remote.ps1
    - Builds JSON payload with ConvertTo-Json -Compress to support quotes/newlines.

Last successful test:
  - "add three cones" via COMMAND in uat_one_click.py.
  - Ran run_unreal_python_remote.ps1 -Script ..., cones spawned.

Known gotchas:
  - If commands fail, restart listener after edits:
      import uat_listener
      uat_listener.stop_listener()
      uat_listener.start_listener()

Git status:
  - Latest commit: 6d49809
  - Pushed to origin/main and origin/main-backup.

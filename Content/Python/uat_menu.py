import unreal
import uat_one_click
import uat_listener


SECTION = "UAT"


def _make_command_entry(label, tooltip, command_name):
    entry = unreal.ToolMenuEntry(
        name=f"UAT.{command_name}",
        type=unreal.MultiBlockType.MENU_ENTRY,
        insert_position=unreal.ToolMenuInsert("", unreal.ToolMenuInsertType.DEFAULT)
    )
    entry.set_label(label)
    entry.set_tool_tip(tooltip)
    entry.set_string_command(
        unreal.ToolMenuStringCommandType.PYTHON,
        "",
        f"import uat_one_click; uat_one_click.run_command_once('{command_name}')"
    )
    return entry


def _make_listener_entry(label, tooltip, code):
    entry = unreal.ToolMenuEntry(
        name=f"UAT.Listener.{label}",
        type=unreal.MultiBlockType.MENU_ENTRY,
        insert_position=unreal.ToolMenuInsert("", unreal.ToolMenuInsertType.DEFAULT)
    )
    entry.set_label(label)
    entry.set_tool_tip(tooltip)
    entry.set_string_command(
        unreal.ToolMenuStringCommandType.PYTHON,
        "",
        code
    )
    return entry


def build_menu():
    menus = unreal.ToolMenus.get()
    menu = menus.find_menu("LevelEditor.MainMenu.Tools")
    if not menu:
        unreal.log_error("[UAT] Tools menu not found; cannot register UAT commands.")
        return
    try:
        menu.remove_section(SECTION)
    except Exception:
        pass
    menu.add_section(SECTION, "UAT Commands")

    commands = [
        ("Create Solar System", "Clear shapes and build solar system scene", "create_solar_system"),
        ("Diagnostic Solar System", "Build solar system + log + snapshot + viewport focus", "diagnostic_solar_system"),
        ("Add Blue Sphere", "Add a blue sphere above selection/world origin", "add_blue_sphere"),
        ("Log Marker + Snapshot", "Write marker and snapshot log files", "log_marker_and_snapshot"),
        ("Write Log Marker", "Write marker to Saved/Automation/uat_script.log", "write_log_marker"),
        ("Snapshot Log", "Write Saved/Automation/uat_log_snapshot.txt", "snapshot_log"),
        ("Write Log Paths", "Emit Saved/Automation/uat_log_paths.txt", "write_log_paths"),
    ]

    for label, tip, cmd in commands:
        menu.add_menu_entry(SECTION, _make_command_entry(label, tip, cmd))

    # Listener helpers
    menu.add_menu_entry(
        SECTION,
        _make_listener_entry(
            "Start Listener",
            "Start the UAT listener on 127.0.0.1:27777",
            "import uat_listener; uat_listener.start_listener()"
        )
    )
    menu.add_menu_entry(
        SECTION,
        _make_listener_entry(
            "Stop Listener",
            "Stop the UAT listener",
            "import uat_listener; uat_listener.stop_listener()"
        )
    )

    menus.refresh_all_widgets()
    unreal.log("[UAT] Menu registered under Tools > UAT Commands")


def unregister_menu():
    menus = unreal.ToolMenus.get()
    menu = menus.find_menu("LevelEditor.MainMenu.Tools")
    if menu:
        menu.remove_section(SECTION)
    menus.refresh_all_widgets()
    unreal.log("[UAT] Menu unregistered")


if __name__ == "__main__":
    build_menu()

import unreal
import os
import json
import socket
import threading
import queue

_queue = queue.Queue()
_shutdown = threading.Event()
_server = None
_thread = None
_tick_handle = None


def _log(msg):
    unreal.log(f"[UAT] {msg}")


def _exec_script(path):
    if not os.path.exists(path):
        unreal.log_error(f"[UAT] Script not found: {path}")
        return

    try:
        if hasattr(unreal, "PythonScriptLibrary") and hasattr(unreal.PythonScriptLibrary, "execute_python_script"):
            unreal.PythonScriptLibrary.execute_python_script(path)
            return
    except Exception as exc:
        unreal.log_warning(f"[UAT] PythonScriptLibrary failed, falling back: {exc}")

    with open(path, "r", encoding="utf-8") as f:
        code = f.read()
    scope = {"__file__": path, "__name__": "__main__"}
    exec(compile(code, path, "exec"), scope, scope)


def _handle_message(msg):
    msg = msg.strip()
    if not msg:
        return

    if msg.startswith("{"):
        try:
            payload = json.loads(msg)
        except Exception:
            unreal.log_warning("[UAT] Invalid JSON payload")
            return

        if "script" in payload:
            _log(f"Running script: {payload['script']}")
            _exec_script(payload["script"])
            return
        if "command" in payload:
            _log("Running python command")
            unreal.execute_python_command(payload["command"])
            return

        unreal.log_warning("[UAT] JSON payload missing 'script' or 'command'")
        return

    # Default: treat as script path
    _log(f"Running script: {msg}")
    _exec_script(msg)


def _tick(_delta_seconds):
    while True:
        try:
            msg = _queue.get_nowait()
        except queue.Empty:
            break
        try:
            _handle_message(msg)
        except Exception as exc:
            unreal.log_error(f"[UAT] Listener error: {exc}")


def _listener_thread(host, port):
    global _server
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(5)
        _server = s
        _log(f"Listening on {host}:{port}")

        while not _shutdown.is_set():
            try:
                s.settimeout(0.5)
                conn, _addr = s.accept()
            except socket.timeout:
                continue
            except Exception:
                break

            with conn:
                data = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                try:
                    text = data.decode("utf-8")
                except Exception:
                    continue
                _queue.put(text)

    _server = None


def start_listener(host="127.0.0.1", port=27777):
    global _thread, _tick_handle

    if _thread and _thread.is_alive():
        _log("Listener already running")
        return

    _shutdown.clear()
    _thread = threading.Thread(target=_listener_thread, args=(host, port), daemon=True)
    _thread.start()

    if _tick_handle is None:
        _tick_handle = unreal.register_slate_post_tick_callback(_tick)


def stop_listener():
    global _thread, _tick_handle

    _shutdown.set()

    if _server:
        try:
            _server.close()
        except Exception:
            pass

    if _thread:
        _thread.join(timeout=1.0)
        _thread = None

    if _tick_handle is not None:
        unreal.unregister_slate_post_tick_callback(_tick_handle)
        _tick_handle = None

    _log("Listener stopped")


def status():
    running = _thread is not None and _thread.is_alive()
    return {"running": running}

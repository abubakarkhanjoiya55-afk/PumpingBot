"""
SceneCut Pro+ — desktop launcher

Stable Windows shell:
  - Edge/Chrome --app window (avoids pywebview .NET KeyError: 'master')
  - Local Flask server for fast 2GB+ cuts
  - PowerShell file dialog for local paths (no upload)

Usage:
  python desktop_app.py
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

from flask import jsonify, request


def _app_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


BASE_DIR = _app_root()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

os.environ.setdefault("SCENECUT_DESKTOP", "1")

from app import (  # noqa: E402
    JOB,
    SESSION,
    UPLOAD_KIND_MAP,
    _ensure_dirs,
    _file_meta,
    _validate_upload_kind,
    app,
)
from desktop_shell import (  # noqa: E402
    open_app_window,
    pick_file_path,
    wait_app_process,
)
from desktop_update import (  # noqa: E402
    live_base,
    local_version,
    remote_manifest,
    restart_desktop,
    sync_from_live,
    update_frozen_app,
    write_local_version,
)


SHUTDOWN = threading.Event()
APP_PROC = None


def _install_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    local = Path(os.environ.get("LOCALAPPDATA") or "") / "SceneCutProPlus"
    if local.exists():
        return local
    return BASE_DIR


def _free_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])


def _wait_until_up(port: int, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def _run_server(port: int) -> None:
    try:
        from waitress import serve

        serve(
            app,
            host="127.0.0.1",
            port=port,
            threads=16,
            channel_timeout=3600,
            recv_bytes=65536,
        )
    except ImportError:
        app.run(
            host="127.0.0.1",
            port=port,
            debug=False,
            use_reloader=False,
            threaded=True,
        )


def _kill_app_proc() -> None:
    global APP_PROC
    proc = APP_PROC
    APP_PROC = None
    if proc is None:
        return
    try:
        proc.terminate()
    except Exception:  # noqa: BLE001
        pass


@app.post("/api/shutdown")
def api_shutdown():
    if os.environ.get("SCENECUT_DESKTOP") != "1":
        return jsonify({"ok": False, "error": "Shutdown only in desktop mode"}), 400

    def _do() -> None:
        SHUTDOWN.set()
        _kill_app_proc()

    threading.Timer(0.2, _do).start()
    return jsonify({"ok": True, "message": "Closing SceneCut Pro+…"})


@app.get("/api/desktop")
def api_desktop():
    return jsonify(
        {
            "ok": True,
            "desktop": True,
            "native_window": True,
            "shell": "edge-app",
            "local_fast": True,
            "live_url": live_base(),
            "local_version": local_version(_install_dir()),
            "job": JOB.snapshot().get("status"),
            "project": SESSION.get("project_name"),
            "has_movie": bool(SESSION.get("movie")),
        }
    )


@app.post("/api/desktop/pick")
def api_desktop_pick_file():
    """Native file dialog — registers absolute path (no multi‑GB upload)."""
    if os.environ.get("SCENECUT_DESKTOP") != "1":
        return jsonify({"ok": False, "error": "desktop only"}), 400
    payload = request.get_json(silent=True) or {}
    kind = (payload.get("kind") or "").strip()
    if kind not in UPLOAD_KIND_MAP:
        return jsonify({"ok": False, "error": "invalid kind"}), 400
    path_str = pick_file_path(kind)
    if not path_str:
        return jsonify({"ok": False, "cancelled": True})
    path = Path(path_str).expanduser().resolve()
    if not path.is_file():
        return jsonify({"ok": False, "error": "file missing"}), 400
    err, _ = _validate_upload_kind(kind, path.name)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    SESSION[UPLOAD_KIND_MAP[kind]] = str(path)
    return jsonify(
        {
            "ok": True,
            "kind": kind,
            "filename": path.name,
            "meta": _file_meta(path),
            "path": str(path),
            "size": path.stat().st_size,
            "local": True,
        }
    )


@app.post("/api/desktop/update")
def api_desktop_update():
    """Apply update + restart desktop."""
    if os.environ.get("SCENECUT_DESKTOP") != "1":
        return jsonify({"ok": False, "error": "desktop only"}), 400
    install = _install_dir()
    if getattr(sys, "frozen", False):
        result = update_frozen_app()
        if result.get("ok"):
            threading.Timer(0.8, lambda: (SHUTDOWN.set(), _kill_app_proc())).start()
        return jsonify(result)
    result = sync_from_live(install, force=True)
    if result.get("ok"):
        restart_desktop(install)
        threading.Timer(0.9, lambda: (SHUTDOWN.set(), _kill_app_proc())).start()
    return jsonify(result)


def _prepend_bundled_ffmpeg() -> None:
    for folder in (
        BASE_DIR / "tools" / "ffmpeg" / "bin",
        _install_dir() / "tools" / "ffmpeg" / "bin",
        Path(os.environ.get("LOCALAPPDATA", "")) / "SceneCutProPlus" / "tools" / "ffmpeg" / "bin",
    ):
        if (folder / "ffmpeg.exe").exists():
            os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
            return


def _quiet_background_sync() -> None:
    if getattr(sys, "frozen", False):
        return
    try:
        result = sync_from_live(_install_dir(), force=False)
        if result.get("updated"):
            print(f"  Background update applied ({result.get('files')} files).")
    except Exception as exc:  # noqa: BLE001
        print(f"  Background update skip: {exc}")


def main(argv: list[str] | None = None) -> int:
    global APP_PROC
    parser = argparse.ArgumentParser(description="SceneCut Pro+ Desktop")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "5000")))
    parser.add_argument("--browser", action="store_true", help="Classic browser tab")
    parser.add_argument("--no-update", action="store_true")
    args = parser.parse_args(argv)

    _ensure_dirs()
    _prepend_bundled_ffmpeg()

    if not args.no_update:
        _quiet_background_sync()
        try:
            man = remote_manifest()
            ver = str(man.get("version") or "")
            if ver:
                write_local_version(_install_dir(), ver)
        except Exception:  # noqa: BLE001
            pass

    port = _free_port(args.port)
    url = f"http://127.0.0.1:{port}/home?desktop=1"

    print("")
    print("  SceneCut Pro+ Desktop")
    print("  Shell: Edge/Chrome app window (stable — no .NET crash)")
    print(f"  Window: {url}")
    print("")

    thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
    thread.start()
    if not _wait_until_up(port):
        print("ERROR: local server start fail")
        return 1

    if args.browser:
        webbrowser.open(url)
        try:
            while not SHUTDOWN.is_set():
                time.sleep(0.25)
        except KeyboardInterrupt:
            pass
        return 0

    APP_PROC = open_app_window(url)
    if APP_PROC is None:
        print("Edge/Chrome nahi mila — browser tab fallback.")
        webbrowser.open(url)
        try:
            while not SHUTDOWN.is_set():
                time.sleep(0.25)
        except KeyboardInterrupt:
            pass
    else:
        try:
            wait_app_process(APP_PROC, SHUTDOWN)
        except KeyboardInterrupt:
            SHUTDOWN.set()
            _kill_app_proc()

    print("SceneCut Pro+ closed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

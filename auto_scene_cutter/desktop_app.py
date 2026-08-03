"""
SceneCut Pro+ — desktop launcher

Starts the local editor server, opens the default browser,
and keeps running until the user quits from the app (or Ctrl+C).

Usage:
  python desktop_app.py
  python desktop_app.py --port 5000
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

def _app_root() -> Path:
    """Source tree OR PyInstaller extract folder."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


BASE_DIR = _app_root()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

# Mark desktop mode before importing app (UI can show Quit)
os.environ.setdefault("SCENECUT_DESKTOP", "1")

from app import JOB, SESSION, _ensure_dirs, app  # noqa: E402


SHUTDOWN = threading.Event()


def _free_port(preferred: int) -> int:
    """Use preferred port if free, otherwise pick an open one."""
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
    # Desktop: localhost only (safer on shared PCs)
    try:
        from waitress import serve

        serve(
            app,
            host="127.0.0.1",
            port=port,
            threads=8,
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


@app.post("/api/shutdown")
def api_shutdown():
    """Quit desktop app from the UI."""
    if os.environ.get("SCENECUT_DESKTOP") != "1":
        return {"ok": False, "error": "Shutdown only in desktop mode"}, 400
    # Delay so the HTTP response can flush
    threading.Timer(0.35, SHUTDOWN.set).start()
    return {"ok": True, "message": "Closing SceneCut Pro+…"}


@app.get("/api/desktop")
def api_desktop():
    return {
        "ok": True,
        "desktop": os.environ.get("SCENECUT_DESKTOP") == "1",
        "job": JOB.snapshot().get("status"),
        "project": SESSION.get("project_name"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SceneCut Pro+ Desktop")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "5000")))
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    _ensure_dirs()
    port = _free_port(args.port)
    url = f"http://127.0.0.1:{port}/?desktop=1"

    print("")
    print("  SceneCut Pro+ Desktop")
    print(f"  Editor: {url}")
    print("  Quit from the app Quit button, or press Ctrl+C here.")
    print("")

    thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
    thread.start()

    if not _wait_until_up(port):
        print("ERROR: server start fail — port busy / firewall?")
        return 1

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            print(f"Browser open fail — manually open: {url}")

    try:
        while not SHUTDOWN.is_set():
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass

    print("SceneCut Pro+ closed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

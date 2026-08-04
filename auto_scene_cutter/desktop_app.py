"""
SceneCut Pro+ — desktop launcher

Starts local server and opens a native app window (pywebview).
Falls back to the system browser if native window is unavailable.

Usage:
  python desktop_app.py
  python desktop_app.py --port 5000
  python desktop_app.py --browser
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
WINDOW = None


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


def _close_window() -> None:
    global WINDOW
    w = WINDOW
    WINDOW = None
    if w is not None:
        try:
            w.destroy()
        except Exception:  # noqa: BLE001
            pass


@app.post("/api/shutdown")
def api_shutdown():
    """Quit desktop app from the UI."""
    if os.environ.get("SCENECUT_DESKTOP") != "1":
        return {"ok": False, "error": "Shutdown only in desktop mode"}, 400

    def _do() -> None:
        SHUTDOWN.set()
        _close_window()

    # Delay so the HTTP response can flush
    threading.Timer(0.25, _do).start()
    return {"ok": True, "message": "Closing SceneCut Pro+…"}


@app.get("/api/desktop")
def api_desktop():
    return {
        "ok": True,
        "desktop": os.environ.get("SCENECUT_DESKTOP") == "1",
        "native_window": WINDOW is not None,
        "job": JOB.snapshot().get("status"),
        "project": SESSION.get("project_name"),
    }


def _open_native_window(url: str) -> bool:
    """Open CapCut-like native window. Return False to fall back to browser."""
    global WINDOW
    try:
        import webview
    except ImportError:
        return False

    try:
        WINDOW = webview.create_window(
            "SceneCut Pro+",
            url,
            width=1360,
            height=860,
            min_size=(1024, 680),
            background_color="#0e0e10",
            text_select=True,
        )

        def _on_closed() -> None:
            SHUTDOWN.set()

        try:
            WINDOW.events.closed += _on_closed
        except Exception:  # noqa: BLE001
            pass

        # Blocks until window closes
        webview.start(debug=False)
        SHUTDOWN.set()
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"Native window fail — browser fallback ({exc})")
        WINDOW = None
        return False


def _prepend_bundled_ffmpeg() -> None:
    """Use portable ffmpeg next to the app when present (Setup.exe / student pack)."""
    candidates = [
        BASE_DIR / "tools" / "ffmpeg" / "bin",
        Path(os.environ.get("LOCALAPPDATA", "")) / "SceneCutProPlus" / "tools" / "ffmpeg" / "bin",
    ]
    for folder in candidates:
        exe = folder / "ffmpeg.exe"
        if exe.exists():
            os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
            return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SceneCut Pro+ Desktop")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "5000")))
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Force system browser instead of native window",
    )
    args = parser.parse_args(argv)

    _ensure_dirs()
    _prepend_bundled_ffmpeg()
    port = _free_port(args.port)
    # CapCut-style home landing inside the app window
    url = f"http://127.0.0.1:{port}/home?desktop=1"

    print("")
    print("  SceneCut Pro+ Desktop")
    print(f"  Home: {url}")
    print("  Quit from app Quit button, or close the window.")
    print("")

    thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
    thread.start()

    if not _wait_until_up(port):
        print("ERROR: server start fail — port busy / firewall?")
        return 1

    use_browser = args.browser or args.no_browser
    opened_native = False
    if not use_browser and not args.no_browser:
        opened_native = _open_native_window(url)

    if not opened_native:
        if args.no_browser:
            print(f"Server only — open manually: {url}")
        else:
            try:
                webbrowser.open(url)
                print("Browser mode (native window unavailable).")
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

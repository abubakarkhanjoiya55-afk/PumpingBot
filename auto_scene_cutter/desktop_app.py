"""
SceneCut Pro+ — desktop launcher

Opens a REAL native app window (pywebview) — not Chrome/Edge tabs.
When online, the window loads the LIVE site so desktop stays updated.
When offline, falls back to the local server.

Usage:
  python desktop_app.py
  python desktop_app.py --local
  python desktop_app.py --browser
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
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
from desktop_update import (  # noqa: E402
    ensure_webview_installed,
    is_online,
    live_base,
    sync_from_live,
)


SHUTDOWN = threading.Event()
WINDOW = None


class DesktopApi:
    """JS bridge so Quit works even when UI is loaded from the live site."""

    def quit(self) -> None:
        SHUTDOWN.set()
        _close_window()

    def ping(self) -> str:
        return "scenecut-desktop"


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
    if os.environ.get("SCENECUT_DESKTOP") != "1":
        return {"ok": False, "error": "Shutdown only in desktop mode"}, 400

    def _do() -> None:
        SHUTDOWN.set()
        _close_window()

    threading.Timer(0.25, _do).start()
    return {"ok": True, "message": "Closing SceneCut Pro+…"}


@app.get("/api/desktop")
def api_desktop():
    return {
        "ok": True,
        "desktop": True,
        "native_window": WINDOW is not None,
        "live_url": live_base(),
        "job": JOB.snapshot().get("status"),
        "project": SESSION.get("project_name"),
    }


def _open_native_window(url: str) -> bool:
    """Open CapCut-like native window. Never opens a browser tab."""
    global WINDOW
    if not ensure_webview_installed():
        print("ERROR: pywebview install fail — desktop window nahi khul sakti.")
        return False

    try:
        import webview

        api = DesktopApi()
        WINDOW = webview.create_window(
            "SceneCut Pro+",
            url,
            width=1360,
            height=860,
            min_size=(1024, 680),
            background_color="#07080c",
            text_select=True,
            js_api=api,
        )

        def _on_closed() -> None:
            SHUTDOWN.set()

        try:
            WINDOW.events.closed += _on_closed
        except Exception:  # noqa: BLE001
            pass

        webview.start(debug=False)
        SHUTDOWN.set()
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"Native window fail: {exc}")
        WINDOW = None
        return False


def _prepend_bundled_ffmpeg() -> None:
    candidates = [
        BASE_DIR / "tools" / "ffmpeg" / "bin",
        _install_dir() / "tools" / "ffmpeg" / "bin",
        Path(os.environ.get("LOCALAPPDATA", "")) / "SceneCutProPlus" / "tools" / "ffmpeg" / "bin",
    ]
    for folder in candidates:
        if (folder / "ffmpeg.exe").exists():
            os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
            return


def _pick_ui_url(port: int, force_local: bool) -> tuple[str, str]:
    """
    Returns (url, mode) where mode is 'live' or 'local'.
    Live = always latest landing/home from production inside the app window.
    """
    local = f"http://127.0.0.1:{port}/home?desktop=1"
    if force_local:
        return local, "local"
    if is_online():
        return f"{live_base()}/home?desktop=1", "live"
    return local, "local"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SceneCut Pro+ Desktop")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "5000")))
    parser.add_argument(
        "--local",
        action="store_true",
        help="Force local UI (skip live site)",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Debug only: open system browser",
    )
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="Skip live file sync for local installs",
    )
    args = parser.parse_args(argv)

    _ensure_dirs()
    _prepend_bundled_ffmpeg()

    # Keep non-frozen installs fresh from the live student pack
    if not args.no_update and not getattr(sys, "frozen", False):
        try:
            result = sync_from_live(_install_dir())
            if result.get("updated"):
                print(f"  Updated from live ({result.get('files')} files).")
        except Exception as exc:  # noqa: BLE001
            print(f"  Update skip: {exc}")

    port = _free_port(args.port)
    force_local = args.local or os.environ.get("SCENECUT_FORCE_LOCAL") == "1"
    url, mode = _pick_ui_url(port, force_local)

    print("")
    print("  SceneCut Pro+ Desktop")
    print(f"  Mode: {mode}")
    print(f"  Window: {url}")
    print("  Native app window — browser tab nahi.")
    print("")

    # Local API server always available (offline / local mode)
    thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
    thread.start()
    if not _wait_until_up(port):
        print("ERROR: local server start fail")
        return 1

    if args.browser:
        import webbrowser

        webbrowser.open(url)
        try:
            while not SHUTDOWN.is_set():
                time.sleep(0.25)
        except KeyboardInterrupt:
            pass
        return 0

    if not _open_native_window(url):
        # Last resort: still do NOT silently dump users into a random browser
        # without saying so — open browser only if native window impossible.
        print("Native window unavailable. Opening browser fallback…")
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            print(f"Open manually: {url}")
            return 1
        try:
            while not SHUTDOWN.is_set():
                time.sleep(0.25)
        except KeyboardInterrupt:
            pass

    print("SceneCut Pro+ closed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

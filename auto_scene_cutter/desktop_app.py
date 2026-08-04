"""
SceneCut Pro+ — CapCut-style desktop launcher

FIXED behavior (do not thrash):
  1) Native pywebview window titled "SceneCut Pro+" (NOT Microsoft Edge UI)
  2) Always opens APP HOME at /d  (never marketing landing)
  3) Local server for fast 2GB cuts + PowerShell file pick
  4) Edge --app only if native window fails to start

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


def _install_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    local = Path(os.environ.get("LOCALAPPDATA") or "") / "SceneCutProPlus"
    if local.exists():
        return local
    return BASE_DIR


def _bootstrap_sync(force: bool = False) -> bool:
    if getattr(sys, "frozen", False):
        return False
    try:
        from desktop_update import sync_from_live

        result = sync_from_live(_install_dir(), force=force)
        if result.get("updated"):
            print(f"  Updated ({result.get('files')} files) — restarting…")
            return True
    except Exception as exc:  # noqa: BLE001
        print(f"  Update skip: {exc}")
    return False


def _reexec() -> None:
    script = str(Path(__file__).resolve())
    args = [sys.executable, script, "--no-update"]
    for a in sys.argv[1:]:
        if a != "--no-update":
            args.append(a)
    os.execv(sys.executable, args)


if "--no-update" not in sys.argv and "--help" not in sys.argv:
    if _bootstrap_sync(force=False):
        _reexec()


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
    open_native_window,
    pick_file_path,
    start_native_gui,
    wait_app_process,
)
from desktop_update import (  # noqa: E402
    ensure_webview_installed,
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
WINDOW = None
_WINDOW_LIVE = False


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


def _mark_window_dead() -> None:
    global WINDOW, _WINDOW_LIVE
    _WINDOW_LIVE = False
    WINDOW = None
    SHUTDOWN.set()


def _safe_destroy_once() -> None:
    """Never double-destroy — that caused .NET KeyError: 'master'."""
    global WINDOW, _WINDOW_LIVE
    if not _WINDOW_LIVE:
        return
    _WINDOW_LIVE = False
    w = WINDOW
    WINDOW = None
    if w is None:
        return
    try:
        w.destroy()
    except KeyError:
        pass
    except Exception:  # noqa: BLE001
        pass


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


def _exit_soon() -> None:
    SHUTDOWN.set()
    _kill_app_proc()
    _safe_destroy_once()
    threading.Timer(0.5, lambda: os._exit(0)).start()


@app.post("/api/shutdown")
def api_shutdown():
    if os.environ.get("SCENECUT_DESKTOP") != "1":
        return jsonify({"ok": False, "error": "desktop only"}), 400
    threading.Timer(0.12, _exit_soon).start()
    return jsonify({"ok": True, "message": "Closing SceneCut Pro+…"})


@app.get("/api/desktop")
def api_desktop():
    return jsonify(
        {
            "ok": True,
            "desktop": True,
            "native_window": bool(_WINDOW_LIVE),
            "shell": "native" if _WINDOW_LIVE else ("edge-fallback" if APP_PROC else "server"),
            "local_fast": True,
            "entry": "/d",
            "live_url": live_base(),
            "local_version": local_version(_install_dir()),
            "job": JOB.snapshot().get("status"),
            "project": SESSION.get("project_name"),
            "has_movie": bool(SESSION.get("movie")),
        }
    )


@app.post("/api/desktop/pick")
def api_desktop_pick_file():
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
    if os.environ.get("SCENECUT_DESKTOP") != "1":
        return jsonify({"ok": False, "error": "desktop only"}), 400
    install = _install_dir()
    if getattr(sys, "frozen", False):
        result = update_frozen_app()
        if result.get("ok"):
            threading.Timer(0.8, _exit_soon).start()
        return jsonify(result)
    result = sync_from_live(install, force=True)
    if result.get("ok"):
        restart_desktop(install)
        threading.Timer(0.9, _exit_soon).start()
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


def main(argv: list[str] | None = None) -> int:
    global APP_PROC, WINDOW, _WINDOW_LIVE

    parser = argparse.ArgumentParser(description="SceneCut Pro+ Desktop")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "5000")))
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--no-update", action="store_true")
    parser.add_argument("--edge-fallback", action="store_true")
    args = parser.parse_args(argv)

    if not args.no_update and not getattr(sys, "frozen", False):
        if not (_install_dir() / "templates" / "home.html").exists():
            if _bootstrap_sync(force=True):
                _reexec()

    _ensure_dirs()
    _prepend_bundled_ffmpeg()
    try:
        man = remote_manifest()
        ver = str(man.get("version") or "")
        if ver:
            write_local_version(_install_dir(), ver)
    except Exception:  # noqa: BLE001
        pass

    port = _free_port(args.port)
    # STABLE desktop entry — app home only (never landing page)
    url = f"http://127.0.0.1:{port}/d"

    print("")
    print("  SceneCut Pro+")
    print("  CapCut-style native window")
    print(f"  {url}")
    print("")

    thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
    thread.start()
    if not _wait_until_up(port):
        print("ERROR: server start fail")
        return 1

    if args.browser:
        webbrowser.open(url)
        try:
            while not SHUTDOWN.is_set():
                time.sleep(0.25)
        except KeyboardInterrupt:
            pass
        return 0

    force_edge = args.edge_fallback or os.environ.get("SCENECUT_EDGE_FALLBACK") == "1"

    if not force_edge:
        ensure_webview_installed()
        WINDOW, ok = open_native_window(url, on_closed=_mark_window_dead)
        if ok and WINDOW is not None:
            _WINDOW_LIVE = True
            print("  Window: native (WebView2)")
            if start_native_gui():
                return 0
            # start failed after create
            _mark_window_dead()
            print("  Native GUI start fail — trying fallback…")

    # Fallback only
    print("  Fallback: Edge/Chrome app window")
    APP_PROC = open_app_window(url)
    if APP_PROC is None:
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

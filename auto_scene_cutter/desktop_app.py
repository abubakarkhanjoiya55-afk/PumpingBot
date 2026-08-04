"""
SceneCut Pro+ — desktop launcher

Stable Windows shell:
  - Sync latest code FIRST (before importing app) so /home never 404s
  - Edge/Chrome --app window
  - Local Flask for fast 2GB+ cuts
  - PowerShell file dialog for local paths

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
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


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
    """
    Update install files BEFORE importing app.
    Returns True if files changed (caller should re-exec).
    """
    if getattr(sys, "frozen", False):
        return False
    try:
        from desktop_update import sync_from_live

        result = sync_from_live(_install_dir(), force=force)
        if result.get("updated"):
            print(f"  Updated from live ({result.get('files')} files) — restarting…")
            return True
        if not result.get("ok"):
            print(f"  Update skip: {result.get('reason')}")
    except Exception as exc:  # noqa: BLE001
        print(f"  Update skip: {exc}")
    return False


def _reexec() -> None:
    """Restart this process so newly synced app.py is loaded."""
    script = str(Path(__file__).resolve())
    args = [sys.executable, script, "--no-update", *sys.argv[1:]]
    # Avoid infinite loop
    if "--no-update" not in sys.argv:
        os.execv(sys.executable, args)


# Optional early sync (skipped when --no-update already in argv during re-exec)
if "--no-update" not in sys.argv and "--help" not in sys.argv:
    if _bootstrap_sync(force=False):
        _reexec()


from flask import jsonify, request  # noqa: E402

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


def _http_ok(url: str) -> bool:
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "SceneCutPro-Desktop"})
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            return 200 <= getattr(resp, "status", 200) < 400
    except urllib.error.HTTPError as exc:
        return 200 <= exc.code < 400
    except Exception:  # noqa: BLE001
        return False


def _pick_working_url(port: int) -> str:
    """
    Prefer /d (short desktop entry), then /home, then /editor, then /.
    Avoids white Flask 404 when an old build is still somehow loaded.
    """
    candidates = [
        f"http://127.0.0.1:{port}/d",
        f"http://127.0.0.1:{port}/home",
        f"http://127.0.0.1:{port}/editor",
        f"http://127.0.0.1:{port}/",
    ]
    for url in candidates:
        if _http_ok(url):
            # Keep desktop flag for UI (query may be stripped by some --app parsers)
            if url.endswith("/d") or url.rstrip("/").endswith("/home"):
                return url if "desktop=" in url else (url + ("&" if "?" in url else "?") + "desktop=1")
            if url.endswith("/editor"):
                return url + "?desktop=1"
            return url + "?desktop=1" if "?" not in url else url
    return f"http://127.0.0.1:{port}/d"


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


def main(argv: list[str] | None = None) -> int:
    global APP_PROC
    parser = argparse.ArgumentParser(description="SceneCut Pro+ Desktop")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "5000")))
    parser.add_argument("--browser", action="store_true", help="Classic browser tab")
    parser.add_argument("--no-update", action="store_true")
    args = parser.parse_args(argv)

    # If launched without --no-update and files are stale, force one more sync+reexec
    if not args.no_update and not getattr(sys, "frozen", False):
        # Ensure home template exists; if not, force sync
        home_html = _install_dir() / "templates" / "home.html"
        if not home_html.exists() and _bootstrap_sync(force=True):
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

    print("")
    print("  SceneCut Pro+ Desktop")
    print("  Shell: Edge/Chrome app window")
    print("")

    thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
    thread.start()
    if not _wait_until_up(port):
        print("ERROR: local server start fail")
        return 1

    url = _pick_working_url(port)
    print(f"  Window: {url}")

    # If still 404 on /home|/d — force sync + restart once
    if (not _http_ok(f"http://127.0.0.1:{port}/d")) and (not _http_ok(f"http://127.0.0.1:{port}/home")):
        if not args.no_update and not getattr(sys, "frozen", False):
            print("  Local app outdated — forcing update…")
            if _bootstrap_sync(force=True):
                _kill_app_proc()
                _reexec()

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

"""
SceneCut Pro+ — CapCut-style desktop launcher

LOCKED (do not thrash again):
  1) Native pywebview window titled "SceneCut Pro+"  → CapCut / VLC feel
  2) NEVER open Microsoft Edge / Chrome browser automatically
  3) First paint = embedded CapCut home HTML (never black Flask 404)
  4) Local Flask for 2GB cuts + PowerShell file pick
  5) Do NOT stamp remote version unless files actually updated
  6) Edge --app= ONLY with --edge-fallback (emergency debug)

Usage:
  python desktop_app.py
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
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


def _log(msg: str) -> None:
    line = f"[SceneCut] {msg}"
    print(line)
    try:
        log_path = _install_dir() / "desktop.log"
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:  # noqa: BLE001
        pass


def _bootstrap_sync(force: bool = False) -> bool:
    if getattr(sys, "frozen", False):
        return False
    try:
        from desktop_update import sync_from_live

        result = sync_from_live(_install_dir(), force=force)
        if result.get("updated"):
            _log(f"Updated ({result.get('files')} files) — restarting…")
            return True
    except Exception as exc:  # noqa: BLE001
        _log(f"Update skip: {exc}")
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
    _html,
    _validate_upload_kind,
    app,
)
from desktop_shell import (  # noqa: E402
    open_app_window,
    open_native_window,
    pick_file_path,
    start_native_gui,
    wait_app_process,
    webview2_runtime_ok,
    win_message,
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

# Minimal CapCut-style home if templates are missing (broken / half-updated install)
_FALLBACK_HOME = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>SceneCut Pro+</title>
<style>
html,body{margin:0;height:100%;background:#0e0e10;color:#f4f4f5;
font-family:Segoe UI,system-ui,sans-serif}
.wrap{min-height:100%;display:grid;place-items:center;padding:32px}
h1{font-size:42px;margin:0 0 8px;letter-spacing:-.02em}
p{color:#a1a1aa;margin:0 0 24px}
a{display:inline-block;padding:14px 22px;border-radius:10px;background:#3b82f6;
color:#fff;text-decoration:none;font-weight:600}
</style></head>
<body><div class="wrap">
<div><h1>SceneCut Pro</h1>
<p>New project se editor kholo — CapCut jaisi start.</p>
<a href="/editor">+ New project</a>
</div></div></body></html>
"""


def _render_app_home():
    """Always return usable home HTML — never Werkzeug Not Found."""
    try:
        return _html("home.html")
    except Exception as exc:  # noqa: BLE001
        _log(f"home.html missing/fail: {exc}")
        return _FALLBACK_HOME, 200, {"Content-Type": "text/html; charset=utf-8"}


def _bind_route(path: str, endpoint: str, view) -> None:
    """Ensure path serves view (override stale/missing routes)."""
    existing = [r for r in app.url_map.iter_rules() if r.rule == path]
    if existing:
        for rule in existing:
            app.view_functions[rule.endpoint] = view
        return
    app.add_url_rule(path, endpoint, view)


def _install_guaranteed_desktop_routes() -> None:
    """
    Black-screen fix: even if local app.py is old/missing /d,
    these routes (registered by the launcher) always serve home.
    """
    _bind_route("/start", "sc_desktop_start", _render_app_home)
    _bind_route("/d", "sc_desktop_d", _render_app_home)
    _bind_route("/home", "sc_desktop_home", _render_app_home)
    _bind_route("/app", "sc_desktop_app", _render_app_home)

    @app.errorhandler(404)
    def _desktop_never_black(_err):  # noqa: ANN001
        path = request.path or ""
        if path.startswith("/api/") or path.startswith("/media/"):
            return jsonify({"error": "Not found"}), 404
        return _render_app_home()


_install_guaranteed_desktop_routes()


def _bundled_version() -> str:
    try:
        raw = json.loads((BASE_DIR / "version.json").read_text(encoding="utf-8"))
        return str(raw.get("version") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _clear_version_marker() -> None:
    try:
        marker = _install_dir() / ".scenecut_version"
        if marker.exists():
            marker.unlink()
    except OSError:
        pass


def _repair_stale_install_if_needed() -> None:
    """If home template /d route missing, force live sync once (python installs)."""
    if getattr(sys, "frozen", False):
        return
    home_tpl = _install_dir() / "templates" / "home.html"
    app_py = _install_dir() / "app.py"
    broken = (not home_tpl.is_file()) or (not app_py.is_file())
    if not broken and app_py.is_file():
        try:
            text = app_py.read_text(encoding="utf-8", errors="ignore")
            if '@app.get("/d")' not in text and "@app.get('/d')" not in text:
                broken = True
        except OSError:
            broken = True
    if not broken:
        return
    _log("Stale/broken install detected — clearing version marker + force sync")
    _clear_version_marker()
    if _bootstrap_sync(force=True):
        _reexec()


def _boot_html(port: int) -> str:
    """Embedded CapCut home — first paint never depends on Flask routes."""
    path = BASE_DIR / "desktop_boot.html"
    if path.is_file():
        text = path.read_text(encoding="utf-8")
    else:
        text = _FALLBACK_HOME.replace('href="/editor"', f'href="http://127.0.0.1:{port}/editor"')
        return text
    return text.replace("__SC_PORT__", str(port))


def _maybe_upgrade_frozen() -> bool:
    """
    If this Setup.exe is older than live, download+run new Setup silently.
    Returns True if upgrade started (caller should exit).
    """
    if not getattr(sys, "frozen", False):
        return False
    try:
        man = remote_manifest()
        remote = str(man.get("version") or "").strip()
        local = _bundled_version()
        if not remote or not local or remote == local:
            return False
        _log(f"Frozen upgrade {local} → {remote}")
        win_message(
            "SceneCut Pro+",
            f"New version {remote} mil gaya.\nUpdate install ho raha hai — 20-40 sec wait…",
            0x40,
        )
        result = update_frozen_app(man)
        if result.get("ok"):
            return True
        _log(f"Frozen upgrade fail: {result}")
    except Exception as exc:  # noqa: BLE001
        _log(f"Frozen upgrade skip: {exc}")
    return False


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


def _http_ok(url: str, timeout: float = 2.0) -> bool:
    import urllib.request

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SceneCutPro-Desktop"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(800).decode("utf-8", errors="ignore")
            if resp.status != 200:
                return False
            if "The requested URL was not found" in body:
                return False
            return True
    except Exception:  # noqa: BLE001
        return False


def _pick_entry_url(port: int) -> str:
    """Pick first working app-home URL (never open a 404 page)."""
    for path in ("/start", "/d", "/home", "/app", "/editor"):
        url = f"http://127.0.0.1:{port}{path}"
        if _http_ok(url):
            return url
    # Last resort — /start still has our guaranteed handler
    return f"http://127.0.0.1:{port}/start"


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
            "shell": "native" if _WINDOW_LIVE else ("edge-debug" if APP_PROC else "server"),
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


def _native_fail_message() -> str:
    setup = (
        "https://scenecut-production.up.railway.app/download"
    )
    return (
        "SceneCut Pro+ native window start nahi hua.\n\n"
        "Yeh Microsoft Edge browser NAHI kholega (CapCut jaisa app chahiye).\n\n"
        "Fix:\n"
        "1) Naya Setup.exe install karo:\n"
        f"   {setup}\n"
        "2) Phir Desktop shortcut 'SceneCut Pro+' se kholo.\n\n"
        "Agar WebView2 missing ho to Windows Update / Edge update chalao."
    )


def main(argv: list[str] | None = None) -> int:
    global APP_PROC, WINDOW, _WINDOW_LIVE

    parser = argparse.ArgumentParser(description="SceneCut Pro+ Desktop")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "5000")))
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Debug only: open default browser (not for students)",
    )
    parser.add_argument("--no-update", action="store_true")
    parser.add_argument(
        "--edge-fallback",
        action="store_true",
        help="Emergency only: Edge --app= (looks like browser)",
    )
    args = parser.parse_args(argv)

    if not args.no_update:
        if getattr(sys, "frozen", False):
            if _maybe_upgrade_frozen():
                # Silent Setup running — exit so installer can replace files
                time.sleep(1.0)
                return 0
        else:
            if not (_install_dir() / "templates" / "home.html").exists():
                _clear_version_marker()
                if _bootstrap_sync(force=True):
                    _reexec()
            _repair_stale_install_if_needed()

    _ensure_dirs()
    _prepend_bundled_ffmpeg()
    # Only record the version that is actually bundled/running — never stamp remote
    # version onto a stale install (that caused permanent black 404).
    bundled = _bundled_version()
    if bundled:
        write_local_version(_install_dir(), bundled)

    port = _free_port(args.port)
    boot = _boot_html(port)
    url = f"http://127.0.0.1:{port}/start"

    print("")
    print("  SceneCut Pro+")
    print("  CapCut-style native window (embedded home)")
    print(f"  engine: {url}")
    print("")
    _log(f"Boot HTML bytes={len(boot)} engine={url}")

    thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
    thread.start()
    # Don't block UI on slow server — embedded home shows immediately.
    # Still wait briefly so New project API is likely ready.
    _wait_until_up(port, timeout=8.0)

    # Debug browser path only
    if args.browser:
        import webbrowser

        webbrowser.open(_pick_entry_url(port) if _wait_until_up(port, 2.0) else url)
        try:
            while not SHUTDOWN.is_set():
                time.sleep(0.25)
        except KeyboardInterrupt:
            pass
        return 0

    force_edge = args.edge_fallback or os.environ.get("SCENECUT_EDGE_FALLBACK") == "1"

    # ——— PRIMARY: native CapCut-like window with EMBEDDED home ———
    if not force_edge:
        ready = ensure_webview_installed()
        if not ready:
            _log("pywebview/pythonnet install failed")
        if not webview2_runtime_ok():
            _log("WebView2 runtime not detected")

        WINDOW, ok = open_native_window(
            url=url,
            html=boot,
            on_closed=_mark_window_dead,
        )
        if ok and WINDOW is not None:
            _WINDOW_LIVE = True
            _log("Window: native WebView2 + embedded CapCut home")
            if start_native_gui():
                return 0
            _mark_window_dead()
            _log("Native GUI start failed")

        # Do NOT open Edge. Show clear fix message.
        win_message("SceneCut Pro+", _native_fail_message(), 0x30)
        return 2

    # ——— Emergency Edge path (explicit flag only) ———
    _log("EMERGENCY edge-fallback requested")
    APP_PROC = open_app_window(url)
    if APP_PROC is None:
        win_message(
            "SceneCut Pro+",
            "Edge fallback bhi fail. Naya Setup.exe install karo.",
            0x10,
        )
        return 3
    try:
        wait_app_process(APP_PROC, SHUTDOWN)
    except KeyboardInterrupt:
        SHUTDOWN.set()
        _kill_app_proc()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

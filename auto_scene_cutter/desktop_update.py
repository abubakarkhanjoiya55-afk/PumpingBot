"""
SceneCut Pro+ desktop updater

- Sync install folder from live student pack
- Download + run Setup.exe silently (frozen builds)
- CapCut-style version checks via /api/version
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path

DEFAULT_LIVE = "https://scenecut-production.up.railway.app"
SKIP_DIR_NAMES = {
    ".venv",
    "venv",
    ".git",
    "output",
    "_uploads",
    "projects",
    "releases",
    "dist",
    "build",
    "tools",
    "__pycache__",
}


def live_base() -> str:
    return (os.environ.get("SCENECUT_LIVE_URL") or DEFAULT_LIVE).rstrip("/")


def sys_executable() -> str:
    return sys.executable


def fetch_json(url: str, timeout: float = 8.0) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SceneCutPro-Desktop"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def is_online(timeout: float = 4.0) -> bool:
    data = fetch_json(f"{live_base()}/health", timeout=timeout)
    return bool(data and data.get("ok"))


def remote_manifest() -> dict:
    return fetch_json(f"{live_base()}/api/version", timeout=8.0) or {}


def remote_version() -> str:
    data = remote_manifest()
    return str(data.get("version") or data.get("asset_v") or "")


def local_version(install_dir: Path) -> str:
    marker = Path(install_dir) / ".scenecut_version"
    if marker.exists():
        return marker.read_text(encoding="utf-8").strip()
    return ""


def write_local_version(install_dir: Path, version: str) -> None:
    try:
        (Path(install_dir) / ".scenecut_version").write_text(version or "", encoding="utf-8")
    except OSError:
        pass


def _should_skip(rel: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in rel.parts)


def apply_student_pack_zip(zip_bytes: bytes, install_dir: Path) -> int:
    install_dir = Path(install_dir)
    install_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        prefix = ""
        for n in names:
            if n.endswith("app.py"):
                prefix = n[: -len("app.py")]
                break
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if prefix and name.startswith(prefix):
                rel = Path(name[len(prefix) :])
            else:
                rel = Path(name.split("/", 1)[-1]) if "/" in name else Path(name)
            if not rel.parts or _should_skip(rel):
                continue
            dest = install_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            count += 1
    return count


def sync_from_live(install_dir: Path, force: bool = False) -> dict:
    install_dir = Path(install_dir)
    if not is_online():
        return {"ok": False, "updated": False, "reason": "offline"}

    manifest = remote_manifest()
    ver = str(manifest.get("version") or manifest.get("asset_v") or "")
    cur = local_version(install_dir)
    if not force and ver and cur and ver == cur:
        return {"ok": True, "updated": False, "version": ver, "reason": "current"}

    url = f"{live_base()}/api/download/student-pack"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SceneCutPro-Desktop"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            blob = resp.read()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "updated": False, "reason": f"download fail: {exc}"}

    try:
        n = apply_student_pack_zip(blob, install_dir)
        if ver:
            write_local_version(install_dir, ver)
        return {
            "ok": True,
            "updated": True,
            "files": n,
            "version": ver,
            "title": manifest.get("title"),
            "notes": manifest.get("notes") or [],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "updated": False, "reason": f"extract fail: {exc}"}


def download_setup_exe(setup_url: str, dest: Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(setup_url, headers={"User-Agent": "SceneCutPro-Desktop"})
    with urllib.request.urlopen(req, timeout=300) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)
    return dest


def run_silent_setup(setup_path: Path) -> None:
    """Inno Setup silent install over existing app."""
    flags = [
        str(setup_path),
        "/VERYSILENT",
        "/CLOSEAPPLICATIONS",
        "/RESTARTAPPLICATIONS",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
    ]
    subprocess.Popen(flags, close_fds=True)


def update_frozen_app(manifest: dict | None = None) -> dict:
    manifest = manifest or remote_manifest()
    setup_url = str(manifest.get("setup_url") or manifest.get("setup_exe") or "").strip()
    if not setup_url.startswith("http"):
        setup_url = (
            "https://github.com/abubakarkhanjoiya55-afk/PumpingBot/"
            "releases/download/scenecut-desktop/SceneCutPro-Setup.exe"
        )
    try:
        dest = Path(tempfile.gettempdir()) / "SceneCutPro-Setup.exe"
        download_setup_exe(setup_url, dest)
        run_silent_setup(dest)
        return {"ok": True, "action": "setup_silent", "path": str(dest)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": str(exc)}


def ensure_webview_installed() -> bool:
    try:
        import webview  # noqa: F401

        return True
    except ImportError:
        pass
    try:
        subprocess.run(
            [sys_executable(), "-m", "pip", "install", "-q", "pywebview"],
            check=False,
            timeout=180,
        )
        import webview  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def restart_desktop(install_dir: Path) -> None:
    """Relaunch desktop after file sync."""
    install_dir = Path(install_dir)
    vbs = install_dir / "desktop" / "LaunchSilent.vbs"
    exe = install_dir / "SceneCutProPlus.exe"
    bat = install_dir / "desktop" / "Launch.bat"

    def _launch() -> None:
        try:
            if exe.exists():
                subprocess.Popen([str(exe)], cwd=str(install_dir), close_fds=True)
            elif vbs.exists():
                subprocess.Popen(
                    ["wscript.exe", str(vbs)],
                    cwd=str(install_dir),
                    close_fds=True,
                )
            elif bat.exists():
                subprocess.Popen(
                    ["cmd.exe", "/c", str(bat)],
                    cwd=str(install_dir),
                    close_fds=True,
                )
        except Exception:  # noqa: BLE001
            pass

    threading.Timer(0.6, _launch).start()

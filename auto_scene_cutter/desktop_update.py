"""
Pull latest SceneCut UI/code into a desktop install folder.

Used so installed desktop apps stay in sync with the live site
without opening a browser.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
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


def remote_version() -> str:
    data = fetch_json(f"{live_base()}/api/version", timeout=6.0) or {}
    return str(data.get("version") or data.get("asset_v") or "")


def local_version(install_dir: Path) -> str:
    marker = install_dir / ".scenecut_version"
    if marker.exists():
        return marker.read_text(encoding="utf-8").strip()
    return ""


def write_local_version(install_dir: Path, version: str) -> None:
    try:
        (install_dir / ".scenecut_version").write_text(version or "", encoding="utf-8")
    except OSError:
        pass


def _should_skip(rel: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in rel.parts)


def apply_student_pack_zip(zip_bytes: bytes, install_dir: Path) -> int:
    """Extract SceneCut-Pro-Student.zip into install_dir. Returns file count."""
    install_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        # ZIP root is usually SceneCut-Pro-Student/...
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


def sync_from_live(install_dir: Path) -> dict:
    """
    Download live student pack and refresh install_dir when version differs.
    Safe no-op when offline / already current.
    """
    install_dir = Path(install_dir)
    if not is_online():
        return {"ok": False, "updated": False, "reason": "offline"}

    ver = remote_version()
    cur = local_version(install_dir)
    if ver and cur and ver == cur:
        return {"ok": True, "updated": False, "version": ver, "reason": "current"}

    url = f"{live_base()}/api/download/student-pack"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SceneCutPro-Desktop"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            blob = resp.read()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "updated": False, "reason": f"download fail: {exc}"}

    try:
        n = apply_student_pack_zip(blob, install_dir)
        if ver:
            write_local_version(install_dir, ver)
        return {"ok": True, "updated": True, "files": n, "version": ver}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "updated": False, "reason": f"extract fail: {exc}"}


def ensure_webview_installed() -> bool:
    try:
        import webview  # noqa: F401

        return True
    except ImportError:
        pass
    try:
        import subprocess

        subprocess.run(
            [sys_executable(), "-m", "pip", "install", "-q", "pywebview"],
            check=False,
            timeout=180,
        )
        import webview  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def sys_executable() -> str:
    import sys

    return sys.executable

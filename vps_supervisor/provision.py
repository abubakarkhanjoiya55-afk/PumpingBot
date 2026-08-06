"""
Provision a portable MetaTrader 5 instance per MT5 login on the Windows VPS.

Each user needs their own terminal folder so many accounts can trade at once.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))


def template_dir() -> Path:
    return _env_path("MT5_TEMPLATE_DIR", r"C:\PumpingBot\MT5_Template")


def instances_root() -> Path:
    return _env_path("MT5_INSTANCES_DIR", r"C:\PumpingBot\MT5_Instances")


def instance_dir(login: int | str) -> Path:
    return instances_root() / str(login)


def terminal_exe(login: int | str) -> Path:
    return instance_dir(login) / "terminal64.exe"


def _clear_readonly(path: Path) -> None:
    try:
        if path.exists():
            os.chmod(path, 0o666)
    except Exception:
        pass


def ensure_portable_marker(dest: Path) -> None:
    """Create/repair empty 'portable' file (no extension). Ignore read-only copies."""
    marker = dest / "portable"
    if marker.is_dir():
        shutil.rmtree(marker, ignore_errors=True)
    if marker.is_file():
        _clear_readonly(marker)
        return
    try:
        marker.write_text("", encoding="utf-8")
    except PermissionError:
        _clear_readonly(marker)
        marker.write_text("", encoding="utf-8")


def ensure_portable_instance(login: int | str) -> Path:
    """
    Clone portable MT5 template -> C:\\PumpingBot\\MT5_Instances\\{login}
    Returns path to terminal64.exe
    """
    dest = instance_dir(login)
    exe = terminal_exe(login)
    if exe.is_file():
        ensure_portable_marker(dest)
        return exe

    src = template_dir()
    if not (src / "terminal64.exe").is_file():
        raise FileNotFoundError(
            f"MT5 template missing at {src}\\terminal64.exe - "
            "install portable MT5 there first (see vps_supervisor/README.md)"
        )

    instances_root().mkdir(parents=True, exist_ok=True)
    print(f"[PROVISION] Cloning MT5 template -> {dest}")
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)

    # dirs_exist_ok needs py3.8+
    shutil.copytree(src, dest)

    # Clear read-only flags Windows often copies from Program Files
    for p in dest.rglob("*"):
        _clear_readonly(p)

    # Portable mode marker - keeps data inside this folder
    ensure_portable_marker(dest)
    if not exe.is_file():
        raise FileNotFoundError(f"terminal64.exe not found after clone: {exe}")
    return exe


def _normalize_win_path(path: str | Path) -> str:
    return str(path).lower().replace("/", "\\").rstrip("\\")


def _running_terminal_paths() -> list[str]:
    """Executable paths of running terminal64.exe processes (Windows)."""
    paths: list[str] = []
    try:
        # Prefer path-aware query so multi-user portable instances are distinct.
        r = subprocess.run(
            [
                "wmic",
                "process",
                "where",
                "name='terminal64.exe'",
                "get",
                "ExecutablePath",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if not line or line.lower() == "executablepath":
                continue
            if line.lower().endswith("terminal64.exe"):
                paths.append(_normalize_win_path(line))
    except Exception:
        pass
    if paths:
        return paths
    # Fallback: only know that *some* terminal exists (no path detail).
    try:
        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq terminal64.exe", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        if "terminal64.exe" in (r.stdout or "").lower():
            return ["*"]
    except Exception:
        pass
    return []


def _this_instance_running(exe: Path) -> bool:
    """True only if THIS login's portable terminal64.exe is already running."""
    target = _normalize_win_path(exe)
    running = _running_terminal_paths()
    if not running:
        return False
    if running == ["*"]:
        # Path unknown — do NOT treat as this instance; allow launch for multi-user.
        return False
    return target in running


def start_terminal(login: int | str) -> subprocess.Popen | None:
    """
    Launch this login's portable terminal minimized.

    Multi-user VPS: each MT5 login gets its own portable folder/process.
    Only skip launch when THIS login's terminal64.exe is already running.
    (Older logic skipped whenever ANY terminal64 was open — that blocked all
    followers after Admin99's master terminal started.)
    """
    exe = ensure_portable_instance(login)
    if _this_instance_running(exe):
        print(
            f"[PROVISION] This instance already running for {login} - "
            f"reuse {exe} (no second launch of same portable)"
        )
        time.sleep(2)
        return None
    try:
        # /portable is implied by portable file; start minimized
        proc = subprocess.Popen(
            [str(exe), "/portable"],
            cwd=str(exe.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )
        # Give terminal time to boot before Python API attaches (IPC needs this)
        time.sleep(float(os.environ.get("MT5_BOOT_WAIT_SEC", "20")))
        return proc
    except Exception as e:
        print(f"[PROVISION] start_terminal({login}) failed: {e}")
        return None

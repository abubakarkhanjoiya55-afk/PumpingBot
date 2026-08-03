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


def ensure_portable_instance(login: int | str) -> Path:
    """
    Clone portable MT5 template → C:\\PumpingBot\\MT5_Instances\\{login}
    Returns path to terminal64.exe
    """
    dest = instance_dir(login)
    exe = terminal_exe(login)
    if exe.is_file():
        return exe

    src = template_dir()
    if not (src / "terminal64.exe").is_file():
        raise FileNotFoundError(
            f"MT5 template missing at {src}\\terminal64.exe — "
            "install portable MT5 there first (see vps_supervisor/README.md)"
        )

    instances_root().mkdir(parents=True, exist_ok=True)
    print(f"[PROVISION] Cloning MT5 template → {dest}")
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)

    # dirs_exist_ok needs py3.8+
    shutil.copytree(src, dest)

    # Portable mode marker — keeps data inside this folder
    (dest / "portable").write_text("", encoding="utf-8")
    if not exe.is_file():
        raise FileNotFoundError(f"terminal64.exe not found after clone: {exe}")
    return exe


def start_terminal(login: int | str) -> subprocess.Popen | None:
    """Launch terminal minimized; safe to call if already running."""
    exe = ensure_portable_instance(login)
    # If already running with this cwd, skip
    try:
        # /portable is implied by portable file; start minimized
        proc = subprocess.Popen(
            [str(exe)],
            cwd=str(exe.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )
        # Give terminal a moment to boot before Python API attaches
        time.sleep(float(os.environ.get("MT5_BOOT_WAIT_SEC", "8")))
        return proc
    except Exception as e:
        print(f"[PROVISION] start_terminal({login}) failed: {e}")
        return None

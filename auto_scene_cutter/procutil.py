"""
Windows-safe subprocess helpers.

ffmpeg.exe is a console app. Without CREATE_NO_WINDOW it pops a black CMD
window; closing that window can kill the whole SceneCut desktop process
(CTRL_CLOSE_EVENT to the process group). Always hide console on Windows.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any


def windows_hide_kwargs() -> dict[str, Any]:
    if not sys.platform.startswith("win"):
        return {}
    kwargs: dict[str, Any] = {}
    create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    kwargs["creationflags"] = create_no_window
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        kwargs["startupinfo"] = startupinfo
    except Exception:  # noqa: BLE001
        pass
    return kwargs


def run_hidden(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    """subprocess.run with console hidden on Windows."""
    merged = dict(kwargs)
    for key, value in windows_hide_kwargs().items():
        merged.setdefault(key, value)
    return subprocess.run(cmd, **merged)

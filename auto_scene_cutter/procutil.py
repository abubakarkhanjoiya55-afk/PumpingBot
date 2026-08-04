"""
Windows-safe subprocess helpers.

ffmpeg.exe is a console subsystem app. Without CREATE_NO_WINDOW it pops a
black CMD window. Closing that window sends CTRL_CLOSE_EVENT and can kill
the whole SceneCut desktop process. Always hide the console on Windows.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

# Windows process creation flags
_CREATE_NO_WINDOW = 0x08000000


def windows_hide_kwargs() -> dict[str, Any]:
    if not sys.platform.startswith("win"):
        return {}
    kwargs: dict[str, Any] = {
        "creationflags": int(getattr(subprocess, "CREATE_NO_WINDOW", _CREATE_NO_WINDOW)),
        "stdin": subprocess.DEVNULL,
    }
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        kwargs["startupinfo"] = startupinfo
    except Exception:  # noqa: BLE001
        pass
    return kwargs


def run_hidden(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    """subprocess.run with console forced-hidden on Windows."""
    merged = dict(kwargs)
    hide = windows_hide_kwargs()
    if hide:
        # FORCE hide — never allow a visible ffmpeg/cmd console
        flags = int(merged.pop("creationflags", 0) or 0)
        flags |= int(hide["creationflags"])
        merged["creationflags"] = flags
        if "startupinfo" in hide:
            merged["startupinfo"] = hide["startupinfo"]
        # Don't steal/attach a console via stdin
        merged.setdefault("stdin", hide["stdin"])
    return subprocess.run(cmd, **merged)

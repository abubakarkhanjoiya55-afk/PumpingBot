"""
Stable Windows desktop shell without pywebview/.NET 'master' crashes.

1) Microsoft Edge / Chrome --app= window (real app frame, no tabs)
2) PowerShell OpenFileDialog for local multi‑GB paths (no upload)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

_EDGE_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
)
_CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
)

_FILTERS = {
    "movie": "Video files|*.mp4;*.mov;*.mkv;*.webm;*.avi;*.m4v|All files|*.*",
    "movie_srt": "Subtitle files|*.srt;*.txt|All files|*.*",
    "narration_srt": "Subtitle files|*.srt;*.txt|All files|*.*",
    "narration_audio": "Audio files|*.mp3;*.m4a;*.wav;*.aac;*.ogg;*.flac|All files|*.*",
}


def _first_existing(paths: tuple[str, ...]) -> str | None:
    for p in paths:
        if p and Path(p).is_file():
            return p
    # PATH lookup
    for name in ("msedge", "msedge.exe", "chrome", "chrome.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def find_app_browser() -> tuple[str, str] | None:
    """Return (exe, kind) where kind is edge|chrome."""
    edge = _first_existing(_EDGE_CANDIDATES)
    if edge:
        return edge, "edge"
    chrome = _first_existing(_CHROME_CANDIDATES)
    if chrome:
        return chrome, "chrome"
    return None


def open_app_window(url: str) -> subprocess.Popen | None:
    """
    Open a tab-less app window. Returns the Popen handle (wait on it),
    or None if no Edge/Chrome found.
    """
    found = find_app_browser()
    if not found:
        return None
    exe, kind = found
    # Dedicated profile so it doesn't clash with user's normal browser session
    profile = Path(os.environ.get("LOCALAPPDATA") or ".") / "SceneCutProPlus" / "app_profile"
    profile.mkdir(parents=True, exist_ok=True)
    args = [
        exe,
        f"--app={url}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--new-window",
    ]
    # Windows: hide console; browser is GUI
    creation = 0
    if sys.platform.startswith("win"):
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        # DETACHED so pythonw isn't tied oddly — still wait via Popen
        creation |= getattr(subprocess, "DETACHED_PROCESS", 0)
        # Actually DETACHED_PROCESS can break wait(); use CREATE_NEW_PROCESS_GROUP only
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        return subprocess.Popen(args, close_fds=True, creationflags=creation)
    except Exception:  # noqa: BLE001
        try:
            return subprocess.Popen(args, close_fds=True)
        except Exception:  # noqa: BLE001
            return None


def pick_file_path(kind: str) -> str | None:
    """Native WinForms OpenFileDialog via PowerShell STA — no pywebview."""
    if not sys.platform.startswith("win"):
        return None
    filt = _FILTERS.get(kind) or "All files|*.*"
    # Escape for PowerShell single-quoted string
    filt_ps = filt.replace("'", "''")
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
$d = New-Object System.Windows.Forms.OpenFileDialog
$d.Filter = '{filt_ps}'
$d.Multiselect = $false
$d.Title = 'SceneCut Pro+ — Select file'
[System.Windows.Forms.Application]::EnableVisualStyles() | Out-Null
$code = $d.ShowDialog()
if ($code -eq [System.Windows.Forms.DialogResult]::OK) {{
  Write-Output $d.FileName
}}
"""
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-STA",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except Exception:  # noqa: BLE001
        return None
    path = (proc.stdout or "").strip().splitlines()
    if not path:
        return None
    candidate = path[-1].strip()
    if candidate and Path(candidate).is_file():
        return candidate
    return None


def wait_app_process(proc: subprocess.Popen, shutdown_event, poll: float = 0.4) -> None:
    """Block until app window process exits or shutdown_event is set."""
    try:
        while True:
            if shutdown_event is not None and shutdown_event.is_set():
                try:
                    proc.terminate()
                except Exception:  # noqa: BLE001
                    pass
                break
            code = proc.poll()
            if code is not None:
                break
            time.sleep(poll)
    finally:
        if shutdown_event is not None:
            shutdown_event.set()

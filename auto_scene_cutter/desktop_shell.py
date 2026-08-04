"""
Desktop window helpers.

Primary: pywebview native window (CapCut-like, not a browser).
Fallback: Edge/Chrome --app= only if native window cannot start.
File pick: PowerShell OpenFileDialog (stable, no pywebview destroy bugs).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

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
    for name in ("msedge", "msedge.exe", "chrome", "chrome.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def find_app_browser() -> tuple[str, str] | None:
    edge = _first_existing(_EDGE_CANDIDATES)
    if edge:
        return edge, "edge"
    chrome = _first_existing(_CHROME_CANDIDATES)
    if chrome:
        return chrome, "chrome"
    return None


def open_native_window(url: str, on_closed: Callable[[], None] | None = None):
    """
    Create a CapCut-like native window with pywebview.
    Returns (window, True) or (None, False).
    Caller must call webview.start() afterward.
    """
    try:
        import webview
    except ImportError:
        return None, False

    try:
        window = webview.create_window(
            "SceneCut Pro+",
            url,
            width=1360,
            height=860,
            min_size=(1100, 700),
            background_color="#0e0e10",
            text_select=True,
            confirm_close=False,
        )

        if on_closed is not None:
            try:
                window.events.closed += on_closed
            except Exception:  # noqa: BLE001
                pass

        return window, True
    except Exception:  # noqa: BLE001
        return None, False


def start_native_gui() -> bool:
    """Block until native window closes. Returns False if start failed."""
    try:
        import webview
    except ImportError:
        return False
    try:
        # edgechromium = real app window using WebView2 (not Edge browser UI)
        webview.start(gui="edgechromium", debug=False)
        return True
    except Exception:
        try:
            webview.start(debug=False)
            return True
        except Exception:  # noqa: BLE001
            return False


def open_app_window(url: str) -> subprocess.Popen | None:
    """Last-resort Edge/Chrome --app window (only if native fails)."""
    found = find_app_browser()
    if not found:
        return None
    exe, _kind = found
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
    creation = 0
    if sys.platform.startswith("win"):
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        return subprocess.Popen(args, close_fds=True, creationflags=creation)
    except Exception:  # noqa: BLE001
        try:
            return subprocess.Popen(args, close_fds=True)
        except Exception:  # noqa: BLE001
            return None


def pick_file_path(kind: str) -> str | None:
    """Native WinForms OpenFileDialog via PowerShell STA."""
    if not sys.platform.startswith("win"):
        return None
    filt = _FILTERS.get(kind) or "All files|*.*"
    filt_ps = filt.replace("'", "''")
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
$d = New-Object System.Windows.Forms.OpenFileDialog
$d.Filter = '{filt_ps}'
$d.Multiselect = $false
$d.Title = 'SceneCut Pro+ — Select file'
[System.Windows.Forms.Application]::EnableVisualStyles() | Out-Null
if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
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
    lines = (proc.stdout or "").strip().splitlines()
    if not lines:
        return None
    candidate = lines[-1].strip()
    if candidate and Path(candidate).is_file():
        return candidate
    return None


def wait_app_process(proc: subprocess.Popen, shutdown_event, poll: float = 0.4) -> None:
    try:
        while True:
            if shutdown_event is not None and shutdown_event.is_set():
                try:
                    proc.terminate()
                except Exception:  # noqa: BLE001
                    pass
                break
            if proc.poll() is not None:
                break
            time.sleep(poll)
    finally:
        if shutdown_event is not None:
            shutdown_event.set()

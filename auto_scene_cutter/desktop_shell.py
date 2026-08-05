"""
Desktop window helpers — LOCKED contract (do not thrash):

  PRIMARY: pywebview + WebView2 native window titled "SceneCut Pro+"
           (CapCut-like app window — NOT Microsoft Edge browser UI)
  NEVER auto-open msedge.exe / chrome.exe / webbrowser
  File pick: PowerShell OpenFileDialog (stable, no pywebview destroy bugs)

Edge --app= exists only behind explicit force_edge=True for emergency debug.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable


_FILTERS = {
    "movie": "Video files|*.mp4;*.mov;*.mkv;*.webm;*.avi;*.m4v|All files|*.*",
    "movie_srt": "Subtitle files|*.srt;*.txt|All files|*.*",
    "narration_srt": "Subtitle files|*.srt;*.txt|All files|*.*",
    "narration_audio": "Audio files|*.mp3;*.m4a;*.wav;*.aac;*.ogg;*.flac|All files|*.*",
}


def win_message(title: str, text: str, icon: int = 0x40) -> None:
    """Show a native Windows MessageBox (no browser)."""
    if not sys.platform.startswith("win"):
        print(f"{title}: {text}")
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, str(text), str(title), int(icon))
    except Exception:  # noqa: BLE001
        print(f"{title}: {text}")


def webview2_runtime_ok() -> bool:
    """True if WebView2 Evergreen runtime looks installed."""
    if not sys.platform.startswith("win"):
        return True
    try:
        import winreg
    except ImportError:
        return True
    keys = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
    )
    for hive, path in keys:
        try:
            with winreg.OpenKey(hive, path) as key:
                ver, _ = winreg.QueryValueEx(key, "pv")
                if ver and str(ver) not in ("", "0.0.0.0"):
                    return True
        except OSError:
            continue
    # Edge browser install usually ships WebView2 bits too
    for p in (
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ):
        if Path(p).is_file():
            return True
    return False


def open_native_window(
    url: str | None = None,
    on_closed: Callable[[], None] | None = None,
    html: str | None = None,
):
    """
    Create CapCut-like native window (WebView2 engine, custom title bar).

    Prefer html= for first paint so a bad local URL can never show black 404.
    Returns (window, True) or (None, False).
    Caller must call start_native_gui() afterward.
    """
    try:
        import webview
    except ImportError:
        return None, False

    # Keep WebView2 profile under our app folder (not Edge browser profile)
    profile = Path(os.environ.get("LOCALAPPDATA") or ".") / "SceneCutProPlus" / "webview2"
    try:
        profile.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("WEBVIEW2_USER_DATA_FOLDER", str(profile))
    except Exception:  # noqa: BLE001
        pass

    common = dict(
        width=1360,
        height=860,
        min_size=(1100, 700),
        background_color="#0e0e10",
        text_select=True,
        confirm_close=False,
        easy_drag=False,
    )
    try:
        # html= embeds CapCut home directly — never depends on Flask /d route
        if html:
            window = webview.create_window("SceneCut Pro+", html=html, **common)
        else:
            window = webview.create_window("SceneCut Pro+", url or "about:blank", **common)
        if on_closed is not None:
            try:
                window.events.closed += on_closed
            except Exception:  # noqa: BLE001
                pass
        return window, True
    except TypeError:
        # Older pywebview without html= support
        if not url:
            return None, False
        try:
            window = webview.create_window("SceneCut Pro+", url, **common)
            if on_closed is not None:
                try:
                    window.events.closed += on_closed
                except Exception:  # noqa: BLE001
                    pass
            return window, True
        except Exception:  # noqa: BLE001
            return None, False
    except Exception:  # noqa: BLE001
        return None, False


def start_native_gui() -> bool:
    """Block until native window closes. Returns False if start failed."""
    try:
        import webview
    except ImportError:
        return False

    # Prefer WebView2 host (looks like real app). Never use Edge browser chrome.
    for gui in ("edgechromium", None):
        try:
            if gui:
                webview.start(gui=gui, debug=False, private_mode=False)
            else:
                webview.start(debug=False, private_mode=False)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def open_app_window(url: str) -> subprocess.Popen | None:
    """
    EMERGENCY ONLY — Edge/Chrome --app= (looks like browser).
    Do not call from normal launch path.
    """
    candidates = (
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    )
    exe = next((p for p in candidates if Path(p).is_file()), None)
    if not exe:
        return None
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
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0
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

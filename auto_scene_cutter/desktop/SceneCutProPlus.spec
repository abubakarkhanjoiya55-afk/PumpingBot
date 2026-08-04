# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — build on Windows (CI or desktop\build_exe.bat)

import sys
from pathlib import Path

try:
    from PyInstaller.utils.hooks import collect_all, collect_submodules
except Exception:  # noqa: BLE001
    collect_all = None
    collect_submodules = None

block_cipher = None
# SPECPATH = auto_scene_cutter/desktop  → app root is parent
ROOT = Path(SPECPATH).resolve().parent

datas = [
    (str(ROOT / "templates"), "templates"),
    (str(ROOT / "static"), "static"),
    (str(ROOT / "sample_movie.srt"), "."),
    (str(ROOT / "sample_movie_cluster.srt"), "."),
    (str(ROOT / "sample_narration.srt"), "."),
    (str(ROOT / "config.json"), "."),
    (str(ROOT / "version.json"), "."),
]
binaries = []
hiddenimports = [
    "pysrt",
    "flask",
    "waitress",
    "webview",
    "desktop_update",
    "export_engine",
    "cutting_engine",
    "matching_engine",
    "pro_plus",
    "final_render",
    "scene_matcher",
    "scene_clustering",
    "srt_parser",
    "video_cutter",
    "presets",
    "config",
    "progress",
    "report",
    "project",
]

if collect_all is not None:
    for pkg in ("webview", "flask", "waitress"):
        try:
            d, b, h = collect_all(pkg)
            datas += d
            binaries += b
            hiddenimports += h
        except Exception:  # noqa: BLE001
            pass

if (ROOT / "sample_movie.mp4").exists():
    datas.append((str(ROOT / "sample_movie.mp4"), "."))

a = Analysis(
    [str(ROOT / "desktop_app.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SceneCutProPlus",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # no black CMD window — real desktop app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SceneCutProPlus",
)

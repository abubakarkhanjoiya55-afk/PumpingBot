# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — build on Windows: desktop\build_exe.bat

block_cipher = None

a = Analysis(
    ['../desktop_app.py'],
    pathex=['..'],
    binaries=[],
    datas=[
        ('../templates', 'templates'),
        ('../static', 'static'),
        ('../sample_movie.srt', '.'),
        ('../sample_movie_cluster.srt', '.'),
        ('../sample_narration.srt', '.'),
        ('../requirements.txt', '.'),
        ('../config.json', '.'),
    ],
    hiddenimports=['pysrt', 'flask', 'export_engine', 'cutting_engine', 'matching_engine', 'pro_plus'],
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
    name='SceneCutProPlus',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
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
    name='SceneCutProPlus',
)

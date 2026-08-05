SceneCut Pro+ — PC Desktop Install
=================================

WINDOWS (recommended)
---------------------
1) Install Python 3.10+ from https://www.python.org/downloads/
   - Enable: "Add python.exe to PATH"

2) Install ffmpeg (required for cutting):
   winget install Gyan.FFmpeg
   OR download from https://www.gyan.dev/ffmpeg/builds/
   and add ffmpeg.exe to PATH

3) Double-click:
   desktop\INSTALL.bat

4) Desktop pe "SceneCut Pro+" shortcut aa jayegi.
   Usay double-click karke NATIVE APP WINDOW khulegi
   (browser tab nahi) — CapCut jaisi Home + New project.

Uninstall:
  Start Menu → SceneCut Pro+ → Uninstall
  OR run desktop\UNINSTALL.bat


OPTIONAL: Standalone .exe folder
--------------------------------
On a Windows PC with Python:
  desktop\build_exe.bat
Output:
  dist\SceneCutProPlus\SceneCutProPlus.exe
(ffmpeg still required on the PC PATH)


LINUX / MAC
-----------
  chmod +x start.sh desktop/install_linux.sh
  ./desktop/install_linux.sh
  # or: python3 desktop_app.py

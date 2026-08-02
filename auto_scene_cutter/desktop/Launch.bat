@echo off
setlocal
title SceneCut Pro+
cd /d "%~dp0\.."

if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
) else if exist "%LOCALAPPDATA%\SceneCutProPlus\.venv\Scripts\activate.bat" (
  cd /d "%LOCALAPPDATA%\SceneCutProPlus"
  call ".venv\Scripts\activate.bat"
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo WARNING: ffmpeg not found in PATH. Cutting may fail.
  echo Install: winget install Gyan.FFmpeg
  echo.
)

set SCENECUT_DESKTOP=1
python desktop_app.py
if errorlevel 1 (
  echo.
  echo App exit with error.
  pause
)
endlocal

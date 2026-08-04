@echo off
setlocal EnableExtensions
title SceneCut Pro+
cd /d "%~dp0\.."

if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
) else if exist "%LOCALAPPDATA%\SceneCutProPlus\.venv\Scripts\activate.bat" (
  cd /d "%LOCALAPPDATA%\SceneCutProPlus"
  call ".venv\Scripts\activate.bat"
)

REM Prefer bundled portable ffmpeg if present
if exist "%CD%\tools\ffmpeg\bin\ffmpeg.exe" (
  set "PATH=%CD%\tools\ffmpeg\bin;%PATH%"
)
if exist "%LOCALAPPDATA%\SceneCutProPlus\tools\ffmpeg\bin\ffmpeg.exe" (
  set "PATH=%LOCALAPPDATA%\SceneCutProPlus\tools\ffmpeg\bin;%PATH%"
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo WARNING: ffmpeg nahi mila - Auto Cut fail ho sakta hai.
  echo 1_DOUBLE_CLICK.bat dobara chalao (ffmpeg auto install karega).
  echo.
)

REM Ensure native-window dep (pywebview) after updates
python -c "import webview" >nul 2>&1
if errorlevel 1 (
  echo Installing app window support...
  python -m pip install -q pywebview
)

set SCENECUT_DESKTOP=1
python desktop_app.py
if errorlevel 1 (
  echo.
  echo App error - window band mat karo, yeh message padho.
  pause
)
endlocal

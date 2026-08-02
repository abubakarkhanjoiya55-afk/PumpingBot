@echo off
setlocal EnableExtensions
title SceneCut Pro+ Installer
cd /d "%~dp0\.."

echo.
echo  ========================================
echo   SceneCut Pro+  -  Desktop Installer
echo  ========================================
echo.

set "APP_NAME=SceneCutProPlus"
set "INSTALL_DIR=%LOCALAPPDATA%\%APP_NAME%"
set "PYTHON_OK="

where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [ERROR] Python 3 nahi mila.
  echo Download: https://www.python.org/downloads/
  echo Install ke dauran "Add python.exe to PATH" check karo.
  echo.
  pause
  exit /b 1
)

echo [1/5] Install folder: %INSTALL_DIR%
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

echo [2/5] App files copy...
robocopy "%CD%" "%INSTALL_DIR%" /E /XD .git __pycache__ output _uploads projects .venv venv dist build desktop\dist /NFL /NDL /NJH /NJS /nc /ns /np >nul
if errorlevel 8 (
  echo [ERROR] Copy fail
  pause
  exit /b 1
)
REM always refresh desktop helper scripts
xcopy /Y /Q "%CD%\desktop\*" "%INSTALL_DIR%\desktop\" >nul

echo [3/5] Virtual environment + dependencies...
pushd "%INSTALL_DIR%"
%PY% -m venv .venv
if errorlevel 1 (
  echo [ERROR] venv ban nahi saka
  popd
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install fail
  popd
  pause
  exit /b 1
)
popd

echo [4/5] ffmpeg check...
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo [WARN] ffmpeg PATH pe nahi mila.
  echo        Video cut ke liye zaroori hai.
  echo        Install options:
  echo          winget install Gyan.FFmpeg
  echo          https://www.gyan.dev/ffmpeg/builds/
  echo.
) else (
  echo       ffmpeg OK
)

echo [5/5] Desktop + Start Menu shortcuts...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcuts.ps1" -InstallDir "%INSTALL_DIR%"
if errorlevel 1 (
  echo [WARN] Shortcut create issue — Launch.bat se chal sakte ho:
  echo        %INSTALL_DIR%\desktop\Launch.bat
)

echo.
echo  ========================================
echo   Install complete!
echo.
echo   Desktop shortcut: SceneCut Pro+
echo   Folder: %INSTALL_DIR%
echo.
echo   Uninstall: desktop\UNINSTALL.bat
echo  ========================================
echo.
pause
endlocal

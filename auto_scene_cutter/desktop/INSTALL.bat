@echo off
setlocal EnableExtensions EnableDelayedExpansion
title SceneCut Pro+ — Auto Install
cd /d "%~dp0\.."

echo.
echo  ========================================
echo   SceneCut Pro+  AUTO INSTALL
echo   Python mil gaya — baaki main khud karunga
echo  ========================================
echo.

set "APP_NAME=SceneCutProPlus"
set "INSTALL_DIR=%LOCALAPPDATA%\%APP_NAME%"

REM ---- Find Python ----
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [ERROR] Python nahi mila PATH pe.
  echo Python install karte waqt "Add python.exe to PATH" CHECK karo.
  echo Phir PC restart / naya Command Prompt kholo, yeh bat dobara chalao.
  echo.
  pause
  exit /b 1
)

echo [1/6] Python OK
%PY% --version

echo [2/6] Install folder: %INSTALL_DIR%
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

echo [3/6] App files copy...
robocopy "%CD%" "%INSTALL_DIR%" /E /XD .git __pycache__ output _uploads projects .venv venv dist build desktop\dist releases /NFL /NDL /NJH /NJS /nc /ns /np >nul
if errorlevel 8 (
  echo [ERROR] Copy fail
  pause
  exit /b 1
)
xcopy /Y /Q /E "%CD%\desktop\*" "%INSTALL_DIR%\desktop\" >nul

echo [4/6] Dependencies install (pip)...
pushd "%INSTALL_DIR%"
%PY% -m venv .venv
if errorlevel 1 (
  echo [ERROR] venv ban nahi saka
  popd
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install fail — internet check karo
  popd
  pause
  exit /b 1
)
popd

echo [5/6] ffmpeg auto-setup...
powershell -NoProfile -ExecutionPolicy Bypass -File "%INSTALL_DIR%\desktop\setup_ffmpeg.ps1" -InstallDir "%INSTALL_DIR%"

echo [6/6] Desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -File "%INSTALL_DIR%\desktop\create_shortcuts.ps1" -InstallDir "%INSTALL_DIR%"

echo.
echo  ========================================
echo   DONE — SceneCut Pro+ ready!
echo   Desktop pe shortcut: SceneCut Pro+
echo  ========================================
echo.
echo  App ab khud open ho rahi hai...
echo.

REM Launch immediately so user is not confused
start "" "%INSTALL_DIR%\desktop\Launch.bat"

timeout /t 3 /nobreak >nul
endlocal
exit /b 0

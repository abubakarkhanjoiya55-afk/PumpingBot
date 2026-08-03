@echo off
setlocal EnableExtensions
title SceneCut Pro+ Auto Install
cd /d "%~dp0\.."

echo.
echo  ========================================
echo   SceneCut Pro+  AUTO INSTALL
echo   Python OK - baaki automatic
echo  ========================================
echo.

set "APP_NAME=SceneCutProPlus"
set "INSTALL_DIR=%LOCALAPPDATA%\%APP_NAME%"
set "PY_CMD="
set "PY_ARGS="

where py >nul 2>&1
if not errorlevel 1 (
  set "PY_CMD=py"
  set "PY_ARGS=-3"
  goto :py_found
)

where python >nul 2>&1
if not errorlevel 1 (
  set "PY_CMD=python"
  set "PY_ARGS="
  goto :py_found
)

echo [ERROR] Python nahi mila PATH pe.
echo Python install karte waqt Add python.exe to PATH CHECK karo.
echo Phir naya CMD kholo aur START_HERE.bat dobara chalao.
echo.
pause
exit /b 1

:py_found
echo [1/6] Python OK
if "%PY_ARGS%"=="" (
  %PY_CMD% --version
) else (
  %PY_CMD% %PY_ARGS% --version
)

echo [2/6] Install folder:
echo       %INSTALL_DIR%
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

echo [3/6] App files copy...
robocopy "%CD%" "%INSTALL_DIR%" /E /XD .git __pycache__ output _uploads projects .venv venv dist build desktop\dist releases /NFL /NDL /NJH /NJS /nc /ns /np >nul
if errorlevel 8 (
  echo [ERROR] Copy fail
  pause
  exit /b 1
)
xcopy /Y /Q /E "%CD%\desktop\*" "%INSTALL_DIR%\desktop\" >nul

echo [4/6] pip packages install...
pushd "%INSTALL_DIR%"
if "%PY_ARGS%"=="" (
  %PY_CMD% -m venv .venv
) else (
  %PY_CMD% %PY_ARGS% -m venv .venv
)
if errorlevel 1 (
  echo [ERROR] venv fail
  popd
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install fail - internet check karo
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
echo   DONE - SceneCut Pro+ ready
echo   Desktop shortcut: SceneCut Pro+
echo  ========================================
echo.
echo  App ab open ho rahi hai...
echo.

start "" "%INSTALL_DIR%\desktop\Launch.bat"
timeout /t 4 /nobreak >nul
endlocal
exit /b 0

@echo off
setlocal EnableExtensions
title SceneCut Pro+ Auto Install
cd /d "%~dp0\.."

set "SRC=%CD%"
set "APP_NAME=SceneCutProPlus"
set "INSTALL_DIR=%LOCALAPPDATA%\%APP_NAME%"
set "PY_CMD="
set "PY_ARGS="

echo.
echo  ========================================
echo   SceneCut Pro+  AUTO INSTALL
echo   Python OK - baaki automatic
echo  ========================================
echo.

where py >nul 2>&1
if errorlevel 1 goto TRY_PYTHON
set "PY_CMD=py"
set "PY_ARGS=-3"
goto PY_FOUND

:TRY_PYTHON
where python >nul 2>&1
if errorlevel 1 goto NO_PYTHON
set "PY_CMD=python"
set "PY_ARGS="
goto PY_FOUND

:NO_PYTHON
echo [ERROR] Python nahi mila PATH pe.
echo Python install karte waqt Add python.exe to PATH CHECK karo.
echo Phir naya CMD kholo aur 1_DOUBLE_CLICK.bat dobara chalao.
echo.
pause
exit /b 1

:PY_FOUND
echo [1/6] Python OK
if defined PY_ARGS goto PY_VER_ARGS
%PY_CMD% --version
goto AFTER_PY_VER
:PY_VER_ARGS
%PY_CMD% %PY_ARGS% --version
:AFTER_PY_VER

echo [2/6] Install folder:
echo       %INSTALL_DIR%
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

echo [3/6] App files copy...
robocopy "%SRC%" "%INSTALL_DIR%" /E /XD .git __pycache__ output _uploads projects .venv venv dist build desktop\dist releases /NFL /NDL /NJH /NJS /nc /ns /np >nul
if errorlevel 8 goto COPY_FAIL
xcopy /Y /Q /E "%SRC%\desktop\*" "%INSTALL_DIR%\desktop\" >nul

echo [4/6] pip packages install...
pushd "%INSTALL_DIR%"
if defined PY_ARGS goto VENV_ARGS
%PY_CMD% -m venv .venv
goto AFTER_VENV
:VENV_ARGS
%PY_CMD% %PY_ARGS% -m venv .venv
:AFTER_VENV
if errorlevel 1 goto VENV_FAIL

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto PIP_FAIL
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

:COPY_FAIL
echo [ERROR] Copy fail
pause
exit /b 1

:VENV_FAIL
popd
echo [ERROR] venv fail
pause
exit /b 1

:PIP_FAIL
popd
echo [ERROR] pip install fail - internet check karo
pause
exit /b 1

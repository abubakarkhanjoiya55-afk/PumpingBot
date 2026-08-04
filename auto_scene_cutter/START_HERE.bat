@echo off
setlocal EnableExtensions
REM Sirf is file pe DOUBLE-CLICK karo
cd /d "%~dp0"
title SceneCut Pro+

set "SRC=%CD%"
set "INSTALL_DIR=%LOCALAPPDATA%\SceneCutProPlus"
set "LAUNCH=%INSTALL_DIR%\desktop\Launch.bat"
set "VENV_PY=%INSTALL_DIR%\.venv\Scripts\python.exe"

if not exist "%LAUNCH%" goto FULL_INSTALL

echo.
echo  Update + open ho raha hai...
echo.
robocopy "%SRC%" "%INSTALL_DIR%" /E /XD .git __pycache__ output _uploads projects .venv venv dist build desktop\dist releases /NFL /NDL /NJH /NJS /nc /ns /np >nul
xcopy /Y /Q /E "%SRC%\desktop\*" "%INSTALL_DIR%\desktop\" >nul
if exist "%VENV_PY%" "%VENV_PY%" -m pip install -q -r "%INSTALL_DIR%\requirements.txt"
start "" "%LAUNCH%"
exit /b 0

:FULL_INSTALL
echo.
echo  SceneCut Pro+ setup shuru...
echo  Ruko - pip + ffmpeg automatic.
echo.
call "%~dp0desktop\INSTALL.bat"
if errorlevel 1 goto INSTALL_FAIL
exit /b 0

:INSTALL_FAIL
echo.
echo Install fail. Window band mat karo - error upar padho.
pause
exit /b 1

@echo off
REM Sirf is file pe DOUBLE-CLICK karo
cd /d "%~dp0"
title SceneCut Pro+

set "INSTALL_DIR=%LOCALAPPDATA%\SceneCutProPlus"
set "LAUNCH=%INSTALL_DIR%\desktop\Launch.bat"

if exist "%LAUNCH%" (
  echo.
  echo  Update + open ho raha hai...
  echo.
  robocopy "%CD%" "%INSTALL_DIR%" /E /XD .git __pycache__ output _uploads projects .venv venv dist build desktop\dist releases /NFL /NDL /NJH /NJS /nc /ns /np >nul
  xcopy /Y /Q /E "%CD%\desktop\*" "%INSTALL_DIR%\desktop\" >nul
  if exist "%INSTALL_DIR%\.venv\Scripts\python.exe" (
    "%INSTALL_DIR%\.venv\Scripts\python.exe" -m pip install -q -r "%INSTALL_DIR%\requirements.txt"
  )
  start "" "%LAUNCH%"
  exit /b 0
)

echo.
echo  SceneCut Pro+ setup shuru...
echo  Ruko - pip + ffmpeg automatic.
echo.
call "%~dp0desktop\INSTALL.bat"
if errorlevel 1 (
  echo.
  echo Install fail. Window band mat karo - error upar padho.
  pause
)

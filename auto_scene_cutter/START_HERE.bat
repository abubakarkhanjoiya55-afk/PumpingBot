@echo off
REM Sirf is file pe DOUBLE-CLICK karo
cd /d "%~dp0"
title SceneCut Pro+

set "LAUNCH=%LOCALAPPDATA%\SceneCutProPlus\desktop\Launch.bat"
if exist "%LAUNCH%" (
  echo.
  echo  Pehle se install mil gaya - app open ho rahi hai...
  echo.
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

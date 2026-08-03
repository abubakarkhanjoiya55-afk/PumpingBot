@echo off
REM Agar install ho chuka ho to app seedha kholo
setlocal
set "LAUNCH=%LOCALAPPDATA%\SceneCutProPlus\desktop\Launch.bat"
if exist "%LAUNCH%" (
  start "" "%LAUNCH%"
  exit /b 0
)
echo Pehle START_HERE.bat chalao install ke liye.
pause
endlocal

@echo off
REM App open - agar install ho chuka ho
setlocal
set "LAUNCH=%LOCALAPPDATA%\SceneCutProPlus\desktop\Launch.bat"
if exist "%LAUNCH%" (
  start "" "%LAUNCH%"
  exit /b 0
)
echo Install abhi nahi hua.
echo Pehle 1_DOUBLE_CLICK.bat chalao.
pause
endlocal

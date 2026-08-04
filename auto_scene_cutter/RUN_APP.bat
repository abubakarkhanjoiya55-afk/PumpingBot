@echo off
setlocal EnableExtensions
REM App open - agar install ho chuka ho
set "LAUNCH=%LOCALAPPDATA%\SceneCutProPlus\desktop\Launch.bat"
if exist "%LAUNCH%" goto DO_LAUNCH
echo Install abhi nahi hua.
echo Pehle 1_DOUBLE_CLICK.bat chalao.
pause
exit /b 1

:DO_LAUNCH
start "" "%LAUNCH%"
exit /b 0

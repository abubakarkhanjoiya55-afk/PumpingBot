@echo off
setlocal EnableExtensions
set "VBS=%LOCALAPPDATA%\SceneCutProPlus\desktop\LaunchSilent.vbs"
set "EXE=%LOCALAPPDATA%\SceneCutProPlus\SceneCutProPlus.exe"
if exist "%EXE%" (
  start "" "%EXE%"
  exit /b 0
)
if exist "%VBS%" (
  start "" wscript.exe "%VBS%"
  exit /b 0
)
echo Install abhi nahi hua.
echo Pehle "Install SceneCut Pro.vbs" ya Setup.exe chalao.
pause
exit /b 1

@echo off
setlocal
title Uninstall SceneCut Pro+
echo.
echo Uninstall SceneCut Pro+ from this PC?
echo Folder: %LOCALAPPDATA%\SceneCutProPlus
echo.
set /p ANS=Type YES to confirm: 
if /I not "%ANS%"=="YES" (
  echo Cancelled.
  pause
  exit /b 0
)

echo Closing running app if any...
taskkill /F /IM pythonw.exe /FI "WINDOWTITLE eq SceneCut Pro+*" >nul 2>&1

echo Removing shortcuts...
del /Q "%USERPROFILE%\Desktop\SceneCut Pro+.lnk" >nul 2>&1
rmdir /S /Q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\SceneCut Pro+" >nul 2>&1

echo Removing install folder...
rmdir /S /Q "%LOCALAPPDATA%\SceneCutProPlus" >nul 2>&1

echo.
echo Uninstall complete.
pause
endlocal

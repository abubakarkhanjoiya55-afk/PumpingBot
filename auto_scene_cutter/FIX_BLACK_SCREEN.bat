@echo off
setlocal EnableExtensions
title SceneCut Pro+ — Fix black screen
echo.
echo  Clearing stale update marker + forcing fresh files...
echo.
set "APP=%LOCALAPPDATA%\SceneCutProPlus"
if exist "%APP%\.scenecut_version" del /f /q "%APP%\.scenecut_version"
if exist "%~dp0.scenecut_version" del /f /q "%~dp0.scenecut_version"
echo  Marker cleared.
echo.
echo  Ab SceneCut Pro+ shortcut se app kholo.
echo  Agar phir black aaye to naya Setup.exe install karo:
echo  https://scenecut-production.up.railway.app/download
echo.
pause
endlocal

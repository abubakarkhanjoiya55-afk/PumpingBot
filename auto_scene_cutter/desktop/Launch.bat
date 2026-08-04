@echo off
setlocal EnableExtensions
title SceneCut Pro+
cd /d "%~dp0\.."

set "APP_DIR=%CD%"
set "ACTIVATE=%APP_DIR%\.venv\Scripts\activate.bat"
if exist "%ACTIVATE%" goto HAVE_VENV

set "APP_DIR=%LOCALAPPDATA%\SceneCutProPlus"
set "ACTIVATE=%APP_DIR%\.venv\Scripts\activate.bat"
if exist "%ACTIVATE%" goto HAVE_VENV
goto AFTER_VENV

:HAVE_VENV
cd /d "%APP_DIR%"
call "%ACTIVATE%"
:AFTER_VENV

if exist "%APP_DIR%\tools\ffmpeg\bin\ffmpeg.exe" set "PATH=%APP_DIR%\tools\ffmpeg\bin;%PATH%"
if exist "%LOCALAPPDATA%\SceneCutProPlus\tools\ffmpeg\bin\ffmpeg.exe" set "PATH=%LOCALAPPDATA%\SceneCutProPlus\tools\ffmpeg\bin;%PATH%"

where ffmpeg >nul 2>&1
if errorlevel 1 goto NO_FFMPEG
goto AFTER_FFMPEG
:NO_FFMPEG
echo WARNING: ffmpeg nahi mila - Auto Cut fail ho sakta hai.
echo.
:AFTER_FFMPEG

set SCENECUT_DESKTOP=1
python desktop_app.py
if errorlevel 1 goto APP_ERR
endlocal
exit /b 0

:APP_ERR
echo.
echo App error - window band mat karo, yeh message padho.
pause
endlocal
exit /b 1

@echo off
setlocal EnableExtensions
cd /d "%~dp0"
REM Professional GUI installer - CMD closes immediately
if exist "%~dp0Install SceneCut Pro.vbs" (
  start "" wscript.exe "%~dp0Install SceneCut Pro.vbs"
  exit /b 0
)
call "%~dp0START_HERE.bat"
exit /b %ERRORLEVEL%

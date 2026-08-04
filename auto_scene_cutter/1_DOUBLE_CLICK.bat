@echo off
setlocal EnableExtensions
REM Confused ho to SIRF YE file pe double-click
cd /d "%~dp0"
call "%~dp0START_HERE.bat"
exit /b %ERRORLEVEL%

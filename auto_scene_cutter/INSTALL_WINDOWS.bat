@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0desktop\INSTALL.bat"
exit /b %ERRORLEVEL%

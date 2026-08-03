@echo off
title PumpingBot VPS Supervisor
cd /d %~dp0

if not exist config.bat (
  echo [ERROR] config.bat nahi mili.
  echo Pehle setup_vps.ps1 chalao, phir config.bat mein SERVER_URL + VPS_SECRET daalo.
  pause
  exit /b 1
)

call config.bat

if "%SERVER_URL%"=="" (
  echo [ERROR] SERVER_URL empty hai — config.bat edit karo
  pause
  exit /b 1
)
if "%VPS_SECRET%"=="" (
  echo [ERROR] VPS_SECRET empty hai — Railway wahi secret yahan daalo
  pause
  exit /b 1
)
if "%SERVER_URL%"=="https://YOUR-APP.up.railway.app" (
  echo [ERROR] SERVER_URL abhi example hai — apna Railway URL daalo
  notepad config.bat
  pause
  exit /b 1
)

if not exist "%MT5_TEMPLATE_DIR%\terminal64.exe" (
  echo [ERROR] MT5 template missing:
  echo   %MT5_TEMPLATE_DIR%\terminal64.exe
  echo Broker se MT5 install karke folder copy karo. Details: README.md
  pause
  exit /b 1
)

if not exist "%MT5_TEMPLATE_DIR%\portable" (
  echo. > "%MT5_TEMPLATE_DIR%\portable"
)

if not exist "%REPO_DIR%\local_agent\agent.py" (
  echo [ERROR] Repo path galat: %REPO_DIR%
  pause
  exit /b 1
)

echo ========================================
echo  PumpingBot VPS Supervisor starting
echo  SERVER_URL=%SERVER_URL%
echo  Keep this window OPEN
echo ========================================

cd /d "%REPO_DIR%"
python vps_supervisor\supervisor.py
echo.
echo Supervisor band ho gaya. Error ke liye upar dekho / logs folder.
pause

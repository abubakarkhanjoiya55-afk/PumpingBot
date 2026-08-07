@echo off
title PumpingBot Setup
cd /d "%~dp0"

echo.
echo  PumpingBot One-Click Installer
echo  ================================
echo  Exness MT5 pehle install hona chahiye.
echo.

REM Unblock + run PowerShell setup
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0PumpingBotSetup.ps1" %*
if errorlevel 1 (
  echo.
  echo Setup error. Agar MT5 abhi install nahi to pehle Exness MT5 lagao.
  pause
)

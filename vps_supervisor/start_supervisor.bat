@echo off
REM Run on Windows VPS (keep this window open, or use Task Scheduler)
cd /d %~dp0\..

if not defined SERVER_URL (
  echo Set SERVER_URL first, e.g.:
  echo   set SERVER_URL=https://your-app.up.railway.app
  exit /b 1
)
if not defined VPS_SECRET (
  echo Set VPS_SECRET first (same value as Railway env VPS_SECRET)
  exit /b 1
)

set REPO_DIR=%cd%
set PYTHONUNBUFFERED=1

echo Starting PumpingBot VPS Supervisor...
python vps_supervisor\supervisor.py
pause

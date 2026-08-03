@echo off
REM Copy this file to config.bat and fill values, then run setup_vps.ps1 / start_supervisor.bat

REM ===== REQUIRED (tum fill karo) =====
set SERVER_URL=https://YOUR-APP.up.railway.app
set VPS_SECRET=same-secret-as-railway-VPS_SECRET

REM ===== USUALLY KEEP AS-IS =====
set REPO_DIR=C:\PumpingBot\PumpingBot
set MT5_TEMPLATE_DIR=C:\PumpingBot\MT5_Template
set MT5_INSTANCES_DIR=C:\PumpingBot\MT5_Instances
set AGENT_LOG_DIR=C:\PumpingBot\logs
set MT5_BOOT_WAIT_SEC=8
set POLL_SEC=10
set PYTHONUNBUFFERED=1

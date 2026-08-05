@echo off
REM Copy this file to config.bat and fill values, then run setup_vps.ps1 / start_supervisor.bat

REM ===== REQUIRED (tum fill karo) =====
set SERVER_URL=https://web-production-c78a0.up.railway.app
set VPS_SECRET=pumpingbot-vps-live-2026

REM ===== USUALLY KEEP AS-IS =====
set REPO_DIR=C:\PumpingBot\PumpingBot
set MT5_TEMPLATE_DIR=C:\PumpingBot\MT5_Template
set MT5_INSTANCES_DIR=C:\PumpingBot\MT5_Instances
set AGENT_LOG_DIR=C:\PumpingBot\logs
set MT5_BOOT_WAIT_SEC=20
set POLL_SEC=10
set PYTHONUNBUFFERED=1
REM standard = demo/real USD (*m). cent = USC (*c).
REM Schedule: Mon-Fri Gold only; Sat-Sun BTC+ETH only.
set ACCOUNT_TYPE=standard
REM set SYMBOLS=XAUUSDm,BTCUSDm,ETHUSDm
REM For cent book instead:
REM set ACCOUNT_TYPE=cent
REM set SYMBOLS=XAUUSDc,BTCUSDc,ETHUSDc

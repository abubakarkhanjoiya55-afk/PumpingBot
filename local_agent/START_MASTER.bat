@echo off
REM ============================================================
REM  PumpingBot — MASTER agent (sirf ADMIN ke PC pe)
REM  Strategy yahan chalti hai; followers ko copy signals jate hain.
REM ============================================================
cd /d "%~dp0\.."

set SERVER_URL=https://web-production-c78a0.up.railway.app
set ACCESS_TOKEN=PASTE_ADMIN_TOKEN_FROM_APP
set MT5_LOGIN=YOUR_MASTER_LOGIN
set MT5_PASSWORD=your_mt5_password
set MT5_SERVER=Exness-MT5Real
set MT5_PATH=
set AGENT_ROLE=master
set BOT_ACTIVE=0

echo [PumpingBot] MASTER agent starting...
python local_agent\agent.py
if errorlevel 1 pause

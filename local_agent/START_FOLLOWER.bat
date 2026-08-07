@echo off
REM ============================================================
REM  PumpingBot — Follower agent (USER ke Windows PC pe chalao)
REM  Yeh window OPEN rehne do. Band = trades ruk jayengi.
REM ============================================================
cd /d "%~dp0\.."

REM ---- EDIT THESE ----
set SERVER_URL=https://web-production-c78a0.up.railway.app
set ACCESS_TOKEN=PASTE_TOKEN_FROM_APP_PC_SETUP
set MT5_LOGIN=12345678
set MT5_PASSWORD=your_mt5_password
set MT5_SERVER=Exness-MT5Real
REM Optional: full path to terminal64.exe (single MT5 pe blank chhod sakte ho)
set MT5_PATH=
set AGENT_ROLE=follower
set BOT_ACTIVE=0
REM --------------------

echo.
echo [PumpingBot] Follower agent starting...
echo Server: %SERVER_URL%
echo Login:  %MT5_LOGIN% @ %MT5_SERVER%
echo.
echo Pehle: pip install -r local_agent\requirements.txt
echo App pe Start Bot tab dabao jab yeh connected dikhe.
echo.

python local_agent\agent.py
if errorlevel 1 (
  echo.
  echo Agent band ho gaya / error. Window band karne se pehle log padho.
  pause
)

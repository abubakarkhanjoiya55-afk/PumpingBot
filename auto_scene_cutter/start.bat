@echo off
REM SceneCut Pro+ — one-click local start (Windows)
cd /d "%~dp0"

echo SceneCut Pro+
echo Installing dependencies...
py -3 -m pip install -q -r requirements.txt
if errorlevel 1 (
  python -m pip install -q -r requirements.txt
)

echo.
echo Starting editor - http://127.0.0.1:5000
echo Stop with Ctrl+C
echo.

start "" http://127.0.0.1:5000

py -3 -c "from app import app; app.run(host='127.0.0.1', port=5000, debug=False)"
if errorlevel 1 (
  python -c "from app import app; app.run(host='127.0.0.1', port=5000, debug=False)"
)

pause

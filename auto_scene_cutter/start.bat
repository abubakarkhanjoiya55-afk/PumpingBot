@echo off
REM Auto Scene Cutter — easy local start (Windows)
cd /d "%~dp0"

echo Dependencies install ho rahi hain...
py -3 -m pip install -r requirements.txt
if errorlevel 1 (
  python -m pip install -r requirements.txt
)

echo.
echo Server start ho raha hai...
echo Browser mein yeh kholo: http://127.0.0.1:5000
echo Band karne ke liye: Ctrl+C
echo.

py -3 -c "from app import app; app.run(host='127.0.0.1', port=5000, debug=False)"
if errorlevel 1 (
  python -c "from app import app; app.run(host='127.0.0.1', port=5000, debug=False)"
)

pause

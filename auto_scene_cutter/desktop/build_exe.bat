@echo off
REM Build a standalone Windows folder with PyInstaller (run on Windows PC)
setlocal
cd /d "%~dp0\.."

echo Installing build tools...
py -3 -m pip install -r requirements.txt pyinstaller
if errorlevel 1 python -m pip install -r requirements.txt pyinstaller

echo.
echo Building SceneCutProPlus.exe ...
py -3 -m PyInstaller --noconfirm --clean desktop\SceneCutProPlus.spec
if errorlevel 1 (
  python -m PyInstaller --noconfirm --clean desktop\SceneCutProPlus.spec
)

echo.
if exist "dist\SceneCutProPlus\SceneCutProPlus.exe" (
  echo BUILD OK
  echo Output: dist\SceneCutProPlus\
  echo Copy that folder to any PC + keep ffmpeg in PATH.
) else (
  echo BUILD FAILED
)
pause
endlocal

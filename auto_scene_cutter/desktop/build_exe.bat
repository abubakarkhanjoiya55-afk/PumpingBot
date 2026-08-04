@echo off
setlocal EnableExtensions
REM Build standalone Windows app + Setup.exe style folder
cd /d "%~dp0\.."

echo Installing build tools...
py -3 -m pip install -r requirements.txt pyinstaller
if errorlevel 1 python -m pip install -r requirements.txt pyinstaller

echo.
echo Building SceneCutProPlus.exe - no console window...
py -3 -m PyInstaller --noconfirm --clean desktop\SceneCutProPlus.spec
if errorlevel 1 python -m PyInstaller --noconfirm --clean desktop\SceneCutProPlus.spec

echo.
if exist "dist\SceneCutProPlus\SceneCutProPlus.exe" (
  echo BUILD OK
  echo Output: dist\SceneCutProPlus\SceneCutProPlus.exe
  echo.
  echo Professional Setup.exe CI pe banta hai:
  echo   GitHub Actions - Build SceneCut Windows Setup
) else (
  echo BUILD FAILED
  pause
  exit /b 1
)
endlocal

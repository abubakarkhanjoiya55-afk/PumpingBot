# PumpingBot Windows VPS one-time setup
# Run in PowerShell (Admin recommended):
#   Set-ExecutionPolicy Bypass -Scope Process -Force
#   cd C:\PumpingBot\PumpingBot\vps_supervisor
#   .\setup_vps.ps1

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " PumpingBot VPS Setup"
Write-Host "========================================" -ForegroundColor Cyan

$Root = "C:\PumpingBot"
$Repo = Join-Path $Root "PumpingBot"
$RepoUrl = "https://github.com/abubakarkhanjoiya55-afk/PumpingBot.git"
$Branch = if ($env:PB_BRANCH) { $env:PB_BRANCH } else { "main" }

New-Item -ItemType Directory -Force -Path $Root | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "MT5_Instances") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "MT5_Template") | Out-Null

function Ensure-Command($name, $wingetId) {
  if (Get-Command $name -ErrorAction SilentlyContinue) {
    Write-Host "[OK] $name found"
    return
  }
  Write-Host "[..] Installing $name via winget..."
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    winget install --id $wingetId -e --accept-source-agreements --accept-package-agreements
  } else {
    Write-Host "[!] winget missing. Install manually: $name" -ForegroundColor Yellow
  }
}

Ensure-Command "git" "Git.Git"
Ensure-Command "python" "Python.Python.3.12"

# Refresh PATH for this session
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path","User")

if (-not (Test-Path (Join-Path $Repo ".git"))) {
  Write-Host "[..] Cloning repo ($Branch)..."
  git clone -b $Branch --single-branch $RepoUrl $Repo
} else {
  Write-Host "[..] Updating repo..."
  Push-Location $Repo
  git fetch origin $Branch
  git checkout $Branch
  git pull origin $Branch
  Pop-Location
}

$ConfigExample = Join-Path $Repo "vps_supervisor\config.example.bat"
$Config = Join-Path $Repo "vps_supervisor\config.bat"
if (-not (Test-Path $Config)) {
  Copy-Item $ConfigExample $Config
  Write-Host "[!] config.bat created - set SERVER_URL and VPS_SECRET" -ForegroundColor Yellow
} else {
  Write-Host "[OK] config.bat already exists"
}

Write-Host "[..] Installing Python packages..."
Push-Location $Repo
python -m pip install --upgrade pip
python -m pip install -r vps_supervisor\requirements.txt
python -m pip install -r local_agent\requirements.txt
Pop-Location

$TemplateExe = Join-Path $Root "MT5_Template\terminal64.exe"
$PortableMarker = Join-Path $Root "MT5_Template\portable"
if (-not (Test-Path $TemplateExe)) {
  Write-Host ""
  Write-Host "========================================" -ForegroundColor Yellow
  Write-Host " MT5 TEMPLATE MISSING"
  Write-Host "========================================" -ForegroundColor Yellow
  Write-Host "Step 1: Install MetaTrader 5 on this VPS from your broker site"
  Write-Host "Step 2: COPY the install folder to:"
  Write-Host "   C:\PumpingBot\MT5_Template\"
  Write-Host "   (must contain terminal64.exe)"
  Write-Host "Step 3: Create empty file named portable (no extension) in that folder"
  Write-Host ""
} else {
  if (-not (Test-Path $PortableMarker)) {
    New-Item -ItemType File -Path $PortableMarker -Force | Out-Null
    Write-Host "[OK] portable marker created"
  }
  Write-Host "[OK] MT5 template found"
}

Write-Host ""
Write-Host "NEXT:" -ForegroundColor Green
Write-Host " 1. Edit: $Config"
Write-Host " 2. Set SERVER_URL + VPS_SECRET"
Write-Host " 3. When MT5 template is ready, run:"
Write-Host "    C:\PumpingBot\PumpingBot\vps_supervisor\START_HERE.bat"
Write-Host ""

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
$Branch = "cursor/local-mt5-agent-hub-ff4b"

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
    Write-Host "[!] winget nahi mila. Khud install karo: $name" -ForegroundColor Yellow
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
  Write-Host "[!] config.bat ban gaya — isme SERVER_URL aur VPS_SECRET daalo" -ForegroundColor Yellow
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
  Write-Host " MT5 TEMPLATE ABHI MISSING HAI"
  Write-Host "========================================" -ForegroundColor Yellow
  Write-Host "1) Is VPS pe MetaTrader 5 install karo (broker website se)"
  Write-Host "2) Install folder KO COPY karke yahan rakho:"
  Write-Host "   C:\PumpingBot\MT5_Template\"
  Write-Host "   (andar terminal64.exe hona chahiye)"
  Write-Host "3) Us folder mein empty file banao naam: portable (bina extension)"
  Write-Host ""
} else {
  if (-not (Test-Path $PortableMarker)) {
    New-Item -ItemType File -Path $PortableMarker -Force | Out-Null
    Write-Host "[OK] portable marker create kiya"
  }
  Write-Host "[OK] MT5 template found"
}

Write-Host ""
Write-Host "NEXT:" -ForegroundColor Green
Write-Host " 1) Edit: $Config"
Write-Host " 2) Set SERVER_URL + VPS_SECRET"
Write-Host " 3) MT5 template ready ho to run:"
Write-Host "    C:\PumpingBot\PumpingBot\vps_supervisor\START_HERE.bat"
Write-Host ""

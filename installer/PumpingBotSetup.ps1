# PumpingBot One-Click Setup (Windows)
# Double-click: PumpingBotSetup.bat
#
# Yeh script:
#  1) EA file Experts folder mein copy karti hai
#  2) Token + Server config likhti hai (InpToken paste ki zaroorat nahi)
#  3) WebRequest URL common.ini mein add karti hai
#  4) MT5 kholne ki koshish karti hai
#
# User se pehle chahiye:
#  - Exness MT5 install
#  - App se EA Token (ya yahan paste)
#  - Baad mein: MT5 login + AutoTrading ON + EA chart pe ek dafa drag

param(
    [string]$ServerUrl = "https://web-production-c78a0.up.railway.app",
    [string]$Token = "",
    [string]$EaSource = ""
)

$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "PumpingBot Setup"

function Write-Title($msg) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " $msg" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}

function Get-Mt5DataRoots {
    $roots = @()
    $appData = Join-Path $env:APPDATA "MetaQuotes\Terminal"
    if (Test-Path $appData) {
        Get-ChildItem -Path $appData -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            $experts = Join-Path $_.FullName "MQL5\Experts"
            if (Test-Path (Join-Path $_.FullName "MQL5")) {
                $roots += $_.FullName
            }
        }
    }
    # Portable / Exness custom installs sometimes keep data next to terminal
    $search = @(
        "$env:ProgramFiles\MetaTrader 5",
        "$env:ProgramFiles\MetaTrader 5 EXNESS",
        "${env:ProgramFiles(x86)}\MetaTrader 5",
        "$env:LOCALAPPDATA\Programs",
        "$env:USERPROFILE\Desktop",
        "$env:USERPROFILE\Downloads",
        "C:\Program Files\MetaTrader 5 EXNESS",
        "C:\Program Files\Exness MetaTrader 5"
    )
    foreach ($p in $search) {
        if (-not (Test-Path $p)) { continue }
        Get-ChildItem -Path $p -Filter "terminal64.exe" -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 5 |
            ForEach-Object {
                $dir = $_.Directory.FullName
                $mql = Join-Path $dir "MQL5"
                if (Test-Path $mql) { $roots += $dir }
            }
    }
    return ($roots | Select-Object -Unique)
}

function Find-TerminalExe {
    $paths = @(
        "$env:ProgramFiles\MetaTrader 5 EXNESS\terminal64.exe",
        "$env:ProgramFiles\MetaTrader 5\terminal64.exe",
        "$env:ProgramFiles\Exness MetaTrader 5\terminal64.exe",
        "${env:ProgramFiles(x86)}\MetaTrader 5\terminal64.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) { return $p }
    }
    $hit = Get-ChildItem -Path "$env:ProgramFiles","${env:ProgramFiles(x86)}","$env:LOCALAPPDATA" `
        -Filter "terminal64.exe" -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($hit) { return $hit.FullName }
    return $null
}

function Ensure-WebRequestUrl([string]$terminalRoot, [string]$url) {
    $cfgDir = Join-Path $terminalRoot "config"
    if (-not (Test-Path $cfgDir)) {
        New-Item -ItemType Directory -Path $cfgDir -Force | Out-Null
    }
    $ini = Join-Path $cfgDir "common.ini"
    $urlLine = "WebRequestUrl=$url"
    if (-not (Test-Path $ini)) {
        @"
[Experts]
Enabled=1
Account=1
Chart=1
WebEnable=1
$urlLine
"@ | Set-Content -Path $ini -Encoding ASCII
        return $true
    }
    $content = Get-Content -Path $ini -Raw -ErrorAction SilentlyContinue
    if ($null -eq $content) { $content = "" }
    if ($content -match [regex]::Escape($url)) {
        return $false  # already present
    }
    if ($content -match "\[Experts\]") {
        # Append under Experts if possible
        $content = $content.TrimEnd() + "`r`n$urlLine`r`n"
    } else {
        $content = $content.TrimEnd() + "`r`n[Experts]`r`nWebEnable=1`r`n$urlLine`r`n"
    }
    # Also ensure WebEnable
    if ($content -notmatch "WebEnable\s*=") {
        $content = $content + "WebEnable=1`r`n"
    }
    Set-Content -Path $ini -Value $content -Encoding ASCII
    return $true
}

function Install-ToTerminal([string]$root, [string]$eaPath, [string]$server, [string]$token) {
    $experts = Join-Path $root "MQL5\Experts"
    $files = Join-Path $root "MQL5\Files"
    New-Item -ItemType Directory -Path $experts -Force | Out-Null
    New-Item -ItemType Directory -Path $files -Force | Out-Null

    Copy-Item -Path $eaPath -Destination (Join-Path $experts "PumpingBotFollower.mq5") -Force

    $cfg = @"
SERVER=$server
TOKEN=$token
"@
    Set-Content -Path (Join-Path $files "pumpingbot_config.txt") -Value $cfg -Encoding ASCII

    # Optional .set presets for Inputs dialog
    $set = @"
InpServerUrl=$server
InpToken=$token
InpPollMs=1000
InpMagic=888888
InpMinLot=0.01
"@
    Set-Content -Path (Join-Path $experts "PumpingBotFollower.set") -Value $set -Encoding ASCII

    $added = Ensure-WebRequestUrl -terminalRoot $root -url $server
    return @{ Root = $root; WebRequestAdded = $added }
}

Write-Title "PumpingBot Automatic Installer"
Write-Host "Yeh tool EA + token + WebRequest URL khud set karega." -ForegroundColor Yellow
Write-Host ""

# Resolve EA source
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $EaSource) {
    $candidates = @(
        (Join-Path $scriptDir "PumpingBotFollower.mq5"),
        (Join-Path $scriptDir "..\mql5\PumpingBotFollower.mq5"),
        (Join-Path $scriptDir "mql5\PumpingBotFollower.mq5")
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $EaSource = $c; break }
    }
}

if (-not $EaSource -or -not (Test-Path $EaSource)) {
    Write-Host "EA file download ho rahi hai server se..." -ForegroundColor Yellow
    $tmp = Join-Path $env:TEMP "PumpingBotFollower.mq5"
    try {
        Invoke-WebRequest -Uri "$ServerUrl/ea/download" -OutFile $tmp -UseBasicParsing
        $EaSource = $tmp
    } catch {
        Write-Host "ERROR: EA download fail. Net check karo ya mq5 file Setup ke saath rakho." -ForegroundColor Red
        Write-Host $_
        Read-Host "Enter dabao band karne ke liye"
        exit 1
    }
}

Write-Host "EA file: $EaSource" -ForegroundColor Green

# Token
if (-not $Token) {
    Write-Host ""
    Write-Host "App kholo -> PC Setup -> Copy EA Token" -ForegroundColor Cyan
    Write-Host "(Browser khol raha hoon PC Setup / app pe...)" -ForegroundColor DarkGray
    try { Start-Process "$ServerUrl/" } catch {}
    Write-Host ""
    $Token = Read-Host "Yahan EA Token PASTE karo"
}
$Token = $Token.Trim()
if ($Token.Length -lt 8) {
    Write-Host "ERROR: Token bohot chhota / khali hai." -ForegroundColor Red
    Read-Host "Enter dabao"
    exit 1
}

$ServerUrl = $ServerUrl.Trim().TrimEnd("/")

Write-Title "MT5 folders dhoondh rahe hain..."
$roots = @(Get-Mt5DataRoots)
if ($roots.Count -eq 0) {
    Write-Host "WARNING: MetaTrader data folder nahi mila." -ForegroundColor Yellow
    Write-Host "Pehle Exness MT5 install + ek dafa khol kar band karo, phir Setup dubara chalao." -ForegroundColor Yellow
    $exe = Find-TerminalExe
    if ($exe) {
        Write-Host "MT5 mil gaya: $exe — khol rahe hain. Login karo, band karo, Setup dubara run." -ForegroundColor Cyan
        Start-Process $exe
    }
    Read-Host "Enter dabao"
    exit 2
}

Write-Host ("Mile terminals: {0}" -f $roots.Count) -ForegroundColor Green
$installed = @()
foreach ($r in $roots) {
    Write-Host "Installing -> $r"
    $info = Install-ToTerminal -root $r -eaPath $EaSource -server $ServerUrl -token $Token
    $installed += $info
}

Write-Title "DONE — Installer ka kaam khatam"
Write-Host "EA copy: OK" -ForegroundColor Green
Write-Host "Token config: OK (Files\pumpingbot_config.txt)" -ForegroundColor Green
Write-Host "WebRequest URL common.ini mein add ki koshish: OK" -ForegroundColor Green
Write-Host ""
Write-Host "AB SIRF YEH BACHA (30 second):" -ForegroundColor Yellow
Write-Host "  1) Exness MT5 kholo + apna account LOGIN" -ForegroundColor White
Write-Host "  2) Upar AutoTrading button ON (green)" -ForegroundColor White
Write-Host "  3) Navigator (Ctrl+N) -> Experts -> PumpingBotFollower" -ForegroundColor White
Write-Host "     ko kisi chart pe DRAG karo -> OK" -ForegroundColor White
Write-Host "  (Token pehle se config mein hai — Inputs mein paste zaroori nahi)" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Rozana baad mein: sirf MT5 open + login + AutoTrading ON" -ForegroundColor Cyan

$exe = Find-TerminalExe
if ($exe) {
    Write-Host ""
    Write-Host "MT5 ab khol rahe hain: $exe" -ForegroundColor Green
    Start-Process $exe
}

Write-Host ""
Read-Host "Enter dabao window band karne ke liye"

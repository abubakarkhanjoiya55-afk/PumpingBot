param(
    [Parameter(Mandatory = $true)]
    [string]$InstallDir
)

$ErrorActionPreference = "Stop"

$exe = Join-Path $InstallDir "SceneCutProPlus.exe"
$vbs = Join-Path $InstallDir "desktop\LaunchSilent.vbs"
$launchBat = Join-Path $InstallDir "desktop\Launch.bat"
$iconCandidates = @(
    (Join-Path $InstallDir "desktop\scenecut.ico"),
    (Join-Path $InstallDir "SceneCutProPlus.exe"),
    (Join-Path $InstallDir "static\favicon.ico")
)
$icon = $iconCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

$WshShell = New-Object -ComObject WScript.Shell

function New-AppShortcut([string]$Path) {
    $shortcut = $WshShell.CreateShortcut($Path)
    if (Test-Path $exe) {
        # Packaged professional .exe — CapCut / VLC style
        $shortcut.TargetPath = $exe
        $shortcut.Arguments = ""
    } elseif (Test-Path $vbs) {
        # Silent launcher — no black CMD window
        $shortcut.TargetPath = "wscript.exe"
        $shortcut.Arguments = "`"$vbs`""
    } else {
        $shortcut.TargetPath = $launchBat
        $shortcut.Arguments = ""
    }
    $shortcut.WorkingDirectory = $InstallDir
    $shortcut.WindowStyle = 1
    $shortcut.Description = "SceneCut Pro+ Desktop"
    if ($icon) { $shortcut.IconLocation = "$icon,0" }
    $shortcut.Save()
}

$desktop = [Environment]::GetFolderPath("Desktop")
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\SceneCut Pro+"
New-Item -ItemType Directory -Force -Path $startMenu | Out-Null

New-AppShortcut (Join-Path $desktop "SceneCut Pro+.lnk")
New-AppShortcut (Join-Path $startMenu "SceneCut Pro+.lnk")

$unBat = Join-Path $InstallDir "desktop\UNINSTALL.bat"
if (Test-Path $unBat) {
    $un = $WshShell.CreateShortcut((Join-Path $startMenu "Uninstall SceneCut Pro+.lnk"))
    $un.TargetPath = $unBat
    $un.WorkingDirectory = $InstallDir
    $un.Description = "Uninstall SceneCut Pro+"
    $un.Save()
}

Write-Host "Shortcuts created."

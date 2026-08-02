param(
    [Parameter(Mandatory = $true)]
    [string]$InstallDir
)

$ErrorActionPreference = "Stop"

$launchBat = Join-Path $InstallDir "desktop\Launch.bat"
$vbs = Join-Path $InstallDir "desktop\LaunchSilent.vbs"
$iconCandidates = @(
    (Join-Path $InstallDir "desktop\scenecut.ico"),
    (Join-Path $InstallDir "static\favicon.ico")
)
$icon = $iconCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

$WshShell = New-Object -ComObject WScript.Shell

function New-AppShortcut([string]$Path) {
    $shortcut = $WshShell.CreateShortcut($Path)
    # Prefer silent VBS launcher (no black console window)
    if (Test-Path $vbs) {
        $shortcut.TargetPath = "wscript.exe"
        $shortcut.Arguments = "`"$vbs`""
    } else {
        $shortcut.TargetPath = $launchBat
    }
    $shortcut.WorkingDirectory = $InstallDir
    $shortcut.WindowStyle = 7
    $shortcut.Description = "SceneCut Pro+ Desktop"
    if ($icon) { $shortcut.IconLocation = "$icon,0" }
    $shortcut.Save()
}

$desktop = [Environment]::GetFolderPath("Desktop")
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\SceneCut Pro+"
New-Item -ItemType Directory -Force -Path $startMenu | Out-Null

New-AppShortcut (Join-Path $desktop "SceneCut Pro+.lnk")
New-AppShortcut (Join-Path $startMenu "SceneCut Pro+.lnk")

# Uninstall shortcut in Start Menu
$un = $WshShell.CreateShortcut((Join-Path $startMenu "Uninstall SceneCut Pro+.lnk"))
$un.TargetPath = Join-Path $InstallDir "desktop\UNINSTALL.bat"
$un.WorkingDirectory = $InstallDir
$un.Description = "Uninstall SceneCut Pro+"
$un.Save()

Write-Host "Shortcuts created."

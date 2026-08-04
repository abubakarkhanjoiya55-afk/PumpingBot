# SceneCut Pro+ — professional silent installer (no CMD window)
param(
    [string]$SourceDir = ""
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

if (-not $SourceDir) {
    $SourceDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
}
$SourceDir = (Resolve-Path $SourceDir).Path
$InstallDir = Join-Path $env:LOCALAPPDATA "SceneCutProPlus"
$LogFile = Join-Path $env:TEMP "scenecut-setup.log"

function Write-Log([string]$msg) {
    $line = "$(Get-Date -Format 'HH:mm:ss')  $msg"
    Add-Content -Path $LogFile -Value $line -ErrorAction SilentlyContinue
}

function Set-UiStatus([string]$text, [int]$pct) {
    $script:lbl.Text = $text
    $script:bar.Value = [Math]::Max(0, [Math]::Min(100, $pct))
    [System.Windows.Forms.Application]::DoEvents()
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "SceneCut Pro+ Setup"
$form.Size = New-Object System.Drawing.Size(460, 220)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.BackColor = [System.Drawing.Color]::FromArgb(14, 14, 16)
$form.ForeColor = [System.Drawing.Color]::White
$form.TopMost = $true

$title = New-Object System.Windows.Forms.Label
$title.Text = "SceneCut Pro+"
$title.Font = New-Object System.Drawing.Font("Segoe UI", 16, [System.Drawing.FontStyle]::Bold)
$title.AutoSize = $true
$title.Location = New-Object System.Drawing.Point(24, 22)
$form.Controls.Add($title)

$sub = New-Object System.Windows.Forms.Label
$sub.Text = "Installing desktop app..."
$sub.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$sub.ForeColor = [System.Drawing.Color]::FromArgb(180, 180, 190)
$sub.AutoSize = $true
$sub.Location = New-Object System.Drawing.Point(26, 56)
$form.Controls.Add($sub)

$script:lbl = New-Object System.Windows.Forms.Label
$script:lbl.Text = "Starting..."
$script:lbl.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$script:lbl.Size = New-Object System.Drawing.Size(400, 22)
$script:lbl.Location = New-Object System.Drawing.Point(26, 100)
$form.Controls.Add($script:lbl)

$script:bar = New-Object System.Windows.Forms.ProgressBar
$script:bar.Location = New-Object System.Drawing.Point(26, 130)
$script:bar.Size = New-Object System.Drawing.Size(400, 22)
$script:bar.Style = "Continuous"
$form.Controls.Add($script:bar)

$form.Add_Shown({
    $form.Activate()
    try {
        Write-Log "Install from $SourceDir -> $InstallDir"
        Set-UiStatus "Checking Python..." 8

        $pyCmd = $null
        $pyArgs = @()
        if (Get-Command py -ErrorAction SilentlyContinue) {
            $pyCmd = "py"
            $pyArgs = @("-3")
        } elseif (Get-Command python -ErrorAction SilentlyContinue) {
            $pyCmd = "python"
        } else {
            throw "Python 3.10+ nahi mila. Pehle python.org se install karo (Add to PATH CHECK)."
        }

        Set-UiStatus "Creating app folder..." 18
        New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

        Set-UiStatus "Copying app files..." 30
        $exclude = @(".git", "__pycache__", "output", "_uploads", "projects", ".venv", "venv", "dist", "build", "releases")
        if (Test-Path $InstallDir) {
            Get-ChildItem $InstallDir -Force | Where-Object {
                $_.Name -notin @(".venv", "tools", "projects", "output", "_uploads")
            } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        }
        Get-ChildItem -Path $SourceDir -Force | Where-Object {
            $_.Name -notin $exclude
        } | ForEach-Object {
            Copy-Item -Path $_.FullName -Destination (Join-Path $InstallDir $_.Name) -Recurse -Force
        }

        Set-UiStatus "Creating Python environment..." 45
        $venvPy = Join-Path $InstallDir ".venv\Scripts\python.exe"
        if (-not (Test-Path $venvPy)) {
            & $pyCmd @pyArgs -m venv (Join-Path $InstallDir ".venv")
            if ($LASTEXITCODE -ne 0) { throw "venv create fail" }
        }

        Set-UiStatus "Installing packages..." 60
        & $venvPy -m pip install --upgrade pip | Out-Null
        & $venvPy -m pip install -r (Join-Path $InstallDir "requirements.txt")
        if ($LASTEXITCODE -ne 0) { throw "pip install fail — internet check karo" }

        Set-UiStatus "Setting up ffmpeg..." 78
        $ff = Join-Path $InstallDir "desktop\setup_ffmpeg.ps1"
        if (Test-Path $ff) {
            try {
                powershell -NoProfile -ExecutionPolicy Bypass -File $ff -InstallDir $InstallDir | Out-Null
            } catch {
                Write-Log "ffmpeg setup warning: $_"
            }
        }

        Set-UiStatus "Creating Desktop shortcut..." 90
        $sc = Join-Path $InstallDir "desktop\create_shortcuts.ps1"
        if (Test-Path $sc) {
            powershell -NoProfile -ExecutionPolicy Bypass -File $sc -InstallDir $InstallDir | Out-Null
        }

        Set-UiStatus "Starting SceneCut Pro+..." 100
        Start-Sleep -Milliseconds 400
        $vbs = Join-Path $InstallDir "desktop\LaunchSilent.vbs"
        if (Test-Path $vbs) {
            Start-Process -FilePath "wscript.exe" -ArgumentList "`"$vbs`""
        } else {
            $launch = Join-Path $InstallDir "desktop\Launch.bat"
            Start-Process -FilePath $launch -WindowStyle Hidden
        }

        Write-Log "Install OK"
        $form.Close()
    } catch {
        Write-Log "FAIL: $_"
        [System.Windows.Forms.MessageBox]::Show(
            "$_`n`nLog: $LogFile",
            "SceneCut Pro+ Setup",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
        $form.Close()
    }
})

[void]$form.ShowDialog()

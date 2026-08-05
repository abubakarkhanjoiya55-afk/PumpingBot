param(
    [Parameter(Mandatory = $true)]
    [string]$InstallDir
)

$ErrorActionPreference = "Continue"
$tools = Join-Path $InstallDir "tools\ffmpeg"
$ffmpegExe = Join-Path $tools "bin\ffmpeg.exe"

function Test-Ffmpeg {
    try {
        $p = Get-Command ffmpeg -ErrorAction SilentlyContinue
        if ($p) { return $true }
    } catch {}
    return (Test-Path $ffmpegExe)
}

if (Test-Ffmpeg) {
    Write-Host "ffmpeg already OK"
    if (Test-Path $ffmpegExe) {
        Write-Host "Using bundled: $ffmpegExe"
    }
    exit 0
}

Write-Host "ffmpeg missing — auto install try..."

# 1) winget (best on modern Windows)
try {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "winget se Gyan.FFmpeg install..."
        & winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements --silent
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path", "User")
        if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
            Write-Host "ffmpeg OK (winget)"
            exit 0
        }
    }
} catch {
    Write-Host "winget path fail — portable download try..."
}

# 2) Portable ffmpeg into app folder (no admin needed)
New-Item -ItemType Directory -Force -Path $tools | Out-Null
$zip = Join-Path $env:TEMP "scenecut-ffmpeg-essentials.zip"
$url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
Write-Host "Downloading portable ffmpeg..."
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Write-Host "Extracting..."
    if (Test-Path $tools) { Remove-Item -Recurse -Force $tools -ErrorAction SilentlyContinue }
    New-Item -ItemType Directory -Force -Path $tools | Out-Null
    Expand-Archive -Path $zip -DestinationPath $tools -Force
    # gyan zip has a versioned top folder — flatten to tools\ffmpeg\bin
    $inner = Get-ChildItem $tools -Directory | Select-Object -First 1
    if ($inner -and (Test-Path (Join-Path $inner.FullName "bin\ffmpeg.exe"))) {
        $binSrc = Join-Path $inner.FullName "bin"
        $binDst = Join-Path $tools "bin"
        New-Item -ItemType Directory -Force -Path $binDst | Out-Null
        Copy-Item -Path (Join-Path $binSrc "*") -Destination $binDst -Recurse -Force
    }
    if (Test-Path $ffmpegExe) {
        Write-Host "ffmpeg OK (portable): $ffmpegExe"
        exit 0
    }
} catch {
    Write-Host "ffmpeg auto download fail: $($_.Exception.Message)"
}

Write-Host "WARN: ffmpeg auto-install fail. Manual: winget install Gyan.FFmpeg"
exit 0

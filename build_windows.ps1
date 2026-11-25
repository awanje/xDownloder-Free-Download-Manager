# Builds the Windows app bundle, a portable zip, and (if Inno Setup is installed)
# the installer. Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File build_windows.ps1 -Version 1.0.0
param(
    [string]$Version = "1.0.0",
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "== Installing build dependencies =="
& $Python -m pip install --quiet -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "== Building app bundle with PyInstaller =="
& $Python -m PyInstaller --noconfirm --clean --windowed `
    --name "X Downloader" --icon "assets/icon.ico" main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$bundle = Join-Path $PSScriptRoot "dist\X Downloader"
$exe = Join-Path $bundle "X Downloader.exe"

Write-Host "== Self-testing the packaged build =="
$proc = Start-Process -FilePath $exe -ArgumentList "--selftest" -Wait -PassThru
if ($proc.ExitCode -ne 0) { throw "Packaged build failed its selftest (exit $($proc.ExitCode))" }

# Ship the browser extension next to the app so users can "Load unpacked" it.
Copy-Item -Recurse -Force (Join-Path $PSScriptRoot "extension") (Join-Path $bundle "extension")

Write-Host "== Creating portable zip =="
$zip = Join-Path $PSScriptRoot "dist\X-Downloader-$Version-windows-portable.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path $bundle -DestinationPath $zip

Write-Host "== Building installer =="
$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($iscc) {
    & $iscc "/DMyAppVersion=$Version" (Join-Path $PSScriptRoot "installer\xdownloader.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
} else {
    Write-Warning "Inno Setup 6 not found - skipped the installer. Install it from https://jrsoftware.org/isinfo.php or let the GitHub Actions workflow build it."
}

Write-Host "`nDone. Output in dist\"
Get-ChildItem (Join-Path $PSScriptRoot "dist") -File | Format-Table Name, @{n="MB";e={[math]::Round($_.Length/1MB,1)}}

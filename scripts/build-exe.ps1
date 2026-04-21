<# Build RecallKB.exe
   Run from repo root with the venv active (or use .venv\Scripts\Activate.ps1 first).
#>
$ErrorActionPreference = 'Stop'

Push-Location $PSScriptRoot\..

# Activate venv if not already
if (-not $env:VIRTUAL_ENV) {
    & .venv\Scripts\Activate.ps1
}

Write-Host '--- Building RecallKB desktop app ---' -ForegroundColor Cyan

# Clean previous build
if (Test-Path dist\RecallKB) { Remove-Item dist\RecallKB -Recurse -Force }

# Run PyInstaller
& pyinstaller recall.spec --noconfirm --clean

if ($LASTEXITCODE -ne 0) {
    Write-Host 'PyInstaller failed.' -ForegroundColor Red
    Pop-Location
    exit 1
}

Write-Host ''
Write-Host '=== Build complete ===' -ForegroundColor Green
Write-Host "Output: dist\RecallKB\RecallKB.exe"
Write-Host "To run:  .\dist\RecallKB\RecallKB.exe"
Write-Host ''

Pop-Location

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

& $python -m pip install --upgrade pip | Out-Null
& $python -m pip install -r requirements-local.txt | Out-Null

& $python -m kb_app.tray

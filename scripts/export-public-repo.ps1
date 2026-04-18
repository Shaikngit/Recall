param(
    [string]$OutputPath = (Join-Path $PSScriptRoot "..\.public-export\mykb-public")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$resolvedOutput = if ([System.IO.Path]::IsPathRooted($OutputPath)) {
    [System.IO.Path]::GetFullPath($OutputPath)
}
else {
    [System.IO.Path]::GetFullPath((Join-Path $repoRoot $OutputPath))
}

$includePaths = @(
    ".gitignore",
    ".webappignore",
    "azure.yaml",
    "deploy-local.ps1",
    "launch-kb.ps1",
    "README.md",
    "requirements-local.txt",
    "requirements.txt",
    "docs",
    "infra",
    "kb_app",
    "scripts"
)

if (Test-Path $resolvedOutput) {
    Remove-Item -Path $resolvedOutput -Recurse -Force
}

New-Item -ItemType Directory -Path $resolvedOutput | Out-Null

foreach ($relativePath in $includePaths) {
    $sourcePath = Join-Path $repoRoot $relativePath
    if (-not (Test-Path $sourcePath)) {
        continue
    }

    $destinationPath = Join-Path $resolvedOutput $relativePath
    $destinationParent = Split-Path -Parent $destinationPath
    if ($destinationParent -and -not (Test-Path $destinationParent)) {
        New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
    }

    Copy-Item -Path $sourcePath -Destination $destinationPath -Recurse -Force
}

Write-Host "Public repo export created at $resolvedOutput" -ForegroundColor Green
Write-Host "Initialize a new git repository there before pushing to a new public GitHub repo." -ForegroundColor Cyan
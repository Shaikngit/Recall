param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory = $true)]
    [string]$AppName,

    [string]$BaseUrl,
    [switch]$Login,
    [switch]$SkipSmokeTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repoRoot

function Assert-Command {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

Assert-Command az
Assert-Command pwsh

if ($Login) {
    az login | Out-Null
}

$stagingPath = Join-Path $repoRoot ".azure\manual-web"
$zipPath = Join-Path $repoRoot ".azure\manual-web.zip"
$excludedTopLevel = @('.git', '.azure', '.github', '.vscode', '.venv', '.recall', '__pycache__')

if (Test-Path $stagingPath) {
    Remove-Item -Path $stagingPath -Recurse -Force
}

New-Item -ItemType Directory -Path $stagingPath -Force | Out-Null

Get-ChildItem -Path $repoRoot -Force |
    Where-Object { $excludedTopLevel -notcontains $_.Name -and $_.Extension -ne '.zip' } |
    ForEach-Object {
        Copy-Item $_.FullName -Destination $stagingPath -Recurse -Force
    }

Get-ChildItem -Path $stagingPath -Recurse -Directory -Force |
    Where-Object { $_.Name -eq '__pycache__' } |
    Remove-Item -Recurse -Force

Get-ChildItem -Path $stagingPath -Recurse -Include *.pyc | Remove-Item -Force

if (Test-Path $zipPath) {
    Remove-Item -Path $zipPath -Force
}

Compress-Archive -Path (Join-Path $stagingPath '*') -DestinationPath $zipPath -Force

Write-Host "Deploying code package to existing App Service $AppName" -ForegroundColor Cyan
az webapp deploy --resource-group $ResourceGroup --name $AppName --src-path $zipPath --type zip --clean true --restart true --track-status true --async false --timeout 600000

if ($PSBoundParameters.ContainsKey('BaseUrl') -and $BaseUrl) {
    $health = Invoke-RestMethod -Uri "$($BaseUrl.TrimEnd('/'))/healthz"
    if ($health.status -ne 'ok') {
        throw "Health check failed after deployment."
    }

    Write-Host "Health check passed." -ForegroundColor Green

    if (-not $SkipSmokeTest) {
        pwsh -NoProfile -File "$repoRoot\scripts\smoke-test.ps1" -BaseUrl $BaseUrl
    }
}
else {
    Write-Host "BaseUrl was not supplied, so hosted verification was skipped." -ForegroundColor Yellow
}
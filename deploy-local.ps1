param(
    [string]$EnvironmentName = "production",
    [string]$Location = "eastus",
    [ValidateSet('existing', 'new')]
    [string]$OpenAiMode = "existing",
    [string]$OpenAiResourceId,
    [string]$OpenAiDeployment,
    [string]$OpenAiModelName = "gpt-4.1-mini",
    [int]$OpenAiDeploymentCapacity = 1,
    [string]$OpenAiAccountName,
    [string]$BaseUrl,
    [switch]$Login,
    [switch]$SkipSmokeTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

function Assert-Command {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

Assert-Command azd
Assert-Command az
Assert-Command pwsh

if ($Login) {
    azd auth login
}

$envSelectFailed = $false
try {
    azd env select $EnvironmentName | Out-Null
}
catch {
    $envSelectFailed = $true
}

if ($envSelectFailed) {
    azd env new $EnvironmentName --no-prompt
}

azd env set AZURE_LOCATION $Location
azd env set AZURE_OPENAI_MODE $OpenAiMode

if ($PSBoundParameters.ContainsKey('OpenAiResourceId')) {
    azd env set AZURE_OPENAI_RESOURCE_ID $OpenAiResourceId
}

if ($PSBoundParameters.ContainsKey('OpenAiDeployment')) {
    azd env set AZURE_OPENAI_DEPLOYMENT $OpenAiDeployment
}

if ($PSBoundParameters.ContainsKey('OpenAiModelName')) {
    azd env set AZURE_OPENAI_MODEL_NAME $OpenAiModelName
}

if ($PSBoundParameters.ContainsKey('OpenAiDeploymentCapacity')) {
    azd env set AZURE_OPENAI_DEPLOYMENT_CAPACITY $OpenAiDeploymentCapacity
}

if ($PSBoundParameters.ContainsKey('OpenAiAccountName')) {
    azd env set AZURE_OPENAI_ACCOUNT_NAME $OpenAiAccountName
}

Write-Host "Running azd provision --preview" -ForegroundColor Cyan
azd provision --preview

Write-Host "Running azd deploy --no-prompt" -ForegroundColor Cyan
azd deploy --no-prompt

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

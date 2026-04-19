param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory = $true)]
    [string]$AppName,

    [Parameter(Mandatory = $true)]
    [string]$StorageAccountName,

    [string]$Location,
    [string]$ShareName = 'mykb-content',
    [string]$MountName = 'kbcontent',
    [string]$MountPath = '/mounts/mykb-content',
    [int]$ShareQuotaGiB = 100,
    [ValidateSet('Standard_LRS', 'Standard_ZRS')]
    [string]$StorageSkuName = 'Standard_ZRS',
    [switch]$Login,
    [switch]$PreviewOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repoRoot

function Assert-Command {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

Assert-Command az

if ($Login) {
    az login | Out-Null
}

if (-not $PSBoundParameters.ContainsKey('Location') -or [string]::IsNullOrWhiteSpace($Location)) {
    $Location = az webapp show --resource-group $ResourceGroup --name $AppName --query location --output tsv
}

$templatePath = Join-Path $repoRoot 'infra\existing-appservice-storage.bicep'

$deploymentArgs = @(
    'deployment', 'group', 'what-if',
    '--resource-group', $ResourceGroup,
    '--template-file', $templatePath,
    '--parameters',
    "appName=$AppName",
    "location=$Location",
    "storageAccountName=$StorageAccountName",
    "shareName=$ShareName",
    "mountName=$MountName",
    "mountPath=$MountPath",
    "shareQuotaGiB=$ShareQuotaGiB",
    "storageSkuName=$StorageSkuName"
)

Write-Host 'Running what-if for existing App Service Azure Files configuration' -ForegroundColor Cyan
az @deploymentArgs

if ($PreviewOnly) {
    Write-Host 'PreviewOnly was specified, so no changes were deployed.' -ForegroundColor Yellow
    exit 0
}

$deploymentArgs[2] = 'create'

Write-Host 'Applying Azure Files configuration to existing App Service' -ForegroundColor Cyan
az @deploymentArgs

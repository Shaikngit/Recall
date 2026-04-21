<#
.SYNOPSIS
    Restricts App Service access to Azure network traffic only (covers Global Secure Access).
.DESCRIPTION
    Applies the AzureCloud service tag to allow traffic from Azure's network
    (which includes Global Secure Access / Entra VPN egress) while blocking
    all other internet traffic. GSA uses rotating egress IPs so individual
    IP restrictions don't work — the service tag covers the entire pool.
.PARAMETER ResourceGroup
    Azure resource group name.
.PARAMETER AppName
    Azure App Service name.
.PARAMETER RuleName
    Name for the service tag rule (default: AzureCloud-GSA).
.EXAMPLE
    .\update-ip-restriction.ps1
.EXAMPLE
    .\update-ip-restriction.ps1 -ResourceGroup rg-mykb-shaikn -AppName app-mykbshaikn-th6h7z
#>
param(
    [string]$ResourceGroup = "rg-mykb-shaikn",
    [string]$AppName       = "app-mykbshaikn-th6h7z",
    [string]$RuleName      = "AzureCloud-GSA"
)

$ErrorActionPreference = "Stop"

# Check if the rule already exists
Write-Host "Checking existing access restrictions..." -ForegroundColor Cyan
$existing = az webapp config access-restriction show `
    --name $AppName --resource-group $ResourceGroup `
    --query "ipSecurityRestrictions[?name=='$RuleName'].name" -o tsv 2>&1

if ($existing -eq $RuleName) {
    Write-Host "AzureCloud service tag rule already exists — no changes needed." -ForegroundColor Green
} else {
    # Add AzureCloud service tag for main site
    Write-Host "Adding AzureCloud service tag (main site)..." -ForegroundColor Cyan
    az webapp config access-restriction add `
        --name $AppName --resource-group $ResourceGroup `
        --rule-name $RuleName --priority 100 --action Allow `
        --service-tag AzureCloud -o none 2>&1

    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to add main site restriction." -ForegroundColor Red
        exit 1
    }
}

# Check SCM site
$scmExisting = az webapp config access-restriction show `
    --name $AppName --resource-group $ResourceGroup `
    --query "scmIpSecurityRestrictions[?name=='$RuleName'].name" -o tsv 2>&1

if ($scmExisting -eq $RuleName) {
    Write-Host "SCM site rule already exists." -ForegroundColor Green
} else {
    Write-Host "Adding AzureCloud service tag (SCM/deployment site)..." -ForegroundColor Cyan
    az webapp config access-restriction add `
        --name $AppName --resource-group $ResourceGroup `
        --rule-name $RuleName --priority 100 --action Allow `
        --service-tag AzureCloud --scm-site -o none 2>&1
}

# Quick verification
Write-Host "`nVerifying access..." -ForegroundColor Cyan
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $health = Invoke-RestMethod -Uri "https://$AppName.azurewebsites.net/healthz" -TimeoutSec 15
    Write-Host "Access confirmed — health check: $($health.status)" -ForegroundColor Green
} catch {
    Write-Host "WARNING: Health check failed (may need a few seconds to propagate): $_" -ForegroundColor Yellow
}

Write-Host "`nDone. Only Azure network traffic (incl. GSA/Entra VPN) can reach $AppName." -ForegroundColor Green

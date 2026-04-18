param(
    [string]$BaseUrl = "http://127.0.0.1:8765"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$base = $BaseUrl.TrimEnd('/')
$marker = "SMOKE-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$captureNote = @"
Smoke test note for $marker
Service: MyKB
Learning: smoke validation path
"@

function Invoke-JsonPost {
    param(
        [string]$Url,
        [hashtable]$Payload
    )

    $body = $Payload | ConvertTo-Json -Depth 10
    return Invoke-RestMethod -Method Post -Uri $Url -ContentType 'application/json' -Body $body
}

Write-Host "Testing $base" -ForegroundColor Cyan

$rootResponse = Invoke-WebRequest -Uri "$base/" -UseBasicParsing
if ($rootResponse.StatusCode -ne 200) {
    throw "Root page failed with status $($rootResponse.StatusCode)."
}

$health = Invoke-RestMethod -Uri "$base/healthz"
if ($health.status -ne 'ok') {
    throw "Health endpoint did not return status ok."
}

$recent = Invoke-RestMethod -Uri "$base/api/recent"
if ($null -eq $recent) {
    throw "Recent endpoint returned null."
}

$capture = Invoke-JsonPost -Url "$base/api/capture" -Payload @{ note = $captureNote }
if (-not $capture.savedTo) {
    throw "Capture did not return a savedTo value."
}

$ask = Invoke-JsonPost -Url "$base/api/ask" -Payload @{ query = $marker; history = @() }
if (-not $ask.answer) {
    throw "Ask endpoint did not return an answer."
}
if (-not $ask.results -or $ask.results.Count -lt 1) {
    throw "Ask endpoint did not return any source results."
}

$firstResult = $ask.results[0]
if (-not $firstResult.path -or $firstResult.path -notlike "*$($capture.savedTo)") {
    throw "Top result was not the note created by the smoke test. Top result path: $($firstResult.path)"
}

Write-Host "Root: OK" -ForegroundColor Green
Write-Host "Health: OK" -ForegroundColor Green
Write-Host "Recent: OK ($($recent.Count) item(s))" -ForegroundColor Green
Write-Host "Capture: $($capture.savedTo)" -ForegroundColor Green
Write-Host "Ask: OK" -ForegroundColor Green
Write-Host "Top source: $($firstResult.path)" -ForegroundColor Green
Write-Host "Smoke test passed." -ForegroundColor Green
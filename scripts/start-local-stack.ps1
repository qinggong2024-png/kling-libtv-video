param(
    [int]$StartupTimeoutSeconds = 45
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$apiScript = Join-Path $PSScriptRoot 'start-local-api.ps1'
$frontendScript = Join-Path $PSScriptRoot 'start-local-frontend.ps1'
$checkScript = Join-Path $PSScriptRoot 'check-local-services.ps1'
$logDir = Join-Path $projectRoot 'var\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Test-Ready([string]$Uri) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2
        return $response.StatusCode -eq 200
    }
    catch { return $false }
}

if (-not (Test-Ready 'http://127.0.0.1:8000/api/v1/health/ready')) {
    Start-Process `
        -FilePath 'powershell.exe' `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $apiScript) `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden | Out-Null
}

if (-not (Test-Ready 'http://127.0.0.1:5173/')) {
    Start-Process `
        -FilePath 'powershell.exe' `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $frontendScript) `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden | Out-Null
}

$deadline = [DateTimeOffset]::Now.AddSeconds($StartupTimeoutSeconds)
do {
    $apiReady = Test-Ready 'http://127.0.0.1:8000/api/v1/health/ready'
    $frontendReady = Test-Ready 'http://127.0.0.1:5173/'
    $proxyReady = Test-Ready 'http://127.0.0.1:5173/api/v1/health/ready'
    if ($apiReady -and $frontendReady -and $proxyReady) { break }
    Start-Sleep -Milliseconds 500
} while ([DateTimeOffset]::Now -lt $deadline)

if (-not ($apiReady -and $frontendReady -and $proxyReady)) {
    Write-Error "Local stack did not become ready within $StartupTimeoutSeconds seconds."
    foreach ($name in @('migration.autostart.log', 'api.autostart.log', 'frontend.autostart.log')) {
        $path = Join-Path $logDir $name
        if (Test-Path -LiteralPath $path) {
            Write-Host "--- $name ---"
            Get-Content -LiteralPath $path -Tail 30
        }
    }
    exit 1
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $checkScript -RequireFrontend
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host 'Local stack is ready: http://127.0.0.1:5173'

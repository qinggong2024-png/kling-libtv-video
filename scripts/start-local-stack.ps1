param(
    [int]$StartupTimeoutSeconds = 45
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$apiScript = Join-Path $PSScriptRoot 'start-local-api.ps1'
$frontendScript = Join-Path $PSScriptRoot 'start-local-frontend.ps1'
$checkScript = Join-Path $PSScriptRoot 'check-local-services.ps1'
$logDir = Join-Path $projectRoot 'var\logs'
. (Join-Path $PSScriptRoot 'local-instance-identity.ps1')
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Test-Ready([string]$Uri, [int]$Port) {
    $identity = Get-WorkspacePortIdentity -Port $Port -ProjectRoot $projectRoot
    if (-not $identity.Listening -or -not $identity.OwnedByWorkspace) {
        return $false
    }
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2
        return $response.StatusCode -eq 200
    }
    catch { return $false }
}

Assert-WorkspacePortOwnership -Port 8000 -ProjectRoot $projectRoot -ServiceName 'API' | Out-Null
Assert-WorkspacePortOwnership -Port 5173 -ProjectRoot $projectRoot -ServiceName 'frontend' | Out-Null

if (-not (Test-Ready 'http://127.0.0.1:8000/api/v1/health/ready' 8000)) {
    Start-Process `
        -FilePath 'powershell.exe' `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $apiScript) `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden | Out-Null
}

if (-not (Test-Ready 'http://127.0.0.1:5173/' 5173)) {
    Start-Process `
        -FilePath 'powershell.exe' `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $frontendScript) `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden | Out-Null
}

$deadline = [DateTimeOffset]::Now.AddSeconds($StartupTimeoutSeconds)
do {
    Assert-WorkspacePortOwnership -Port 8000 -ProjectRoot $projectRoot -ServiceName 'API' | Out-Null
    Assert-WorkspacePortOwnership -Port 5173 -ProjectRoot $projectRoot -ServiceName 'frontend' | Out-Null
    $apiReady = Test-Ready 'http://127.0.0.1:8000/api/v1/health/ready' 8000
    $frontendReady = Test-Ready 'http://127.0.0.1:5173/' 5173
    $proxyReady = Test-Ready 'http://127.0.0.1:5173/api/v1/health/ready' 5173
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

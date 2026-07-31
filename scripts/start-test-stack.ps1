param(
    [int]$ApiPort = 8001,
    [int]$FrontendPort = 5175,
    [int]$StartupTimeoutSeconds = 60
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'local-instance-identity.ps1')
$logDir = Join-Path $projectRoot 'var\test\logs'
$databasePath = (Join-Path $projectRoot 'var\test\development.db').Replace('\', '/')
$artifactRoot = Join-Path $projectRoot 'var\test\artifacts'
$runnerRoot = Join-Path $projectRoot 'var\test\runner'
$runtimeRoot = Join-Path $projectRoot 'var\test\runtime'
$processFile = Join-Path $runtimeRoot 'stack-processes.json'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$appDir = Join-Path $projectRoot 'backend\src'

New-Item -ItemType Directory -Force -Path $logDir, $artifactRoot, $runnerRoot, $runtimeRoot | Out-Null

function Test-Ready([string]$Uri) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 3
        return $response.StatusCode -eq 200
    }
    catch { return $false }
}

function Stop-RecordedProcesses {
    if (-not (Test-Path -LiteralPath $processFile)) { return }
    $record = Get-Content -Raw -LiteralPath $processFile | ConvertFrom-Json
    $targets = @(
        [pscustomobject]@{ processId = $record.apiPid; port = $ApiPort; name = 'API' },
        [pscustomobject]@{ processId = $record.frontendPid; port = $FrontendPort; name = 'frontend' }
    )
    foreach ($target in $targets) {
        if (-not $target.processId) { continue }
        $identity = Get-WorkspacePortIdentity -Port $target.port -ProjectRoot $projectRoot
        if ($identity.Listening -and $identity.OwnedByWorkspace -and
            $identity.ProcessId -eq $target.processId) {
            Stop-Process -Id $target.processId -Force
        }
        elseif (Get-Process -Id $target.processId -ErrorAction SilentlyContinue) {
            Write-Warning "Ignoring stale $($target.name) PID $($target.processId); ownership could not be verified."
        }
    }
    Remove-Item -LiteralPath $processFile -Force
    Start-Sleep -Milliseconds 500
}

function Assert-PortAvailable([int]$Port) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) {
        throw "Port $Port is already owned by PID $($listener.OwningProcess)."
    }
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found: $python"
}
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\node_modules'))) {
    throw 'Frontend dependencies are missing.'
}

Stop-RecordedProcesses
Assert-PortAvailable $ApiPort
Assert-PortAvailable $FrontendPort

# Test instances have their own database, files, cookies, ports, and disabled paid execution.
$env:APP_ENV = 'test'
$env:APP_HOST = '127.0.0.1'
$env:APP_PORT = "$ApiPort"
$env:APP_PUBLIC_ORIGINS = "http://127.0.0.1:$FrontendPort,http://localhost:$FrontendPort"
$env:DATABASE_URL = "sqlite+aiosqlite:///$databasePath"
$env:OBJECT_STORE_MODE = 'local'
$env:OBJECT_STORE_PREFIX = 'test'
$env:ARTIFACT_ROOT = $artifactRoot
$env:RUNNER_ROOT = $runnerRoot
$env:ADMIN_CREDENTIALS_FILE = Join-Path $runtimeRoot 'admin-credentials.json'
$env:LIBTV_CONFIG_DIR = Join-Path $runtimeRoot 'libtv'
$env:SHARED_AUTHENTICATION_ENABLED = 'false'
$env:SESSION_COOKIE_NAME = 'libtv_test_session'
$env:CSRF_COOKIE_NAME = 'libtv_test_csrf'
$env:SESSION_COOKIE_SECURE = 'false'
$env:AI_ADAPTER_MODE = 'fake'
$env:LIBTV_ADAPTER_MODE = 'fake'
$env:LIBTV_EXECUTION_MODE = 'dry-run'
$env:PAID_GENERATION_ENABLED = 'false'
$env:PAID_SUBMISSIONS_PAUSED = 'true'
$env:KLING_CLI_ENABLED = 'false'
$env:KLING_API_ENABLED = 'false'
$env:KLING_ADMIN_CONFIG_FILE = Join-Path $runtimeRoot 'kling-config.json'
$env:KLING_ENABLE_PAID_INTEGRATION_TEST = 'false'
$env:KLING_API_ENABLE_PAID_INTEGRATION_TEST = 'false'
$env:WAVESPEED_ENABLED = 'false'
$env:WAVESPEED_ADMIN_CONFIG_FILE = Join-Path $runtimeRoot 'wavespeed-config.json'
$env:OPENAI_MODEL = 'gpt-5.6-luna'
$env:OPENAI_ANALYSIS_FALLBACK_MODEL = 'gpt-5.6-terra'
$env:OPENAI_REASONING_EFFORT = 'none'
$env:OPENAI_ANALYSIS_FALLBACK_REASONING_EFFORT = 'low'
$env:OPENAI_ANALYSIS_VERBOSITY = 'low'
$env:OPENAI_ANALYSIS_MAX_OUTPUT_TOKENS = '4000'
$env:OPENAI_ANALYSIS_FALLBACK_MAX_OUTPUT_TOKENS = '6000'
$env:VITE_API_PROXY = "http://127.0.0.1:$ApiPort"

Push-Location $projectRoot
try {
    & uv run alembic -c backend/alembic.ini upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Test database migration failed.' }

    $api = Start-Process -FilePath $python `
        -ArgumentList @('-m', 'uvicorn', 'libtv_agent.app:create_app', '--factory', '--app-dir', $appDir, '--port', $ApiPort) `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDir 'api.log') `
        -RedirectStandardError (Join-Path $logDir 'api.error.log')

    $frontend = Start-Process -FilePath 'npm.cmd' `
        -ArgumentList @('run', 'dev', '--prefix', 'frontend', '--', '--host', '127.0.0.1', '--port', $FrontendPort, '--strictPort') `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDir 'frontend.log') `
        -RedirectStandardError (Join-Path $logDir 'frontend.error.log')

    @{ apiPid = $api.Id; frontendPid = $frontend.Id } |
        ConvertTo-Json |
        Set-Content -Encoding ascii -LiteralPath $processFile

    $deadline = [DateTimeOffset]::Now.AddSeconds($StartupTimeoutSeconds)
    do {
        $apiReady = Test-Ready "http://127.0.0.1:$ApiPort/api/v1/health/ready"
        $frontendReady = Test-Ready "http://127.0.0.1:$FrontendPort/"
        $proxyReady = Test-Ready "http://127.0.0.1:$FrontendPort/api/v1/health/ready"
        if ($apiReady -and $frontendReady -and $proxyReady) { break }
        if ($api.HasExited -or $frontend.HasExited) { break }
        Start-Sleep -Milliseconds 500
    } while ([DateTimeOffset]::Now -lt $deadline)

    if (-not ($apiReady -and $frontendReady -and $proxyReady)) {
        throw "Test stack did not become ready. See $logDir"
    }
    $apiListener = Get-NetTCPConnection -State Listen -LocalPort $ApiPort |
        Select-Object -First 1
    $frontendListener = Get-NetTCPConnection -State Listen -LocalPort $FrontendPort |
        Select-Object -First 1
    @{ apiPid = $apiListener.OwningProcess; frontendPid = $frontendListener.OwningProcess } |
        ConvertTo-Json |
        Set-Content -Encoding ascii -LiteralPath $processFile
    Write-Host "Test stack is ready: http://127.0.0.1:$FrontendPort"
}
finally {
    Pop-Location
}

param(
    [int]$ApiPort = 8001,
    [int]$FrontendPort = 5175,
    [ValidateSet('Safe', 'Full')]
    [string]$Profile = 'Safe',
    [int]$StartupTimeoutSeconds = 60
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'local-instance-identity.ps1')
$sourceRevision = Get-WorkspaceSourceRevision -ProjectRoot $projectRoot
$storageName = if ($Profile -eq 'Full') { 'test-live' } else { 'test' }
$storageRoot = Join-Path $projectRoot ("var\" + $storageName)
$logDir = Join-Path $storageRoot 'logs'
$databasePath = (Join-Path $storageRoot 'development.db').Replace('\', '/')
$artifactRoot = Join-Path $storageRoot 'artifacts'
$runnerRoot = Join-Path $storageRoot 'runner'
$runtimeRoot = Join-Path $storageRoot 'runtime'
$processFile = Join-Path $runtimeRoot 'stack-processes.json'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$appDir = Join-Path $projectRoot 'backend\src'
$runnerScript = Join-Path $appDir 'libtv_agent\runner\local_runner.py'

New-Item -ItemType Directory -Force -Path $logDir, $artifactRoot, $runnerRoot, $runtimeRoot | Out-Null

function Test-Ready([string]$Uri) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 3
        return $response.StatusCode -eq 200
    }
    catch { return $false }
}

function Test-RunnerReady([int]$Port) {
    try {
        $operations = Invoke-RestMethod `
            -Headers @{ 'X-User-Id' = '00000000-0000-0000-0000-000000000099' } `
            -Uri "http://127.0.0.1:$Port/api/v1/admin/operations" `
            -TimeoutSec 3
        $runner = @($operations.runners) |
            Where-Object { $_.status -eq 'ONLINE' -and $_.lastHeartbeatAt } |
            Select-Object -First 1
        if (-not $runner) { return $false }
        $heartbeat = [DateTimeOffset]::Parse(
            [string]$runner.lastHeartbeatAt,
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::AssumeUniversal
        )
        return ([DateTimeOffset]::Now - $heartbeat).TotalSeconds -le 10
    }
    catch { return $false }
}

function Stop-RecordedProcesses([string]$RecordedProcessFile) {
    if (-not (Test-Path -LiteralPath $RecordedProcessFile)) { return }
    $record = Get-Content -Raw -LiteralPath $RecordedProcessFile | ConvertFrom-Json
    $recordedApiPort = if ($record.apiPort) { [int]$record.apiPort } else { $ApiPort }
    $recordedFrontendPort = if ($record.frontendPort) { [int]$record.frontendPort } else { $FrontendPort }
    $targets = @(
        [pscustomobject]@{ processId = $record.apiPid; port = $recordedApiPort; name = 'API' },
        [pscustomobject]@{ processId = $record.frontendPid; port = $recordedFrontendPort; name = 'frontend' }
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
    if ($record.runnerPid) {
        $runner = Get-CimInstance Win32_Process `
            -Filter "ProcessId = $($record.runnerPid)" `
            -ErrorAction SilentlyContinue
        if ($runner -and [string]$runner.CommandLine -like "*$runnerScript*") {
            Stop-Process -Id $record.runnerPid -Force -ErrorAction SilentlyContinue
        }
        elseif (Get-Process -Id $record.runnerPid -ErrorAction SilentlyContinue) {
            Write-Warning "Ignoring stale Runner PID $($record.runnerPid); ownership could not be verified."
        }
    }
    Remove-Item -LiteralPath $RecordedProcessFile -Force
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

$recordedProcessFiles = @(
    (Join-Path $projectRoot 'var\test\runtime\stack-processes.json'),
    (Join-Path $projectRoot 'var\test-live\runtime\stack-processes.json')
) | Select-Object -Unique
foreach ($recordedProcessFile in $recordedProcessFiles) {
    Stop-RecordedProcesses $recordedProcessFile
}
Assert-PortAvailable $ApiPort
Assert-PortAvailable $FrontendPort

# Every profile has its own database, files, cookies, ports, and Runner. Full is
# an explicit live-provider profile; Safe remains suitable for zero-cost checks.
$env:APP_ENV = if ($Profile -eq 'Full') { 'development' } else { 'test' }
$env:DEPLOYMENT_ID = "libtv-agent-$storageName"
$env:DEPLOYMENT_SOURCE_REVISION = $sourceRevision
$env:APP_HOST = '127.0.0.1'
$env:APP_PORT = "$ApiPort"
$env:APP_PUBLIC_ORIGINS = "http://127.0.0.1:$FrontendPort,http://localhost:$FrontendPort"
$env:DATABASE_URL = "sqlite+aiosqlite:///$databasePath"
$env:OBJECT_STORE_MODE = 'local'
$env:OBJECT_STORE_PREFIX = $storageName
$env:ARTIFACT_ROOT = $artifactRoot
$env:RUNNER_ROOT = $runnerRoot
$env:ADMIN_CREDENTIALS_FILE = Join-Path $runtimeRoot 'admin-credentials.json'
$env:LIBTV_CONFIG_DIR = Join-Path $runtimeRoot 'libtv'
$env:SHARED_AUTHENTICATION_ENABLED = 'false'
$env:SESSION_COOKIE_NAME = 'libtv_test_session'
$env:CSRF_COOKIE_NAME = 'libtv_test_csrf'
$env:SESSION_COOKIE_SECURE = 'false'
$env:RUNNER_POLL_SECONDS = '1'
$env:KLING_ADMIN_CONFIG_FILE = Join-Path $runtimeRoot 'kling-config.json'
$env:BACH_ADMIN_CONFIG_FILE = Join-Path $runtimeRoot 'bach-config.json'
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

# Safe is the default baseline; Full explicitly overrides the live-provider
# settings below. Keeping these assignments unconditional also makes the
# offline test contract easy to audit from this launcher.
$env:AI_ADAPTER_MODE = 'fake'
$env:LIBTV_ADAPTER_MODE = 'fake'
$env:LIBTV_EXECUTION_MODE = 'dry-run'
$env:PAID_GENERATION_ENABLED = 'false'
$env:PAID_SUBMISSIONS_PAUSED = 'true'
$env:KLING_CLI_ENABLED = 'false'
$env:KLING_API_ENABLED = 'false'
$env:KLING_API_ENABLE_PAID_INTEGRATION_TEST = 'false'
$env:BACH_ENABLED = 'false'

if ($Profile -eq 'Full') {
    $sourceKlingConfig = Join-Path $projectRoot 'var\runtime\kling-config.json'
    $testKlingConfig = Join-Path $runtimeRoot 'kling-config.json'
    $sourceBachConfig = Join-Path $projectRoot 'var\runtime\bach-config.json'
    $testBachConfig = Join-Path $runtimeRoot 'bach-config.json'
    $useBach = Test-Path -LiteralPath $sourceBachConfig
    if ($useBach) {
        Copy-Item -LiteralPath $sourceBachConfig -Destination $testBachConfig -Force
    }
    elseif (Test-Path -LiteralPath $sourceKlingConfig) {
        Copy-Item -LiteralPath $sourceKlingConfig -Destination $testKlingConfig -Force
    }
    else {
        throw 'Full test profile requires a configured provider file at var/runtime/bach-config.json or var/runtime/kling-config.json.'
    }
    $env:AI_ADAPTER_MODE = 'openai'
    $env:LIBTV_ADAPTER_MODE = 'real'
    $env:LIBTV_EXECUTION_MODE = 'live'
    $env:PAID_GENERATION_ENABLED = 'true'
    $env:PAID_GENERATION_CONFIRMATION = 'I_ACCEPT_LIBTV_POINT_CHARGES'
    $env:PAID_SUBMISSIONS_PAUSED = 'false'
    $env:KLING_PROVIDER_BACKEND = if ($useBach) { 'bach' } else { 'api' }
    $env:KLING_CLI_ENABLED = 'false'
    $env:KLING_API_ENABLED = if ($useBach) { 'false' } else { 'true' }
    $env:BACH_ENABLED = if ($useBach) { 'true' } else { 'false' }
    $env:KLING_ENABLE_PAID_INTEGRATION_TEST = 'false'
    $env:KLING_API_ENABLE_PAID_INTEGRATION_TEST = 'false'
}
else {
    $env:KLING_ENABLE_PAID_INTEGRATION_TEST = 'false'
}

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

    @{
        profile = $Profile
        apiPort = $ApiPort
        frontendPort = $FrontendPort
        apiPid = $api.Id
        frontendPid = $frontend.Id
    } |
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
    if ($Profile -eq 'Full') {
        $adminHeaders = @{ 'X-User-Id' = '00000000-0000-0000-0000-000000000099' }
        $systemStatus = Invoke-RestMethod `
            -Headers $adminHeaders `
            -Uri "http://127.0.0.1:$ApiPort/api/v1/system/status" `
            -TimeoutSec 10
        $klingStatus = Invoke-RestMethod `
            -Headers $adminHeaders `
            -Uri "http://127.0.0.1:$ApiPort/api/v1/admin/kling/status" `
            -TimeoutSec 10
        if (
            $systemStatus.environment -ne 'development' -or
            $systemStatus.paidGenerationAuthorized -ne $true -or
            $klingStatus.provider -ne 'kling_official_api' -or
            $klingStatus.available -ne $true
        ) {
            throw 'Full test stack started, but its live-provider readiness checks failed.'
        }
    }
    $runner = Start-Process -FilePath $python `
        -ArgumentList @($runnerScript) `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDir 'runner.log') `
        -RedirectStandardError (Join-Path $logDir 'runner.error.log')
    Start-Sleep -Milliseconds 500
    $runner.Refresh()
    if ($runner.HasExited) {
        throw 'Test stack API is ready, but its workspace Runner stopped during startup.'
    }
    $runnerDeadline = [DateTimeOffset]::Now.AddSeconds($StartupTimeoutSeconds)
    do {
        if (Test-RunnerReady $ApiPort) { break }
        if ($runner.HasExited) { break }
        Start-Sleep -Milliseconds 500
    } while ([DateTimeOffset]::Now -lt $runnerDeadline)
    if (-not (Test-RunnerReady $ApiPort)) {
        throw "Test stack Runner did not register a recent heartbeat. See $logDir"
    }
    $apiListener = Get-NetTCPConnection -State Listen -LocalPort $ApiPort |
        Select-Object -First 1
    $frontendListener = Get-NetTCPConnection -State Listen -LocalPort $FrontendPort |
        Select-Object -First 1
    @{
        profile = $Profile
        apiPort = $ApiPort
        frontendPort = $FrontendPort
        apiPid = $apiListener.OwningProcess
        frontendPid = $frontendListener.OwningProcess
        runnerPid = $runner.Id
    } |
        ConvertTo-Json |
        Set-Content -Encoding ascii -LiteralPath $processFile
    Write-Host "Test stack ($Profile profile) is ready: http://127.0.0.1:$FrontendPort"
}
catch {
    foreach ($process in @($runner, $frontend, $api)) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Remove-Item -LiteralPath $processFile -Force -ErrorAction SilentlyContinue
    throw
}
finally {
    Pop-Location
}

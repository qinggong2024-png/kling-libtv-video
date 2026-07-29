param(
    [ValidateSet('development', 'staging', 'production')]
    [string]$Environment = 'development'
)

$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$reportRoot = Join-Path $projectRoot 'var\reports'
New-Item -ItemType Directory -Force -Path $reportRoot | Out-Null
$reportPath = Join-Path $reportRoot "online-$Environment.json"
$envFile = Join-Path $projectRoot ".env.$Environment"
$startedAt = [DateTimeOffset]::UtcNow
$checks = [ordered]@{}
$apiProcess = $null
$pushed = $false

function Set-ProcessEnvironment([string]$Path) {
    Get-Content -LiteralPath $Path | ForEach-Object {
        if ($_ -match '^\s*([^#][A-Za-z0-9_]*)=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
        }
    }
}

try {
    if (-not (Test-Path -LiteralPath $envFile)) {
        $checks.configuration = [ordered]@{
            status = 'BLOCKED'
            reason = "Missing $envFile; create it from $envFile.example with local secrets"
        }
    }
    else {
        $content = Get-Content -Raw -LiteralPath $envFile
        if ($content -match 'replace-with-|change-me-before-shared-use') {
            $checks.configuration = [ordered]@{ status = 'BLOCKED'; reason = 'placeholder found' }
        }
        else {
            Set-ProcessEnvironment $envFile
            $checks.configuration = [ordered]@{ status = 'PASS'; secretValuesReported = $false }
        }
    }

    $dockerServerVersion = (& docker info --format '{{.ServerVersion}}' 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($dockerServerVersion)) {
        $checks.docker = [ordered]@{ status = 'BLOCKED'; reason = 'Docker Engine unavailable' }
    }
    else {
        $checks.docker = [ordered]@{ status = 'PASS'; serverVersion = $dockerServerVersion }
    }

    if ($checks.configuration.status -ne 'PASS' -or $checks.docker.status -ne 'PASS') {
        throw 'online prerequisites unavailable; see configuration and docker checks'
    }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'environment.ps1') -Environment $Environment -Action Up
    $checks.compose = [ordered]@{ status = if ($LASTEXITCODE -eq 0) { 'PASS' } else { 'FAIL' } }
    if ($LASTEXITCODE -ne 0) { throw 'compose startup failed' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'environment.ps1') -Environment $Environment -Action Migrate
    $checks.alembic = [ordered]@{ status = if ($LASTEXITCODE -eq 0) { 'PASS' } else { 'FAIL' } }
    if ($LASTEXITCODE -ne 0) { throw 'Alembic migration failed' }

    Push-Location $projectRoot
    $pushed = $true
    $apiLog = Join-Path $projectRoot "var\logs\online-api-$Environment.log"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $apiLog) | Out-Null
    $apiProcess = Start-Process -FilePath 'uv.exe' -ArgumentList @(
        'run', 'uvicorn', 'libtv_agent.app:create_app', '--factory', '--app-dir', 'backend/src',
        '--host', '127.0.0.1', '--port', $env:APP_PORT
    ) -RedirectStandardOutput $apiLog -RedirectStandardError "$apiLog.stderr" -WindowStyle Hidden -PassThru
    $ready = $false
    for ($index = 0; $index -lt 30; $index++) {
        Start-Sleep -Seconds 1
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$($env:APP_PORT)/api/v1/health/ready" -TimeoutSec 2
            if ($response.StatusCode -eq 200) { $ready = $true; break }
        } catch { }
    }
    $checks.apiReadiness = [ordered]@{ status = if ($ready) { 'PASS' } else { 'FAIL' }; httpStatus = if ($ready) { 200 } else { $null } }
    if (-not $ready) { throw 'API readiness did not return 200' }

    $env:PHASE2_ONLINE_TESTS = '1'
    & uv run pytest backend/tests/test_online_infrastructure.py
    $checks.onlineTests = [ordered]@{ status = if ($LASTEXITCODE -eq 0) { 'PASS' } else { 'FAIL' }; includes = @('postgresql-cas', 'points-reservation', 'idempotency-key', 'minio-upload-download-presign-lifecycle') }
    if ($LASTEXITCODE -ne 0) { throw 'online infrastructure tests failed' }
}
catch {
    if (-not $checks.error) { $checks.error = [ordered]@{ message = $_.Exception.Message } }
}
finally {
    if ($apiProcess -and -not $apiProcess.HasExited) {
        Stop-Process -Id $apiProcess.Id -Force
        $apiProcess.WaitForExit()
    }
    if ($pushed) { Pop-Location }
    $statuses = @($checks.Values | Where-Object { $_ -is [System.Collections.IDictionary] -and $_.Contains('status') } | ForEach-Object { $_.status })
    $overall = if ($statuses -contains 'FAIL') { 'FAIL' } elseif ($statuses -contains 'BLOCKED') { 'BLOCKED' } elseif ($statuses -and @($statuses | Where-Object { $_ -ne 'PASS' }).Count -eq 0) { 'PASS' } else { 'INCOMPLETE' }
    $report = [ordered]@{
        schemaVersion = '1.0'
        environment = $Environment
        status = $overall
        startedAt = $startedAt.ToString('o')
        completedAt = [DateTimeOffset]::UtcNow.ToString('o')
        paidOperationsExecuted = $false
        checks = $checks
    }
    $report | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 -LiteralPath $reportPath
    $report | ConvertTo-Json -Depth 8
    if ($overall -ne 'PASS') { exit 1 }
}

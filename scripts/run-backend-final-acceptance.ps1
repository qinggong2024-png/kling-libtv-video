param(
    [string]$PostgresUrl = $env:G1_TEST_POSTGRES_URL
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$reportRoot = Join-Path $projectRoot 'var\reports'
$reportPath = Join-Path $reportRoot 'backend-final-acceptance.json'
$startedAt = [DateTimeOffset]::UtcNow
$checks = [ordered]@{}

New-Item -ItemType Directory -Force -Path $reportRoot | Out-Null

function Invoke-Pytest([string[]]$Arguments, [string]$Name) {
    Push-Location $projectRoot
    try {
        & $python -m pytest @Arguments
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    $checks[$Name] = [ordered]@{
        status = if ($exitCode -eq 0) { 'PASS' } else { 'FAIL' }
        command = "$python -m pytest $($Arguments -join ' ')"
    }
    if ($exitCode -ne 0) {
        throw "$Name failed"
    }
}

try {
    if (-not (Test-Path -LiteralPath $python)) {
        throw "missing repository virtualenv: $python"
    }

    Invoke-Pytest @(
        'backend/tests/test_g1_claim_fence.py',
        'backend/tests/test_g1_launch_race.py',
        'backend/tests/test_g1_cancel_race.py'
    ) 'sqliteClaimFenceRegression'

    Invoke-Pytest @(
        'backend/tests/test_controlled_production_adapter_integration.py',
        'backend/tests/test_creative_provider_requests.py',
        'backend/tests/test_creative_provider_executor.py',
        'backend/tests/test_creative_provider_submission.py',
        'backend/tests/test_creative_provider_input_lease.py'
    ) 'providerSandboxContract'

    if ([string]::IsNullOrWhiteSpace($PostgresUrl)) {
        $checks.postgresql = [ordered]@{
            status = 'BLOCKED'
            reason = 'G1_TEST_POSTGRES_URL is not set; no isolated PostgreSQL target was supplied'
        }
        throw 'PostgreSQL acceptance is blocked by missing G1_TEST_POSTGRES_URL'
    }

    $env:G1_TEST_POSTGRES_URL = $PostgresUrl
    $env:DATABASE_URL = $PostgresUrl
    $checks.postgresqlConfiguration = [ordered]@{
        status = 'PASS'
        target = '127.0.0.1:15439/g1_safety'
        secretValuesReported = $false
    }

    Push-Location $projectRoot
    try {
        & $python -c @'
import os
from sqlalchemy.engine import make_url

url = make_url(os.environ["G1_TEST_POSTGRES_URL"])
if url.host != "127.0.0.1" or url.port != 15439 or url.database != "g1_safety":
    raise SystemExit("G1_TEST_POSTGRES_URL must target the isolated 127.0.0.1:15439/g1_safety database")
'@
        if ($LASTEXITCODE -ne 0) {
            throw 'PostgreSQL target is outside the isolated G1 database contract'
        }
    }
    finally {
        Pop-Location
    }

    Push-Location $projectRoot
    try {
        & $python -m alembic -c backend/alembic.ini upgrade head
        if ($LASTEXITCODE -ne 0) {
            throw 'Alembic migration failed'
        }
    }
    finally {
        Pop-Location
    }
    $checks.postgresqlMigration = [ordered]@{ status = 'PASS'; migration = 'head' }

    Push-Location $projectRoot
    try {
        & $python -c @'
import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from libtv_agent.services.database_schema import inspect_database_schema

url = os.environ["G1_TEST_POSTGRES_URL"]

async def main():
    engine = create_async_engine(url, pool_pre_ping=True)
    async with engine.begin() as connection:
        await connection.execute(text("SELECT 1"))
        schema = await connection.run_sync(inspect_database_schema)
        if not schema.ready:
            raise RuntimeError(
                f"database schema is not ready: current={schema.current_revisions}, "
                f"expected={schema.expected_revisions}, missing={schema.missing_tables}"
            )
    await engine.dispose()

asyncio.run(main())
'@
        if ($LASTEXITCODE -ne 0) {
            throw 'PostgreSQL SELECT 1 readiness check failed'
        }
    }
    finally {
        Pop-Location
    }
    $checks.postgresqlReadiness = [ordered]@{
        status = 'PASS'
        select1 = $true
        databaseSchema = 'ready'
    }

    $env:PHASE2_ONLINE_TESTS = '1'
    Invoke-Pytest @(
        'backend/tests/test_g1_claim_fence.py',
        'backend/tests/test_g1_launch_race.py',
        'backend/tests/test_g1_cancel_race.py',
        'backend/tests/test_image_quota_concurrency.py',
        'backend/tests/test_backend_readiness_repair.py::test_rejected_source_blocks_video_at_every_boundary'
    ) 'postgresqlConcurrencyAndClaimFence'
}
catch {
    if (-not $checks.error) {
        $checks.error = [ordered]@{ message = $_.Exception.Message }
    }
}
finally {
    $statuses = @(
        $checks.Values |
            Where-Object { $_ -is [System.Collections.IDictionary] -and $_.Contains('status') } |
            ForEach-Object { $_.status }
    )
    $overall = if ($statuses -contains 'FAIL') {
        'FAIL'
    }
    elseif ($statuses -contains 'BLOCKED') {
        'BLOCKED'
    }
    elseif ($statuses -and @($statuses | Where-Object { $_ -ne 'PASS' }).Count -eq 0) {
        'PASS'
    }
    else {
        'INCOMPLETE'
    }
    $report = [ordered]@{
        schemaVersion = '1.0'
        status = $overall
        startedAt = $startedAt.ToString('o')
        completedAt = [DateTimeOffset]::UtcNow.ToString('o')
        paidOperationsExecuted = $false
        checks = $checks
    }
    $report | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 -LiteralPath $reportPath
    $report | ConvertTo-Json -Depth 8
    if ($overall -ne 'PASS') {
        exit 1
    }
}

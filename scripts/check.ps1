$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$reportRoot = Join-Path $projectRoot 'var\reports'
New-Item -ItemType Directory -Force -Path $reportRoot | Out-Null
$junitPath = Join-Path $reportRoot 'pytest-junit.xml'
$alembicSqlPath = Join-Path $reportRoot 'alembic-phase2.sql'
$alembicLogPath = Join-Path $reportRoot 'alembic-phase2.stderr.log'
$startedAt = [DateTimeOffset]::UtcNow
$steps = [ordered]@{}

function Invoke-CheckStep([string]$Name, [scriptblock]$Command) {
    $watch = [Diagnostics.Stopwatch]::StartNew()
    & $Command
    $commandSucceeded = $?
    $exitCode = if ($commandSucceeded) { $LASTEXITCODE } elseif ($LASTEXITCODE -ne 0) { $LASTEXITCODE } else { 1 }
    $watch.Stop()
    $script:steps[$Name] = [ordered]@{
        status = if ($exitCode -eq 0) { 'PASS' } else { 'FAIL' }
        exitCode = $exitCode
        durationMs = $watch.ElapsedMilliseconds
    }
}

Push-Location $projectRoot
try {
    Invoke-CheckStep 'backendRuffLint' { uv run ruff check backend scripts }
    Invoke-CheckStep 'backendRuffFormat' { uv run ruff format --check backend scripts }
    Invoke-CheckStep 'backendPytest' { uv run pytest --junitxml $junitPath }
    if (Test-Path -LiteralPath $junitPath) {
        [xml]$junit = Get-Content -Raw -LiteralPath $junitPath
        $suites = if ($junit.testsuites) { @($junit.testsuites.testsuite) } else { @($junit.testsuite) }
        $totals = [ordered]@{ tests = 0; failures = 0; errors = 0; skipped = 0 }
        foreach ($suite in $suites) {
            foreach ($field in @('tests', 'failures', 'errors', 'skipped')) {
                if ($null -ne $suite.$field) { $totals[$field] += [int]$suite.$field }
            }
        }
        $steps.backendPytest.counts = $totals
        $skippedTests = @()
        foreach ($suite in $suites) {
            foreach ($case in @($suite.testcase)) {
                if ($case.skipped) {
                    $skippedTests += [ordered]@{
                        className = [string]$case.classname
                        name = [string]$case.name
                        reason = [string]$case.skipped.message
                    }
                }
            }
        }
        $steps.backendPytest.skippedTests = $skippedTests
        if ($steps.backendPytest.status -eq 'PASS' -and $totals.skipped -gt 0) {
            $steps.backendPytest.status = 'PASS_WITH_SKIPS'
        }
    }
    Invoke-CheckStep 'alembicOfflineSql' {
        $previousDatabaseUrl = $env:DATABASE_URL
        try {
            $env:DATABASE_URL = 'postgresql+asyncpg://offline:offline@localhost/offline'
            uv run alembic -c backend/alembic.ini upgrade head --sql 2> $alembicLogPath |
                Set-Content -Encoding utf8 -LiteralPath $alembicSqlPath
        }
        finally {
            $env:DATABASE_URL = $previousDatabaseUrl
        }
    }
    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        Invoke-CheckStep 'frontendLint' { npm.cmd run lint }
        Invoke-CheckStep 'frontendTest' { npm.cmd test }
        Invoke-CheckStep 'frontendBuild' { npm.cmd run build }
    }
    finally { Pop-Location }
}
finally { Pop-Location }

$statuses = @($steps.Values | ForEach-Object { $_.status })
$status = if ($statuses -contains 'FAIL') {
    'FAIL'
} elseif ($statuses -contains 'PASS_WITH_SKIPS') {
    'PASS_WITH_SKIPS'
} else {
    'PASS'
}
$report = [ordered]@{
    schemaVersion = '1.0'
    status = $status
    startedAt = $startedAt.ToString('o')
    completedAt = [DateTimeOffset]::UtcNow.ToString('o')
    steps = $steps
    evidence = [ordered]@{
        pytestJunit = 'var/reports/pytest-junit.xml'
        alembicOfflineSql = 'var/reports/alembic-phase2.sql'
        alembicStderr = 'var/reports/alembic-phase2.stderr.log'
        generatedBy = 'scripts/check.ps1'
    }
}
$reportPath = Join-Path $reportRoot 'check.json'
$report | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 -LiteralPath $reportPath
$report | ConvertTo-Json -Depth 8
if ($status -eq 'FAIL') { exit 1 }

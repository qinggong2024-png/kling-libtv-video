param(
    [int]$TimeoutSeconds = 5,
    [switch]$RequireFrontend
)

$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$results = [ordered]@{}

function Test-Endpoint([string]$Name, [string]$Uri) {
    $watch = [Diagnostics.Stopwatch]::StartNew()
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec $TimeoutSeconds
        $script:results[$Name] = [ordered]@{
            status = if ($response.StatusCode -eq 200) { 'PASS' } else { 'FAIL' }
            httpStatus = $response.StatusCode
            durationMs = $watch.ElapsedMilliseconds
            uri = $Uri
        }
    }
    catch {
        $statusCode = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { $null }
        $script:results[$Name] = [ordered]@{
            status = 'FAIL'
            httpStatus = $statusCode
            durationMs = $watch.ElapsedMilliseconds
            uri = $Uri
            error = $_.Exception.Message
        }
    }
    finally { $watch.Stop() }
}

function Get-PortStatus([int]$Port) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $listener) {
        return [ordered]@{ status = 'FAIL'; port = $Port; listening = $false }
    }
    $process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    return [ordered]@{
        status = 'PASS'
        port = $Port
        listening = $true
        pid = $listener.OwningProcess
        process = if ($process) { $process.ProcessName } else { $null }
    }
}

Push-Location $projectRoot
try {
    $results.apiPort = Get-PortStatus 8000
    $results.frontendPort = Get-PortStatus 5173
    Test-Endpoint 'apiLiveness' 'http://127.0.0.1:8000/api/v1/health/live'
    Test-Endpoint 'apiReadiness' 'http://127.0.0.1:8000/api/v1/health/ready'
    Test-Endpoint 'apiSystemStatus' 'http://127.0.0.1:8000/api/v1/system/status'
    if ($RequireFrontend -or $results.frontendPort.listening) {
        Test-Endpoint 'frontend' 'http://127.0.0.1:5173/'
        Test-Endpoint 'frontendApiProxy' 'http://127.0.0.1:5173/api/v1/health/ready'
    }

    $migrationOutput = & cmd.exe /d /c "uv run alembic -c backend/alembic.ini current 2>&1"
    $migrationExitCode = $LASTEXITCODE
    $headOutput = & cmd.exe /d /c "uv run alembic -c backend/alembic.ini heads 2>&1"
    $headExitCode = $LASTEXITCODE
    $currentRevision = @($migrationOutput | Where-Object { $_ -match '\(head\)' } | Select-Object -Last 1)
    $expectedRevision = @($headOutput | Where-Object { $_ -match '\(head\)' } | Select-Object -Last 1)
    $results.databaseMigration = [ordered]@{
        status = if ($migrationExitCode -eq 0 -and $headExitCode -eq 0 -and $currentRevision -eq $expectedRevision) { 'PASS' } else { 'FAIL' }
        current = $currentRevision
        expected = $expectedRevision
    }

    $service = Get-Service -Name 'LibTVProductionRunner' -ErrorAction SilentlyContinue
    $runnerScript = Join-Path $projectRoot 'backend\src\libtv_agent\runner\local_runner.py'
    $localRunner = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine.Contains($runnerScript) } |
        Select-Object -First 1
    $runnerReady = ($service -and $service.Status -eq 'Running') -or $null -ne $localRunner
    $results.runner = [ordered]@{
        status = if ($runnerReady) { 'PASS' } else { 'FAIL' }
        serviceStatus = if ($service) { [string]$service.Status } else { 'NotInstalled' }
        localPid = if ($localRunner) { $localRunner.ProcessId } else { $null }
    }

    foreach ($commandName in @('uv', 'node', 'npm.cmd', 'ffmpeg', 'ffprobe')) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        $results["dependency:$commandName"] = [ordered]@{
            status = if ($command) { 'PASS' } else { 'FAIL' }
            path = if ($command) { $command.Source } else { $null }
        }
    }

    $drive = Get-PSDrive -Name ([IO.Path]::GetPathRoot($projectRoot).TrimEnd('\').TrimEnd(':'))
    $freeBytes = [int64]$drive.Free
    $results.diskSpace = [ordered]@{
        status = if ($freeBytes -ge 5GB) { 'PASS' } else { 'FAIL' }
        freeBytes = $freeBytes
        freeGB = [Math]::Round($freeBytes / 1GB, 2)
    }
}
finally { Pop-Location }

$resultStatuses = @($results.Values | ForEach-Object { $_.status })
$overallStatus = if ($resultStatuses -contains 'FAIL') { 'FAIL' } else { 'PASS' }
$report = [ordered]@{
    status = $overallStatus
    checkedAt = [DateTimeOffset]::Now.ToString('o')
    results = $results
}
$report | ConvertTo-Json -Depth 6
if ($overallStatus -eq 'FAIL') { exit 1 }

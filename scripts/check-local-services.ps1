param(
    [int]$TimeoutSeconds = 5,
    [switch]$RequireFrontend
)

$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$results = [ordered]@{}
. (Join-Path $PSScriptRoot 'local-instance-identity.ps1')
. (Join-Path $PSScriptRoot 'stack-logging.ps1')

function Get-ServicePortIdentity([int]$Port) {
    # The API listener of `uv run uvicorn` has no workspace path in its own
    # command line, so process-only identification reported the workspace's own
    # healthy API as a foreign process. Accept launcher ancestry and the API's
    # own sourceRevision as additional evidence.
    if ($Port -eq 8000) {
        return Get-WorkspacePortIdentity `
            -Port $Port `
            -ProjectRoot $projectRoot `
            -AllowLauncherAncestry `
            -AllowBehaviouralIdentity
    }
    return Get-WorkspacePortIdentity -Port $Port -ProjectRoot $projectRoot
}

function Test-Endpoint([string]$Name, [string]$Uri, [int]$Port) {
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $identity = Get-ServicePortIdentity -Port $Port
    if (-not $identity.Listening -or -not $identity.OwnedByWorkspace) {
        $script:results[$Name] = [ordered]@{
            status = 'FAIL'
            httpStatus = $null
            durationMs = $watch.ElapsedMilliseconds
            uri = $Uri
            error = if ($identity.Listening) {
                "Port $Port belongs to PID $($identity.ProcessId) outside this workspace."
            }
            else {
                "Port $Port is not listening."
            }
        }
        $watch.Stop()
        return
    }
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
    $identity = Get-ServicePortIdentity -Port $Port
    if (-not $identity.Listening) {
        return [ordered]@{ status = 'FAIL'; port = $Port; listening = $false }
    }
    return [ordered]@{
        status = if ($identity.OwnedByWorkspace) { 'PASS' } else { 'FAIL' }
        port = $Port
        listening = $true
        workspaceOwned = $identity.OwnedByWorkspace
        ownershipEvidence = $identity.OwnershipEvidence
        pid = $identity.ProcessId
        process = $identity.ProcessName
        executablePath = $identity.ExecutablePath
    }
}

Push-Location $projectRoot
try {
    $results.apiPort = Get-PortStatus 8000
    $results.frontendPort = Get-PortStatus 5173
    # var\ is a junction to the data volume; the database, artifacts and runner
    # state all live behind it. Check it explicitly so an offline data volume is
    # reported as such instead of as a generic API failure.
    $dataDir = Join-Path $projectRoot 'var'
    $dataWritable = (Test-Path -LiteralPath $dataDir) -and
        (Test-StackLogDirectoryWritable -Directory (Join-Path $dataDir 'logs'))
    $results.dataVolume = [ordered]@{
        status = if ($dataWritable) { 'PASS' } else { 'FAIL' }
        path = $dataDir
        writable = $dataWritable
    }
    Test-Endpoint 'apiLiveness' 'http://127.0.0.1:8000/api/v1/health/live' 8000
    Test-Endpoint 'apiReadiness' 'http://127.0.0.1:8000/api/v1/health/ready' 8000
    Test-Endpoint 'apiSystemStatus' 'http://127.0.0.1:8000/api/v1/system/status' 8000
    $expectedSourceRevision = Get-WorkspaceSourceRevision -ProjectRoot $projectRoot
    $currentSourceRevision = $null
    $sourceRevisionError = $null
    if ($results.apiPort.workspaceOwned) {
        try {
            $systemStatus = Invoke-RestMethod `
                -Uri 'http://127.0.0.1:8000/api/v1/system/status' `
                -TimeoutSec $TimeoutSeconds
            $currentSourceRevision = [string]$systemStatus.sourceRevision
        }
        catch { $sourceRevisionError = $_.Exception.Message }
    }
    $results.apiSourceRevision = [ordered]@{
        status = if ($currentSourceRevision -and $currentSourceRevision -eq $expectedSourceRevision) { 'PASS' } else { 'FAIL' }
        current = $currentSourceRevision
        expected = $expectedSourceRevision
        error = $sourceRevisionError
    }
    if ($RequireFrontend -or $results.frontendPort.listening) {
        Test-Endpoint 'frontend' 'http://127.0.0.1:5173/' 5173
        Test-Endpoint 'frontendApiProxy' 'http://127.0.0.1:5173/api/v1/health/ready' 5173
    }

    $migrationOutput = & cmd.exe /d /c "uv run alembic -c backend/alembic.ini current 2>&1"
    $migrationExitCode = $LASTEXITCODE
    $headOutput = & cmd.exe /d /c "uv run alembic -c backend/alembic.ini heads 2>&1"
    $headExitCode = $LASTEXITCODE
    $currentRevision = @(Get-AlembicRevisionIds -Output $migrationOutput)
    $expectedRevision = @(Get-AlembicRevisionIds -Output $headOutput)
    $currentRevisionKey = ($currentRevision -join ',')
    $expectedRevisionKey = ($expectedRevision -join ',')
    $results.databaseMigration = [ordered]@{
        status = if ($migrationExitCode -eq 0 -and $headExitCode -eq 0 -and $currentRevisionKey -eq $expectedRevisionKey) { 'PASS' } else { 'FAIL' }
        current = $currentRevision
        expected = $expectedRevision
    }

    $service = Get-Service -Name 'LibTVProductionRunner' -ErrorAction SilentlyContinue
    $runnerScript = Join-Path $projectRoot 'backend\src\libtv_agent\runner\local_runner.py'
    $runnerMatches = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -and $_.CommandLine.Contains($runnerScript) }
    )
    # .venv\Scripts\python.exe is a launcher stub, not the interpreter: it re-executes
    # the real uv-managed python as a CHILD process with the same arguments (and no
    # pyvenv.cfg, because uv venvs do not write one). One logical Runner therefore
    # shows up as a parent/child pair, which made localCount read 2 on every healthy
    # start and failed this check -- and with it the stack watchdog's post-startup
    # gate -- permanently. Collapse a match whose parent also matches; only matches
    # from unrelated parents are genuine duplicate instances.
    $runnerMatchIds = @($runnerMatches | ForEach-Object { $_.ProcessId })
    $localRunners = @(
        $runnerMatches | Where-Object { $runnerMatchIds -notcontains $_.ParentProcessId }
    )
    $runnerReady = ($service -and $service.Status -eq 'Running') -or $localRunners.Count -gt 0
    # Two local runners share var\runner\service-instance-id, so they publish the
    # same service instance id and overwrite each other's heartbeat. Report that
    # as a failure instead of silently passing on "at least one exists".
    $duplicateRunners = $localRunners.Count -gt 1
    $results.runner = [ordered]@{
        status = if ($runnerReady -and -not $duplicateRunners) { 'PASS' } else { 'FAIL' }
        serviceStatus = if ($service) { [string]$service.Status } else { 'NotInstalled' }
        localCount = $localRunners.Count
        localPids = @($localRunners | ForEach-Object { $_.ProcessId })
        duplicateInstances = $duplicateRunners
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

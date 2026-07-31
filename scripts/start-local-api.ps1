$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $projectRoot 'var\logs'
$runnerScript = Join-Path $projectRoot 'backend\src\libtv_agent\runner\local_runner.py'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
. (Join-Path $PSScriptRoot 'local-instance-identity.ps1')
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Location $projectRoot

function Get-ProcessAncestorIds([int]$ProcessId) {
    $ancestors = @()
    $currentId = $ProcessId
    for ($depth = 0; $depth -lt 12; $depth++) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $currentId" -ErrorAction SilentlyContinue
        if (-not $process -or -not $process.ParentProcessId) { break }
        $currentId = [int]$process.ParentProcessId
        $ancestors += $currentId
    }
    return $ancestors
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv was not found on PATH. Install uv before starting the API.'
}
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found: $python. Run 'uv sync --extra dev' first."
}

$apiPort = 8000
$sourceRevision = Get-WorkspaceSourceRevision -ProjectRoot $projectRoot
$existingIdentity = Assert-WorkspacePortOwnership `
    -Port $apiPort `
    -ProjectRoot $projectRoot `
    -ServiceName 'API'
if ($existingIdentity.Listening) {
    try {
        $status = Invoke-RestMethod `
            -Uri "http://127.0.0.1:$apiPort/api/v1/system/status" `
            -TimeoutSec 3
        if ($status.sourceRevision -eq $sourceRevision) {
            Write-Host "API from this workspace is already ready on http://127.0.0.1:$apiPort (PID $($existingIdentity.ProcessId))."
            exit 0
        }
    }
    catch { }
    $apiWrapperIds = @(
        Get-ProcessAncestorIds -ProcessId $existingIdentity.ProcessId |
            Where-Object {
                $ancestor = Get-CimInstance Win32_Process -Filter "ProcessId = $_" -ErrorAction SilentlyContinue
                $ancestor -and
                $ancestor.CommandLine -and
                $ancestor.CommandLine.Contains($PSCommandPath) -and
                (Test-WorkspaceProcessIdentity `
                    -CommandLine $ancestor.CommandLine `
                    -ExecutablePath $ancestor.ExecutablePath `
                    -ProjectRoot $projectRoot)
            }
    )
    $coupledRunnerIds = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.CommandLine -and
                $_.CommandLine.Contains($runnerScript) -and
                (Test-WorkspaceProcessIdentity `
                    -CommandLine $_.CommandLine `
                    -ExecutablePath $_.ExecutablePath `
                    -ProjectRoot $projectRoot)
            } |
            Where-Object {
                $runnerAncestors = @(Get-ProcessAncestorIds -ProcessId $_.ProcessId)
                @($runnerAncestors | Where-Object { $apiWrapperIds -contains $_ }).Count -gt 0
            } |
            Select-Object -ExpandProperty ProcessId
    )
    Write-Host "API source revision is stale; stopping this workspace's PID $($existingIdentity.ProcessId)."
    Stop-Process -Id $existingIdentity.ProcessId -ErrorAction Stop
    Wait-Process -Id $existingIdentity.ProcessId -Timeout 10 -ErrorAction SilentlyContinue
    $deadline = [DateTimeOffset]::Now.AddSeconds(10)
    do {
        Start-Sleep -Milliseconds 200
        $remaining = Get-WorkspacePortIdentity -Port $apiPort -ProjectRoot $projectRoot
    } while ($remaining.Listening -and [DateTimeOffset]::Now -lt $deadline)
    if ($remaining.Listening) {
        throw "This workspace's stale API PID $($existingIdentity.ProcessId) did not release port $apiPort."
    }
    foreach ($runnerId in $coupledRunnerIds) {
        if (Get-Process -Id $runnerId -ErrorAction SilentlyContinue) {
            Write-Host "Stopping stale Runner PID $runnerId coupled to the old API wrapper."
            Stop-Process -Id $runnerId -ErrorAction Stop
            Wait-Process -Id $runnerId -Timeout 10 -ErrorAction SilentlyContinue
        }
    }
}

$env:DEPLOYMENT_SOURCE_REVISION = $sourceRevision

$preflightCode = "import sys; sys.path.insert(0, 'backend/src'); from libtv_agent.app import create_app; create_app()"
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $python -c $preflightCode 2>&1 |
    Tee-Object -FilePath (Join-Path $logDir 'api.preflight.log')
$preflightExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousErrorActionPreference
if ($preflightExitCode -ne 0) {
    throw 'API import or configuration preflight failed. See var/logs/api.preflight.log.'
}

# Keep the local database schema in lockstep with the checked-out backend code.
# Without this gate, newly added models can make otherwise healthy API requests
# fail with opaque HTTP 500 responses until somebody remembers to migrate by hand.
& cmd.exe /d /c "uv run alembic -c backend/alembic.ini upgrade head 2>&1" |
    Tee-Object -FilePath (Join-Path $logDir 'migration.autostart.log')
$migrationExitCode = $LASTEXITCODE
if ($migrationExitCode -ne 0) {
    throw 'Database migration failed; API startup was aborted. See var/logs/migration.autostart.log.'
}

$runnerProcess = $null
$ownsRunner = $false
$service = Get-Service -Name 'LibTVProductionRunner' -ErrorAction SilentlyContinue
$existingLocalRunner = Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains($runnerScript) } |
    Select-Object -First 1

if (($null -eq $service -or $service.Status -ne 'Running') -and $null -eq $existingLocalRunner) {
    $runnerProcess = Start-Process `
        -FilePath $python `
        -ArgumentList @($runnerScript) `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir 'runner.autostart.log') `
        -RedirectStandardError (Join-Path $logDir 'runner.autostart.error.log') `
        -PassThru
    $ownsRunner = $true
    Start-Sleep -Seconds 1
    $runnerProcess.Refresh()
    if ($runnerProcess.HasExited) {
        throw "Local runner stopped during startup with exit code $($runnerProcess.ExitCode). See var/logs/runner.autostart.error.log."
    }
}

$apiExitCode = 0
try {
    & cmd.exe /d /c "uv run uvicorn libtv_agent.app:create_app --factory --app-dir backend/src 2>&1" |
        Tee-Object -FilePath (Join-Path $logDir 'api.autostart.log')
    $apiExitCode = $LASTEXITCODE
}
finally {
    if ($ownsRunner -and $runnerProcess -and -not $runnerProcess.HasExited) {
        Stop-Process -Id $runnerProcess.Id
    }
}
if ($apiExitCode -ne 0) {
    throw "API stopped with exit code $apiExitCode. See var/logs/api.autostart.log."
}

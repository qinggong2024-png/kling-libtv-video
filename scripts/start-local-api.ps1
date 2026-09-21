$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runnerScript = Join-Path $projectRoot 'backend\src\libtv_agent\runner\local_runner.py'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
. (Join-Path $PSScriptRoot 'local-instance-identity.ps1')
. (Join-Path $PSScriptRoot 'stack-logging.ps1')

# Resolve a writable log directory first. var\logs is a junction to the data
# volume, so if that volume is offline every write below would fail silently and
# this launcher would die without a trace.
$logTarget = Get-StackLogPath -ProjectRoot $projectRoot -Name 'api.autostart.log'
if ($logTarget.Degraded) {
    Write-Warning "API startup logging is degraded: $($logTarget.Reason)"
}
$logDir = Split-Path -Parent $logTarget.Path
$apiLogPath = $logTarget.Path
$preflightLogPath = Join-Path $logDir 'api.preflight.log'
$migrationLogPath = Join-Path $logDir 'migration.autostart.log'

function Stop-ApiStartup([string]$Message) {
    # Every abort is recorded before it happens. start-local-stack.ps1 launches
    # this script in a hidden window with no output redirection, so an unlogged
    # throw is indistinguishable from "nothing happened".
    Write-StackLog -Path $apiLogPath -Text @(
        ("[{0}] FAILED: {1}" -f [DateTimeOffset]::Now.ToString('o'), $Message)
    )
    throw $Message
}

Write-StackLogHeader -Path $apiLogPath -Component 'api-launcher' -Detail "projectRoot=$projectRoot"
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
    Stop-ApiStartup 'uv was not found on PATH. Install uv before starting the API.'
}
if (-not (Test-Path -LiteralPath $python)) {
    Stop-ApiStartup "Python environment not found: $python. Run 'uv sync --extra dev' first."
}

$apiPort = 8000
$sourceRevision = Get-WorkspaceSourceRevision -ProjectRoot $projectRoot
# AllowLauncherAncestry: the listener process of `uv run uvicorn` carries no
# workspace path in its own command line, so ownership has to be established
# from the launcher script in its ancestry. Without this the launcher refused to
# touch even its own API and could never restart a stale one.
$existingIdentity = Assert-WorkspacePortOwnership `
    -Port $apiPort `
    -ProjectRoot $projectRoot `
    -ServiceName 'API' `
    -AllowLauncherAncestry
if ($existingIdentity.OwnedByWorkspace) {
    Write-StackLog -Path $apiLogPath -Text @(
        ("[{0}] port {1} owned by PID {2} (evidence={3})" -f [DateTimeOffset]::Now.ToString('o'), $apiPort, $existingIdentity.ProcessId, $existingIdentity.OwnershipEvidence)
    )
}
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
Write-StackLogHeader -Path $preflightLogPath -Component 'api-preflight' -Detail "python=$python"
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $python -c $preflightCode 2>&1 |
    Write-StackLogRecord -Path $preflightLogPath
$preflightExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousErrorActionPreference
if ($preflightExitCode -ne 0) {
    Stop-ApiStartup "API import or configuration preflight failed with exit code $preflightExitCode. See $preflightLogPath."
}

# Keep the local database schema in lockstep with the checked-out backend code.
# Without this gate, newly added models can make otherwise healthy API requests
# fail with opaque HTTP 500 responses until somebody remembers to migrate by hand.
Write-StackLogHeader -Path $migrationLogPath -Component 'alembic-upgrade' -Detail 'backend/alembic.ini upgrade head'
& cmd.exe /d /c "uv run alembic -c backend/alembic.ini upgrade head 2>&1" |
    Write-StackLogRecord -Path $migrationLogPath
$migrationExitCode = $LASTEXITCODE
if ($migrationExitCode -ne 0) {
    Stop-ApiStartup "Database migration failed with exit code $migrationExitCode; API startup was aborted. See $migrationLogPath."
}

$runnerProcess = $null
$ownsRunner = $false
$service = Get-Service -Name 'LibTVProductionRunner' -ErrorAction SilentlyContinue
$existingLocalRunner = Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains($runnerScript) } |
    Select-Object -First 1

if (($null -eq $service -or $service.Status -ne 'Running') -and $null -eq $existingLocalRunner) {
    # NOTE: deliberately NO -RedirectStandardOutput / -RedirectStandardError here.
    #
    # Passing either of them forces UseShellExecute=$false, which makes .NET build a
    # child-process environment block out of ProcessStartInfo.EnvironmentVariables --
    # a CASE-INSENSITIVE dictionary. If the parent environment happens to contain any
    # two variable names that differ only by case (e.g. both `Path` and `PATH`, or both
    # `http_proxy` and `HTTP_PROXY`, as injected by some IDEs / sandboxes), building
    # that dictionary throws:
    #     ArgumentException: an item with the same key has already been added.
    #     (localized on this machine as a Chinese message naming Path and PATH)
    # Because $ErrorActionPreference is 'Stop', the whole launcher then dies -- and
    # silently, since start-local-stack.ps1 spawns it in a hidden window with no
    # redirection of its own, so the error never reaches var/logs. Symptom: frontend
    # comes up fine, API never listens on 8000, api.autostart.log stays stale.
    #
    # The local Runner does not write to stdout/stderr (its redirected log files
    # stayed at 0 bytes), so the redirection bought nothing and only added this
    # failure mode. The Runner now writes its own UTF-8 file log instead; see
    # libtv_agent/runner/file_logging.py.
    try {
        $runnerProcess = Start-Process `
            -FilePath $python `
            -ArgumentList @($runnerScript) `
            -WorkingDirectory $projectRoot `
            -WindowStyle Hidden `
            -PassThru
    }
    catch {
        Stop-ApiStartup "Failed to spawn the local Runner: $($_.Exception.Message)"
    }
    $ownsRunner = $true
    Write-StackLog -Path $apiLogPath -Text @(
        ("[{0}] local Runner spawned (PID {1})" -f [DateTimeOffset]::Now.ToString('o'), $runnerProcess.Id)
    )
    Start-Sleep -Seconds 1
    $runnerProcess.Refresh()
    if ($runnerProcess.HasExited) {
        Stop-ApiStartup "Local runner stopped during startup with exit code $($runnerProcess.ExitCode)."
    }
}

$apiExitCode = 0
try {
    Write-StackLogHeader -Path $apiLogPath -Component 'uvicorn' -Detail '127.0.0.1:8000'
    & cmd.exe /d /c "uv run uvicorn libtv_agent.app:create_app --factory --app-dir backend/src 2>&1" |
        Write-StackLogRecord -Path $apiLogPath
    $apiExitCode = $LASTEXITCODE
}
finally {
    if ($ownsRunner -and $runnerProcess -and -not $runnerProcess.HasExited) {
        Stop-Process -Id $runnerProcess.Id
    }
}
if ($apiExitCode -ne 0) {
    Stop-ApiStartup "API stopped with exit code $apiExitCode. See $apiLogPath."
}
Write-StackLog -Path $apiLogPath -Text @(
    ("[{0}] API exited normally" -f [DateTimeOffset]::Now.ToString('o'))
)

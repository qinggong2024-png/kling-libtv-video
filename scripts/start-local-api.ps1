$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $projectRoot 'var\logs'
$runnerScript = Join-Path $projectRoot 'backend\src\libtv_agent\runner\local_runner.py'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
. (Join-Path $PSScriptRoot 'local-instance-identity.ps1')
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Location $projectRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv was not found on PATH. Install uv before starting the API.'
}
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found: $python. Run 'uv sync --extra dev' first."
}

$apiPort = 8000
$existingIdentity = Assert-WorkspacePortOwnership `
    -Port $apiPort `
    -ProjectRoot $projectRoot `
    -ServiceName 'API'
if ($existingIdentity.Listening) {
    try {
        $response = Invoke-WebRequest `
            -UseBasicParsing `
            -Uri "http://127.0.0.1:$apiPort/api/v1/health/ready" `
            -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            Write-Host "API from this workspace is already ready on http://127.0.0.1:$apiPort (PID $($existingIdentity.ProcessId))."
            exit 0
        }
    }
    catch { }
    throw "Port $apiPort is owned by this workspace's PID $($existingIdentity.ProcessId), but the API readiness check failed."
}

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

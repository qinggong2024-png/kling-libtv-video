$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'local-instance-identity.ps1')
. (Join-Path $PSScriptRoot 'stack-logging.ps1')

$logTarget = Get-StackLogPath -ProjectRoot $projectRoot -Name 'frontend.autostart.log'
if ($logTarget.Degraded) {
    Write-Warning "Frontend startup logging is degraded: $($logTarget.Reason)"
}
$logDir = Split-Path -Parent $logTarget.Path
$frontendLogPath = $logTarget.Path
$preflightLogPath = Join-Path $logDir 'frontend.preflight.log'

function Stop-FrontendStartup([string]$Message) {
    # Recorded before throwing: this launcher is also started in a hidden window
    # with no output redirection, so an unlogged throw leaves no evidence.
    Write-StackLog -Path $frontendLogPath -Text @(
        ("[{0}] FAILED: {1}" -f [DateTimeOffset]::Now.ToString('o'), $Message)
    )
    throw $Message
}

Write-StackLogHeader -Path $frontendLogPath -Component 'frontend-launcher' -Detail "projectRoot=$projectRoot"
Set-Location $projectRoot

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    Stop-FrontendStartup 'npm.cmd was not found on PATH. Install Node.js before starting the frontend.'
}
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\node_modules'))) {
    Stop-FrontendStartup "Frontend dependencies are missing. Run 'npm.cmd install --prefix frontend' first."
}

$frontendPort = 5173
$existingIdentity = Assert-WorkspacePortOwnership `
    -Port $frontendPort `
    -ProjectRoot $projectRoot `
    -ServiceName 'frontend'
if ($existingIdentity.Listening) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$frontendPort/" -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            Write-Host "Frontend from this workspace is already available on http://127.0.0.1:$frontendPort (PID $($existingIdentity.ProcessId))."
            exit 0
        }
    }
    catch { }
    Stop-FrontendStartup "Port $frontendPort is owned by this workspace's PID $($existingIdentity.ProcessId), but the frontend check failed."
}

Write-StackLogHeader -Path $preflightLogPath -Component 'frontend-build'
& cmd.exe /d /c "npm.cmd run build --prefix frontend 2>&1" |
    Write-StackLogRecord -Path $preflightLogPath
$preflightExitCode = $LASTEXITCODE
if ($preflightExitCode -ne 0) {
    Stop-FrontendStartup "Frontend type-check or build preflight failed with exit code $preflightExitCode. See $preflightLogPath."
}

Write-StackLogHeader -Path $frontendLogPath -Component 'vite-dev'
& cmd.exe /d /c "npm.cmd run dev --prefix frontend 2>&1" |
    Write-StackLogRecord -Path $frontendLogPath
$frontendExitCode = $LASTEXITCODE
if ($frontendExitCode -ne 0) {
    Stop-FrontendStartup "Frontend stopped with exit code $frontendExitCode. See $frontendLogPath."
}

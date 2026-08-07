param(
    [ValidateSet('Local', 'Lan')]
    [string]$Mode = 'Local',
    [ValidateRange(10, 3600)]
    [int]$PollSeconds = 30,
    [ValidateRange(15, 600)]
    [int]$StartupTimeoutSeconds = 90
)

$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$startScript = Join-Path $PSScriptRoot $(if ($Mode -eq 'Lan') { 'start-lan-stack.ps1' } else { 'start-local-stack.ps1' })
$logDir = Join-Path $projectRoot 'var\logs'
$logPath = Join-Path $logDir 'stack-watchdog.log'
. (Join-Path $PSScriptRoot 'local-instance-identity.ps1')
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-WatchdogLog([string]$Message) {
    $timestamp = [DateTimeOffset]::Now.ToString('o')
    Add-Content -LiteralPath $logPath -Value "$timestamp $Message"
}

function Test-Ready([string]$Uri) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 3
        return $response.StatusCode -eq 200
    }
    catch { return $false }
}

function Test-ApiCurrent {
    $identity = Get-WorkspacePortIdentity -Port 8000 -ProjectRoot $projectRoot
    if (-not $identity.Listening -or -not $identity.OwnedByWorkspace) { return $false }
    try {
        $status = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/system/status' -TimeoutSec 3
        return $status.sourceRevision -eq (Get-WorkspaceSourceRevision -ProjectRoot $projectRoot)
    }
    catch { return $false }
}

if (-not (Test-Path -LiteralPath $startScript)) {
    throw "Local stack startup script not found: $startScript"
}

Write-WatchdogLog "Watchdog started (PID $PID, mode=$Mode)."
$lastState = $null

while ($true) {
    $apiReady = (Test-Ready 'http://127.0.0.1:8000/api/v1/health/ready') -and (Test-ApiCurrent)
    $frontendReady = Test-Ready 'http://127.0.0.1:5173/'
    if ($apiReady -and $Mode -eq 'Lan') {
        try {
            $status = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/system/status' -TimeoutSec 3
            $apiReady = $status.sharedAuthentication -eq $true
        }
        catch { $apiReady = $false }
    }

    if ($apiReady -and $frontendReady) {
        if ($lastState -ne 'ready') {
            Write-WatchdogLog 'Local stack is ready.'
            $lastState = 'ready'
        }
        Start-Sleep -Seconds $PollSeconds
        continue
    }

    if ($lastState -ne 'unavailable') {
        Write-WatchdogLog "Local stack is unavailable (api=$apiReady, frontend=$frontendReady); starting it."
        $lastState = 'unavailable'
    }

    $output = & powershell.exe `
        -NoProfile `
        -ExecutionPolicy Bypass `
        -File $startScript `
        -StartupTimeoutSeconds $StartupTimeoutSeconds 2>&1 | Out-String
    $startupExitCode = $LASTEXITCODE

    if ($output.Trim()) {
        Add-Content -LiteralPath $logPath -Value $output.TrimEnd()
    }
    if ($startupExitCode -ne 0) {
        Write-WatchdogLog "Startup attempt failed with exit code $startupExitCode; retrying after $PollSeconds seconds."
    }

    Start-Sleep -Seconds $PollSeconds
}

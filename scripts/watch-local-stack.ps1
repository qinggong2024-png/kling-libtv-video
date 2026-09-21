param(
    [ValidateSet('Local', 'Lan')]
    [string]$Mode = 'Local',
    [ValidateRange(10, 3600)]
    [int]$PollSeconds = 30,
    [ValidateRange(15, 600)]
    [int]$StartupTimeoutSeconds = 90,
    [ValidateRange(60, 7200)]
    [int]$MaxBackoffSeconds = 600
)

$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$startScript = Join-Path $PSScriptRoot $(if ($Mode -eq 'Lan') { 'start-lan-stack.ps1' } else { 'start-local-stack.ps1' })
. (Join-Path $PSScriptRoot 'local-instance-identity.ps1')
. (Join-Path $PSScriptRoot 'stack-logging.ps1')

# var\logs is a junction to the data volume. If that volume is offline, New-Item
# and Add-Content fail WITHOUT raising an error under $ErrorActionPreference =
# 'Continue' and $? still reports True, so the watchdog used to keep looping in
# total silence with no log file at all. Resolve a writable target up front and
# keep the flag so the loop can say so out loud.
$logTarget = Get-StackLogPath -ProjectRoot $projectRoot -Name 'stack-watchdog.log'
$logPath = $logTarget.Path
$logDegraded = $logTarget.Degraded
$logDegradedReason = $logTarget.Reason

function Write-WatchdogLog([string]$Message) {
    $timestamp = [DateTimeOffset]::Now.ToString('o')
    Write-StackLog -Path $logPath -Text @("$timestamp $Message")
}

function Test-DataVolume {
    # The database, artifacts and runner state all live behind var\ -> the data
    # volume. Its loss is a distinct, actionable state: the stack cannot be
    # started, so retrying is pointless and the operator has to intervene.
    $dataDir = Join-Path $projectRoot 'var'
    return [pscustomobject]@{
        Available = (Test-Path -LiteralPath $dataDir) -and
            (Test-StackLogDirectoryWritable -Directory (Join-Path $dataDir 'logs'))
        Path = $dataDir
    }
}

function Compress-StartupOutput([string]$Text) {
    # The raw child output is three copies of the same stack trace per attempt,
    # which is how this file reached 811 KB. Keep the signal, drop the noise.
    $kept = [System.Collections.Generic.List[string]]::new()
    $seen = @{}
    foreach ($raw in ($Text -split "`r?`n")) {
        $line = $raw.Trim()
        if (-not $line) { continue }
        if ($line -match '^\s*[+~]') { continue }
        if ($line -match '^(CategoryInfo|FullyQualifiedErrorId|Exception)\s*:') { continue }
        if ($line -match '^\s*[\u4e00-\u9fff]') { continue }
        if ($line -match '^\s*0x[0-9a-fA-F]+\s*$') { continue }
        if ($seen.ContainsKey($line)) { continue }
        $seen[$line] = $true
        $kept.Add($line)
        if ($kept.Count -ge 25) {
            $kept.Add('... (further output truncated)')
            break
        }
    }
    return ($kept -join "`n")
}

function Test-Ready([string]$Uri) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 3
        return $response.StatusCode -eq 200
    }
    catch { return $false }
}

function Test-ApiCurrent {
    $identity = Get-WorkspacePortIdentity `
        -Port 8000 `
        -ProjectRoot $projectRoot `
        -AllowLauncherAncestry `
        -AllowBehaviouralIdentity
    if (-not $identity.Listening -or -not $identity.OwnedByWorkspace) { return $false }
    try {
        $status = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/system/status' -TimeoutSec 3
        return $status.sourceRevision -eq (Get-WorkspaceSourceRevision -ProjectRoot $projectRoot)
    }
    catch { return $false }
}

if (-not (Test-Path -LiteralPath $startScript)) {
    $message = "Local stack startup script not found: $startScript"
    Write-WatchdogLog "FATAL: $message"
    throw $message
}

Write-WatchdogLog "Watchdog started (PID $PID, mode=$Mode, poll=${PollSeconds}s)."
if ($logDegraded) {
    Write-WatchdogLog "WARNING: logging is degraded - $logDegradedReason"
}
$lastState = $null
$consecutiveFailures = 0

while ($true) {
    $dataVolume = Test-DataVolume

    if (-not $dataVolume.Available) {
        if ($lastState -ne 'data-volume-offline') {
            Write-WatchdogLog (
                "DATA VOLUME UNAVAILABLE: $($dataVolume.Path) is not writable. " +
                'The database, artifacts and runner state live there, so the stack cannot start ' +
                'until the drive is back. Not retrying a doomed start.'
            )
            $lastState = 'data-volume-offline'
        }
        Start-Sleep -Seconds $PollSeconds
        continue
    }
    if ($lastState -eq 'data-volume-offline') {
        Write-WatchdogLog "DATA VOLUME RECOVERED: $($dataVolume.Path) is writable again."
    }

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
        $consecutiveFailures = 0
        Start-Sleep -Seconds $PollSeconds
        continue
    }

    if ($lastState -ne 'unavailable') {
        $identity = Get-WorkspacePortIdentity `
            -Port 8000 `
            -ProjectRoot $projectRoot `
            -AllowLauncherAncestry `
            -AllowBehaviouralIdentity
        Write-WatchdogLog (
            "Local stack is unavailable (api=$apiReady, frontend=$frontendReady); starting it. " +
            "port8000: listening=$($identity.Listening) owned=$($identity.OwnedByWorkspace) " +
            "evidence=$($identity.OwnershipEvidence) pid=$($identity.ProcessId)"
        )
        $lastState = 'unavailable'
    }

    $output = & powershell.exe `
        -NoProfile `
        -ExecutionPolicy Bypass `
        -File $startScript `
        -StartupTimeoutSeconds $StartupTimeoutSeconds 2>&1 | Out-String
    $startupExitCode = $LASTEXITCODE

    $compressed = Compress-StartupOutput $output
    if ($compressed.Trim()) {
        Write-StackLog -Path $logPath -Text @($compressed.TrimEnd())
    }
    if ($startupExitCode -ne 0) {
        $consecutiveFailures++
        # Exponential backoff: an unrecoverable condition (a foreign process
        # holding port 8000, a locked database) must not be retried every 30
        # seconds forever. Success resets the counter to zero.
        $delay = [int][Math]::Min(
            $MaxBackoffSeconds,
            $PollSeconds * [Math]::Pow(2, [Math]::Min($consecutiveFailures - 1, 6))
        )
        Write-WatchdogLog (
            "Startup attempt failed with exit code $startupExitCode " +
            "(consecutive failures: $consecutiveFailures); retrying in $delay seconds."
        )
        Start-Sleep -Seconds $delay
        continue
    }
    $consecutiveFailures = 0

    Start-Sleep -Seconds $PollSeconds
}

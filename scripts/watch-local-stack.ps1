param(
    [ValidateSet('Local', 'Lan')]
    [string]$Mode = 'Local',
    [ValidateRange(10, 3600)]
    [int]$PollSeconds = 30,
    [ValidateRange(15, 600)]
    [int]$StartupTimeoutSeconds = 90,
    [ValidateRange(60, 7200)]
    [int]$MaxBackoffSeconds = 600,
    [ValidateRange(30, 3600)]
    [int]$HeartbeatSeconds = 300
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

function Write-HeartbeatIfDue {
    # The loop used to log only on state transitions, so a healthy "ready"
    # stretch wrote nothing at all. The last line of the log was therefore a
    # lower bound on how long the watchdog ran, never an upper one - and a
    # quiet log could not be told apart from a healthy one. On 2026-09-25 the
    # process died with 0xC000013A and the log ended on "Local stack is ready."
    # with no way to say whether that was thirty seconds or three hours before.
    #
    # This writes an unconditional line at a fixed cadence, so both edges of a
    # death window are bounded: no "alive" line for more than twice
    # HeartbeatSeconds means the loop stopped turning. The cadence is recorded
    # on the startup line so the reader does not have to guess it, and a stale
    # process running an older script is visible as a startup line without the
    # heartbeat field.
    #
    # It reports the readiness flags the loop already computed instead of
    # probing again. A second set of health criteria in the same process is how
    # a watchdog starts disagreeing with the launcher it supervises.
    $now = [DateTimeOffset]::Now
    if (($now - $script:lastHeartbeat).TotalSeconds -lt $HeartbeatSeconds) { return }
    $uptime = [int]($now - $script:startedAt).TotalSeconds
    # An offline data volume short-circuits the loop before the readiness probes
    # run, so these are still null. Say so rather than printing an empty field
    # that reads like a formatting bug.
    $api = if ($null -eq $script:apiReady) { 'unmeasured' } else { $script:apiReady }
    $frontend = if ($null -eq $script:frontendReady) { 'unmeasured' } else { $script:frontendReady }
    Write-WatchdogLog (
        "alive: iteration=$($script:iteration) uptime=${uptime}s state=$($script:lastState) " +
        "api=$api frontend=$frontend logDegraded=$logDegraded"
    )
    $script:lastHeartbeat = $now
}

function Wait-WithHeartbeat([int]$Seconds) {
    # Heartbeats are emitted at the top of the loop, but two branches sleep far
    # longer than the cadence: the backoff after a failed start (up to
    # MaxBackoffSeconds, 600s by default) and the data-volume-offline branch
    # (up to PollSeconds, which the parameter allows to reach 3600s). A sleep
    # that long reproduces exactly the ambiguity this heartbeat exists to
    # remove - silence was indistinguishable from a stalled loop.
    #
    # Sleep in chunks no larger than the cadence and re-emit between them, so
    # expected silence stays bounded by the cadence regardless of which branch
    # is running. Short sleeps are untouched: one chunk, same duration.
    $remaining = $Seconds
    while ($remaining -gt 0) {
        $chunk = [Math]::Min($remaining, $HeartbeatSeconds)
        Start-Sleep -Seconds $chunk
        $remaining -= $chunk
        Write-HeartbeatIfDue
    }
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

Write-WatchdogLog (
    "Watchdog started (PID $PID, mode=$Mode, poll=${PollSeconds}s, " +
    "heartbeat=${HeartbeatSeconds}s)."
)
if ($logDegraded) {
    Write-WatchdogLog "WARNING: logging is degraded - $logDegradedReason"
}
$lastState = 'starting'
$consecutiveFailures = 0
$iteration = 0
$startedAt = [DateTimeOffset]::Now
$lastHeartbeat = $startedAt
$apiReady = $null
$frontendReady = $null

while ($true) {
    $iteration++
    Write-HeartbeatIfDue

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
        Wait-WithHeartbeat $PollSeconds
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
        Wait-WithHeartbeat $PollSeconds
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
        Wait-WithHeartbeat $delay
        continue
    }
    $consecutiveFailures = 0

    Wait-WithHeartbeat $PollSeconds
}

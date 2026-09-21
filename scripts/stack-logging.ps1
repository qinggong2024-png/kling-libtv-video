# scripts/stack-logging.ps1
#
# Shared, encoding-stable logging for the local stack launchers.
#
# Why this file exists
# --------------------
# Before this helper, the same var\logs directory contained three different
# text encodings produced by three different cmdlets:
#
#   * Tee-Object -FilePath   -> UTF-16LE with BOM  (FF FE ...)
#   * Add-Content (no -Encoding) -> the ANSI code page (GBK here)
#   * Set-Content -Encoding utf8 -> UTF-8 with BOM
#
# so diagnosing an outage started with guessing an encoding. Worse, every
# launcher used Tee-Object which OVERWRITES its target, so the evidence of the
# previous failure was destroyed by the next restart attempt - and the watchdog
# restarts every 30 seconds.
#
# Everything written from here on is UTF-8 (ASCII-safe for our own messages),
# append-only, with an explicit run header, a size cap, and a writability probe.
#
# IMPORTANT: keep the contents of this file ASCII-only. Windows PowerShell 5.1
# decodes a .ps1 without a BOM using the ANSI code page, so non-ASCII comments
# are silently mangled.

$script:StackLogMaxBytes = 5MB
$script:StackLogKeepGenerations = 2

function Test-StackLogDirectoryWritable {
    # A junction pointing at an offline data volume makes the PowerShell file
    # cmdlets fail WITHOUT raising a terminating error by default, and $? still
    # reports True. The .NET APIs below throw instead, which is what makes the
    # failure catchable - and they keep this probe independent of the
    # Recycle-Bin/safe-delete policy, which can refuse a throwaway file deletion
    # and must not be mistaken for a read-only directory.
    param([Parameter(Mandatory = $true)][string]$Directory)

    try {
        if (-not [System.IO.Directory]::Exists($Directory)) {
            [System.IO.Directory]::CreateDirectory($Directory) | Out-Null
        }
        $probe = Join-Path $Directory ('.stack-log-probe-{0}.tmp' -f $PID)
        [System.IO.File]::WriteAllText($probe, 'ok')
        try { [System.IO.File]::Delete($probe) } catch { }
        return $true
    }
    catch {
        return $false
    }
}

function Get-StackLogPath {
    # Returns the log file to use, plus a flag telling the caller whether the
    # preferred location (var\logs, a junction to the data volume) is usable.
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][string]$Name,
        [switch]$ForceFallback
    )

    $primaryDir = Join-Path $ProjectRoot 'var\logs'
    if (-not $ForceFallback -and (Test-StackLogDirectoryWritable -Directory $primaryDir)) {
        return [pscustomobject]@{
            Path = (Join-Path $primaryDir $Name)
            Degraded = $false
            Reason = $null
        }
    }

    # var\ is a junction to the data volume. When that volume is offline the
    # only place that still accepts writes is the project volume itself.
    $fallbackDir = Join-Path $ProjectRoot '.libtv\logs'
    $fallbackOk = Test-StackLogDirectoryWritable -Directory $fallbackDir
    return [pscustomobject]@{
        Path = (Join-Path $fallbackDir $Name)
        Degraded = $true
        Reason = if ($fallbackOk) {
            "primary log directory is not writable: $primaryDir"
        }
        else {
            "neither $primaryDir nor $fallbackDir is writable"
        }
    }
}

function Invoke-StackLogRotation {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [int64]$MaxBytes = $script:StackLogMaxBytes,
        [int]$KeepGenerations = $script:StackLogKeepGenerations
    )

    try {
        if (-not (Test-Path -LiteralPath $Path)) { return }
        $length = (Get-Item -LiteralPath $Path -ErrorAction Stop).Length
        if ($length -lt $MaxBytes) { return }
        for ($generation = $KeepGenerations; $generation -ge 1; $generation--) {
            $source = if ($generation -eq 1) { $Path } else { "$Path.$($generation - 1)" }
            $target = "$Path.$generation"
            if (Test-Path -LiteralPath $source) {
                Move-Item -LiteralPath $source -Destination $target -Force -ErrorAction Stop
            }
        }
    }
    catch {
        # Rotation is best-effort. Never let log housekeeping break a launcher.
    }
}

function Write-StackLog {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][AllowEmptyString()][AllowNull()][string[]]$Text
    )

    try {
        Invoke-StackLogRotation -Path $Path
        foreach ($line in $Text) {
            Add-Content -LiteralPath $Path -Value ([string]$line) -Encoding utf8 -ErrorAction Stop
        }
    }
    catch {
        # Logging must never be the reason a launcher fails.
    }
}

function Write-StackLogHeader {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Component,
        [string]$Detail = ''
    )

    $stamp = [DateTimeOffset]::Now.ToString('o')
    Write-StackLog -Path $Path -Text @(
        ''
        ('=' * 72)
        "$stamp  [$Component] run start  pid=$PID  $Detail".TrimEnd()
        ('=' * 72)
    )
}

function Write-StackLogRecord {
    # Pipeline sink that replaces Tee-Object: appends every line to the log in
    # UTF-8 and still forwards it to the caller's pipeline.
    #
    # -Line MUST carry ValueFromPipeline. Declaring [Parameter()] attributes
    # turns this into an advanced function, and an advanced function whose
    # parameters cannot accept pipeline input raises ParameterBindingException
    # ("no parameter can accept the pipeline input") instead of silently
    # ignoring the piped object. Under the launchers'
    # $ErrorActionPreference = 'Stop' that exception is terminating, so every
    # `& <native command> | Write-StackLogRecord -Path <log>` caller died one
    # line after its run header: the launchers are spawned in a hidden window
    # with no output redirection, so the API never listened on 8000 and neither
    # api.autostart.log nor frontend.autostart.log recorded a single line of
    # the real output. Deliberately NOT Mandatory: a missing pipeline input
    # must not turn into an interactive prompt.
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(ValueFromPipeline = $true)][AllowEmptyString()][AllowNull()][string]$Line = ''
    )

    begin {
        Invoke-StackLogRotation -Path $Path
    }
    process {
        $text = [string]$Line
        try {
            Add-Content -LiteralPath $Path -Value $text -Encoding utf8 -ErrorAction Stop
        }
        catch {
        }
        Write-Output $text
    }
}

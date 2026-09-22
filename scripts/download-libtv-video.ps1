[CmdletBinding(DefaultParameterSetName = 'Download')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Download')]
    [Parameter(Mandatory = $true, ParameterSetName = 'Worker')]
    [string]$Url,

    [Parameter(Mandatory = $true, ParameterSetName = 'Download')]
    [string]$OutputFile,

    [Parameter(ParameterSetName = 'Download')]
    [ValidateRange(1, 16)]
    [int]$SegmentCount = 8,

    [Parameter(ParameterSetName = 'Download')]
    [Parameter(ParameterSetName = 'Worker')]
    [ValidateSet('Auto', 'Direct', 'SystemProxy')]
    [string]$NetworkMode = 'Auto',

    [Parameter(ParameterSetName = 'Download')]
    [long]$ExpectedSize = 0,

    [Parameter(ParameterSetName = 'Download')]
    [ValidatePattern('^[0-9a-fA-F]{64}$')]
    [string]$ExpectedSha256,

    [Parameter(ParameterSetName = 'Download')]
    [Parameter(ParameterSetName = 'Worker')]
    [ValidateRange(30, 600)]
    [int]$StallTimeoutSeconds = 120,

    [Parameter(ParameterSetName = 'Download')]
    [Parameter(ParameterSetName = 'Worker')]
    [ValidateRange(1, 60)]
    [int]$RetryDelaySeconds = 3,

    [Parameter(Mandatory = $true, ParameterSetName = 'Worker')]
    [switch]$InternalWorker,

    [Parameter(Mandatory = $true, ParameterSetName = 'Worker')]
    [long]$RangeStart,

    [Parameter(Mandatory = $true, ParameterSetName = 'Worker')]
    [long]$RangeEnd,

    [Parameter(Mandatory = $true, ParameterSetName = 'Worker')]
    [string]$SegmentPath,

    [Parameter(Mandatory = $true, ParameterSetName = 'Worker')]
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'
$curlPath = Join-Path $env:SystemRoot 'System32\curl.exe'

if (-not (Test-Path -LiteralPath $curlPath -PathType Leaf)) {
    throw "Windows curl.exe not found: $curlPath"
}

function Add-DownloadLog {
    param(
        [string]$Path,
        [string]$Message
    )

    $line = '{0} {1}' -f (Get-Date).ToString('o'), $Message
    Add-Content -LiteralPath $Path -Value $line -Encoding UTF8
}

function Get-SystemProxyUri {
    param([string]$TargetUrl)

    try {
        $targetUri = [Uri]$TargetUrl
        $systemProxy = [Net.WebRequest]::GetSystemWebProxy()
        if ($systemProxy.IsBypassed($targetUri)) {
            return $null
        }

        $proxyUri = $systemProxy.GetProxy($targetUri)
        if ($proxyUri -and ($proxyUri.AbsoluteUri -ne $targetUri.AbsoluteUri)) {
            return $proxyUri.AbsoluteUri
        }
    }
    catch {
        return $null
    }
    return $null
}

function Get-CurlNetworkArguments {
    param(
        [string]$TargetUrl,
        [string]$Mode
    )

    if ($Mode -eq 'Direct') {
        return @('--noproxy', '*')
    }
    if ($Mode -eq 'SystemProxy') {
        $proxyUri = Get-SystemProxyUri -TargetUrl $TargetUrl
        if (-not $proxyUri) {
            throw 'No system proxy is configured for this video URL.'
        }
        return @('--proxy', $proxyUri)
    }
    throw 'Auto network mode must be resolved before starting a download worker.'
}

function Measure-NetworkRoute {
    param(
        [string]$TargetUrl,
        [string]$Route,
        [string]$ProbeDirectory,
        [long]$RangeStart,
        [string]$RouteLogPath
    )

    $probeBytes = 64KB
    $rangeEnd = $RangeStart + $probeBytes - 1
    $probePath = Join-Path $ProbeDirectory ("route-{0}.probe" -f $Route.ToLowerInvariant())
    $errorPath = Join-Path $ProbeDirectory ("route-{0}.log" -f $Route.ToLowerInvariant())
    $arguments = if ($Route -eq 'Direct') {
        @('--noproxy', '*')
    }
    else {
        $proxyUri = Get-SystemProxyUri -TargetUrl $TargetUrl
        if (-not $proxyUri) {
            return [pscustomobject]@{
                Route = $Route
                Available = $false
                Bytes = 0L
                Seconds = 0.0
                BytesPerSecond = 0.0
                ExitCode = -1
            }
        }
        @('--proxy', $proxyUri)
    }

    Remove-Item -LiteralPath $probePath, $errorPath -Force -ErrorAction SilentlyContinue
    $stopwatch = [Diagnostics.Stopwatch]::StartNew()
    & $curlPath `
        @arguments `
        --http1.1 `
        -L `
        --fail `
        --silent `
        --show-error `
        --connect-timeout 5 `
        --max-time 12 `
        --speed-time 8 `
        --speed-limit 1 `
        --max-filesize 1048576 `
        --range "$RangeStart-$rangeEnd" `
        --output $probePath `
        $TargetUrl 2>> $errorPath
    $exitCode = $LASTEXITCODE
    $stopwatch.Stop()

    $bytes = if (Test-Path -LiteralPath $probePath -PathType Leaf) {
        (Get-Item -LiteralPath $probePath).Length
    }
    else {
        0L
    }
    $seconds = [Math]::Max(0.001, $stopwatch.Elapsed.TotalSeconds)
    $bytesPerSecond = $bytes / $seconds
    $available = ($bytes -ge 8KB)
    Add-DownloadLog -Path $RouteLogPath -Message (
        "route={0} available={1} bytes={2} seconds={3:N3} bytesPerSecond={4:N1} exit={5}" -f
        $Route, $available, $bytes, $seconds, $bytesPerSecond, $exitCode
    )
    Remove-Item -LiteralPath $probePath -Force -ErrorAction SilentlyContinue

    return [pscustomobject]@{
        Route = $Route
        Available = $available
        Bytes = $bytes
        Seconds = $seconds
        BytesPerSecond = $bytesPerSecond
        ExitCode = $exitCode
    }
}

function Select-FastestNetworkMode {
    param(
        [string]$TargetUrl,
        [string]$RequestedMode,
        [string]$ProbeDirectory
    )

    if ($RequestedMode -ne 'Auto') {
        return $RequestedMode
    }

    $routeLogPath = Join-Path $ProbeDirectory 'network-route.log'
    $measurements = @(
        Measure-NetworkRoute `
            -TargetUrl $TargetUrl `
            -Route 'Direct' `
            -ProbeDirectory $ProbeDirectory `
            -RangeStart 0 `
            -RouteLogPath $routeLogPath
    )

    if (Get-SystemProxyUri -TargetUrl $TargetUrl) {
        $measurements += Measure-NetworkRoute `
            -TargetUrl $TargetUrl `
            -Route 'SystemProxy' `
            -ProbeDirectory $ProbeDirectory `
            -RangeStart 64KB `
            -RouteLogPath $routeLogPath
    }

    $winner = $measurements |
        Where-Object { $_.Available } |
        Sort-Object BytesPerSecond -Descending |
        Select-Object -First 1
    if (-not $winner) {
        throw "Direct and system proxy route probes both failed. See: $routeLogPath"
    }

    Add-DownloadLog -Path $routeLogPath -Message (
        "selected route={0} bytesPerSecond={1:N1}" -f
        $winner.Route, $winner.BytesPerSecond
    )
    return $winner.Route
}

if ($PSCmdlet.ParameterSetName -eq 'Worker') {
    $networkArguments = @(
        Get-CurlNetworkArguments -TargetUrl $Url -Mode $NetworkMode
    )
    $expectedLength = $RangeEnd - $RangeStart + 1
    $chunkPath = $SegmentPath + '.chunk'
    $lockPath = $SegmentPath + '.lock'
    $lockStream = $null
    $noProgressAttempts = 0

    if ($expectedLength -le 0) {
        throw "Invalid byte range: $RangeStart-$RangeEnd"
    }

    while (-not $lockStream) {
        try {
            $lockStream = [IO.File]::Open(
                $lockPath,
                [IO.FileMode]::OpenOrCreate,
                [IO.FileAccess]::ReadWrite,
                [IO.FileShare]::None
            )
        }
        catch [IO.IOException] {
            Start-Sleep -Seconds 5
        }
    }

    try {
        while ($true) {
            $existingLength = if (Test-Path -LiteralPath $SegmentPath -PathType Leaf) {
                (Get-Item -LiteralPath $SegmentPath).Length
            }
            else {
                0L
            }

            if ($existingLength -gt $expectedLength) {
                throw "Segment is larger than expected: $SegmentPath"
            }
            if ($existingLength -eq $expectedLength) {
                break
            }

            $nextByte = $RangeStart + $existingLength
            $remainingLength = $RangeEnd - $nextByte + 1
            $range = "$nextByte-$RangeEnd"

            Remove-Item -LiteralPath $chunkPath -Force -ErrorAction SilentlyContinue
            Add-DownloadLog -Path $LogPath -Message "request range=$range"

            & $curlPath `
                @networkArguments `
                --http1.1 `
                -L `
                --fail `
                --silent `
                --show-error `
                --connect-timeout 20 `
                --speed-time $StallTimeoutSeconds `
                --speed-limit 1 `
                --range $range `
                --output $chunkPath `
                $Url 2>> $LogPath
            $curlExitCode = $LASTEXITCODE

            $chunkLength = if (Test-Path -LiteralPath $chunkPath -PathType Leaf) {
                (Get-Item -LiteralPath $chunkPath).Length
            }
            else {
                0L
            }

            if ($chunkLength -gt $remainingLength) {
                throw "Server returned more bytes than requested: range=$range bytes=$chunkLength"
            }

            if ($chunkLength -gt 0) {
                $outputStream = [IO.File]::Open(
                    $SegmentPath,
                    [IO.FileMode]::Append,
                    [IO.FileAccess]::Write,
                    [IO.FileShare]::Read
                )
                try {
                    $inputStream = [IO.File]::OpenRead($chunkPath)
                    try {
                        $inputStream.CopyTo($outputStream)
                    }
                    finally {
                        $inputStream.Dispose()
                    }
                }
                finally {
                    $outputStream.Dispose()
                }

                Remove-Item -LiteralPath $chunkPath -Force
                $noProgressAttempts = 0
                Add-DownloadLog -Path $LogPath -Message "received bytes=$chunkLength curlExit=$curlExitCode"
                continue
            }

            $noProgressAttempts++
            Add-DownloadLog -Path $LogPath -Message "no progress curlExit=$curlExitCode attempt=$noProgressAttempts"
            Start-Sleep -Seconds $RetryDelaySeconds

            if (($noProgressAttempts % 5) -eq 0) {
                Add-DownloadLog -Path $LogPath -Message 'waiting 60 seconds for CDN DNS TTL before reconnect'
                Start-Sleep -Seconds 60
            }
        }

        $actualLength = (Get-Item -LiteralPath $SegmentPath).Length
        if ($actualLength -ne $expectedLength) {
            throw "Segment length mismatch: expected=$expectedLength actual=$actualLength path=$SegmentPath"
        }

        Add-DownloadLog -Path $LogPath -Message "complete bytes=$actualLength"
    }
    finally {
        if ($lockStream) {
            $lockStream.Dispose()
        }
    }

    exit 0
}

$resolvedOutputFile = [IO.Path]::GetFullPath($OutputFile)
$outputDirectory = Split-Path -Parent $resolvedOutputFile
$stateDirectory = $resolvedOutputFile + '.download'

New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null

$selectedNetworkMode = Select-FastestNetworkMode `
    -TargetUrl $Url `
    -RequestedMode $NetworkMode `
    -ProbeDirectory $stateDirectory
$networkArguments = @(
    Get-CurlNetworkArguments -TargetUrl $Url -Mode $selectedNetworkMode
)

$probeHeaders = Join-Path $stateDirectory 'probe.headers'
$probeBody = Join-Path $stateDirectory 'probe.body'
$probeLog = Join-Path $stateDirectory 'probe.log'
$sourceSize = 0L
$probeAttempt = 0

while ($sourceSize -le 0) {
    $probeAttempt++
    Remove-Item -LiteralPath $probeHeaders, $probeBody -Force -ErrorAction SilentlyContinue

    & $curlPath `
        @networkArguments `
        --http1.1 `
        -L `
        --fail `
        --silent `
        --show-error `
        --connect-timeout 20 `
        --speed-time $StallTimeoutSeconds `
        --speed-limit 1 `
        --range '0-0' `
        --dump-header $probeHeaders `
        --output $probeBody `
        $Url 2>> $probeLog
    $probeExitCode = $LASTEXITCODE

    if (($probeExitCode -eq 0) -and (Test-Path -LiteralPath $probeHeaders -PathType Leaf)) {
        $headerText = Get-Content -LiteralPath $probeHeaders -Raw -Encoding ASCII
        $matches = [regex]::Matches(
            $headerText,
            '(?im)^Content-Range:\s*bytes\s+\d+-\d+/(\d+)\s*$'
        )
        if ($matches.Count -gt 0) {
            $sourceSize = [long]$matches[$matches.Count - 1].Groups[1].Value
        }
    }

    if ($sourceSize -le 0) {
        Add-DownloadLog -Path $probeLog -Message "range probe failed exit=$probeExitCode attempt=$probeAttempt"
        Start-Sleep -Seconds $RetryDelaySeconds
        if (($probeAttempt % 5) -eq 0) {
            Add-DownloadLog -Path $probeLog -Message 'waiting 60 seconds for CDN DNS TTL before reconnect'
            Start-Sleep -Seconds 60
        }
    }
}

Remove-Item -LiteralPath $probeBody -Force -ErrorAction SilentlyContinue

if (($ExpectedSize -gt 0) -and ($ExpectedSize -ne $sourceSize)) {
    throw "Source size mismatch: expected=$ExpectedSize actual=$sourceSize"
}
$ExpectedSize = $sourceSize

if (-not $ExpectedSha256) {
    $sourceName = [IO.Path]::GetFileNameWithoutExtension(([Uri]$Url).AbsolutePath)
    if ($sourceName -match '^[0-9a-fA-F]{64}$') {
        $ExpectedSha256 = $sourceName
    }
}

if (Test-Path -LiteralPath $resolvedOutputFile -PathType Leaf) {
    $existingFile = Get-Item -LiteralPath $resolvedOutputFile
    if ($existingFile.Length -ne $ExpectedSize) {
        throw "Output already exists with an unexpected size: $resolvedOutputFile"
    }
    if ($ExpectedSha256) {
        $existingHash = (Get-FileHash -LiteralPath $resolvedOutputFile -Algorithm SHA256).Hash
        if ($existingHash -ine $ExpectedSha256) {
            throw "Output already exists with an unexpected SHA-256: $resolvedOutputFile"
        }
    }

    [pscustomobject]@{
        Status = 'AlreadyComplete'
        Path = $resolvedOutputFile
        Bytes = $existingFile.Length
        Sha256 = if ($ExpectedSha256) { $ExpectedSha256.ToUpperInvariant() } else { $null }
        NetworkMode = $selectedNetworkMode
        Proxy = if ($selectedNetworkMode -eq 'Direct') {
            'BypassedForDownloadProcessOnly'
        }
        else {
            'SystemProxyForDownloadProcessOnly'
        }
        Segments = $SegmentCount
    }
    exit 0
}

$segmentSize = [long][Math]::Ceiling($ExpectedSize / [double]$SegmentCount)
$segments = @()
$workers = @()

for ($index = 0; $index -lt $SegmentCount; $index++) {
    $start = [long]$index * $segmentSize
    if ($start -ge $ExpectedSize) {
        break
    }

    $end = [Math]::Min($ExpectedSize - 1, $start + $segmentSize - 1)
    $segmentPath = Join-Path $stateDirectory ('segment-{0:D2}.part' -f $index)
    $logPath = Join-Path $stateDirectory ('segment-{0:D2}.log' -f $index)
    $argumentLine = @(
        '-NoProfile'
        '-ExecutionPolicy Bypass'
        ('-File "{0}"' -f $PSCommandPath)
        '-InternalWorker'
        ('-Url "{0}"' -f $Url)
        ('-RangeStart {0}' -f $start)
        ('-RangeEnd {0}' -f $end)
        ('-SegmentPath "{0}"' -f $segmentPath)
        ('-LogPath "{0}"' -f $logPath)
        ('-NetworkMode {0}' -f $selectedNetworkMode)
        ('-StallTimeoutSeconds {0}' -f $StallTimeoutSeconds)
        ('-RetryDelaySeconds {0}' -f $RetryDelaySeconds)
    ) -join ' '

    $process = Start-Process `
        -FilePath 'powershell.exe' `
        -ArgumentList $argumentLine `
        -WindowStyle Hidden `
        -PassThru

    $segments += [pscustomobject]@{
        Index = $index
        Start = $start
        End = $end
        ExpectedLength = $end - $start + 1
        Path = $segmentPath
    }
    $workers += $process
}

do {
    $downloadedBytes = 0L
    foreach ($segment in $segments) {
        if (Test-Path -LiteralPath $segment.Path -PathType Leaf) {
            $downloadedBytes += [Math]::Min(
                (Get-Item -LiteralPath $segment.Path).Length,
                $segment.ExpectedLength
            )
        }
    }

    $percent = [Math]::Min(100, [Math]::Round(100 * $downloadedBytes / $ExpectedSize, 1))
    Write-Progress `
        -Activity "Downloading LibTV video over $selectedNetworkMode segmented connections" `
        -Status "$percent% ($downloadedBytes / $ExpectedSize bytes)" `
        -PercentComplete $percent

    $running = @($workers | Where-Object { -not $_.HasExited })
    if ($running.Count -gt 0) {
        Start-Sleep -Seconds 5
    }
} while ($running.Count -gt 0)

Write-Progress -Activity "Downloading LibTV video over $selectedNetworkMode segmented connections" -Completed

$failedWorkers = @($workers | Where-Object { $_.ExitCode -ne 0 })
if ($failedWorkers.Count -gt 0) {
    throw "One or more segment workers failed: $(@($failedWorkers.Id) -join ', ')"
}

foreach ($segment in $segments) {
    $segmentFile = Get-Item -LiteralPath $segment.Path -ErrorAction Stop
    if ($segmentFile.Length -ne $segment.ExpectedLength) {
        throw "Segment length mismatch: expected=$($segment.ExpectedLength) actual=$($segmentFile.Length) path=$($segment.Path)"
    }
}

$assemblingFile = $resolvedOutputFile + '.assembling'
$outputStream = [IO.File]::Create($assemblingFile)
try {
    foreach ($segment in ($segments | Sort-Object Index)) {
        $inputStream = [IO.File]::OpenRead($segment.Path)
        try {
            $inputStream.CopyTo($outputStream)
        }
        finally {
            $inputStream.Dispose()
        }
    }
}
finally {
    $outputStream.Dispose()
}

$assembledItem = Get-Item -LiteralPath $assemblingFile
if ($assembledItem.Length -ne $ExpectedSize) {
    throw "Final length mismatch: expected=$ExpectedSize actual=$($assembledItem.Length)"
}

$actualSha256 = (Get-FileHash -LiteralPath $assemblingFile -Algorithm SHA256).Hash
if ($ExpectedSha256 -and ($actualSha256 -ine $ExpectedSha256)) {
    throw "Final SHA-256 mismatch: expected=$ExpectedSha256 actual=$actualSha256"
}

$ffprobe = Get-Command ffprobe -ErrorAction SilentlyContinue
if ($ffprobe -and ([IO.Path]::GetExtension($resolvedOutputFile) -ieq '.mp4')) {
    & $ffprobe.Source -v error -show_entries format=duration,size -of json $assemblingFile | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "ffprobe rejected the assembled MP4: $assemblingFile"
    }
}

[IO.File]::Move($assemblingFile, $resolvedOutputFile)

[pscustomobject]@{
    Status = 'Complete'
    Path = $resolvedOutputFile
    Bytes = $ExpectedSize
    Sha256 = $actualSha256
    NetworkMode = $selectedNetworkMode
    Proxy = if ($selectedNetworkMode -eq 'Direct') {
        'BypassedForDownloadProcessOnly'
    }
    else {
        'SystemProxyForDownloadProcessOnly'
    }
    Segments = $segments.Count
    StateDirectory = $stateDirectory
}

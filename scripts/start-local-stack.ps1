param(
    [int]$StartupTimeoutSeconds = 45
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$apiScript = Join-Path $PSScriptRoot 'start-local-api.ps1'
$frontendScript = Join-Path $PSScriptRoot 'start-local-frontend.ps1'
$checkScript = Join-Path $PSScriptRoot 'check-local-services.ps1'
. (Join-Path $PSScriptRoot 'local-instance-identity.ps1')
. (Join-Path $PSScriptRoot 'stack-logging.ps1')

$logTarget = Get-StackLogPath -ProjectRoot $projectRoot -Name 'stack.autostart.log'
if ($logTarget.Degraded) {
    Write-Warning "Stack startup logging is degraded: $($logTarget.Reason)"
}
$stackLogPath = $logTarget.Path
$logDir = Split-Path -Parent $stackLogPath

function Write-StackNote([string]$Message) {
    Write-StackLog -Path $stackLogPath -Text @(
        ("[{0}] {1}" -f [DateTimeOffset]::Now.ToString('o'), $Message)
    )
    Write-Host $Message
}

function Test-Ready([string]$Uri, [int]$Port) {
    # Both switches are required here, not just in Test-ApiCurrent. The API is
    # started as `uv run uvicorn ...`, so the listener's own command line carries
    # no workspace path and the process-only check reports the workspace's own
    # healthy API as a foreign owner. With the switches omitted this function
    # returned $false for port 8000 no matter how healthy the API was, so
    # apiReady stayed false for the whole startup timeout while the rest of the
    # stack (frontend + proxy) was already serving.
    $identity = Get-WorkspacePortIdentity `
        -Port $Port `
        -ProjectRoot $projectRoot `
        -AllowLauncherAncestry `
        -AllowBehaviouralIdentity
    if (-not $identity.Listening -or -not $identity.OwnedByWorkspace) {
        return $false
    }
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2
        return $response.StatusCode -eq 200
    }
    catch { return $false }
}

function Test-ApiCurrent {
    # AllowBehaviouralIdentity additionally accepts the API's own sourceRevision
    # as proof of ownership. The listener of `uv run uvicorn` has no workspace
    # path in its command line, so the process-only check used to report the
    # workspace's own healthy API as unavailable and restart it forever.
    $identity = Get-WorkspacePortIdentity `
        -Port 8000 `
        -ProjectRoot $projectRoot `
        -AllowLauncherAncestry `
        -AllowBehaviouralIdentity
    if (-not $identity.Listening -or -not $identity.OwnedByWorkspace) { return $false }
    try {
        $status = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/system/status' -TimeoutSec 2
        $expectedRevision = Get-WorkspaceSourceRevision -ProjectRoot $projectRoot
        return $status.sourceRevision -eq $expectedRevision
    }
    catch { return $false }
}

function Get-ProcessDiagnosis($Process) {
    if (-not $Process) { return 'not spawned' }
    try {
        $Process.Refresh()
        if ($Process.HasExited) {
            return "PID $($Process.Id) has exited with code $($Process.ExitCode)"
        }
        return "PID $($Process.Id) is still running"
    }
    catch {
        return "PID $($Process.Id) state unavailable: $($_.Exception.Message)"
    }
}

Write-StackLogHeader -Path $stackLogPath -Component 'stack-launcher' -Detail "timeout=${StartupTimeoutSeconds}s"

Assert-WorkspacePortOwnership `
    -Port 8000 `
    -ProjectRoot $projectRoot `
    -ServiceName 'API' `
    -AllowLauncherAncestry `
    -AllowBehaviouralIdentity | Out-Null
Assert-WorkspacePortOwnership -Port 5173 -ProjectRoot $projectRoot -ServiceName 'frontend' | Out-Null

# -PassThru is the difference between "we started something" and "we know what
# we started": without it a launcher that dies instantly looks identical to one
# that is still working, which is exactly how the API stayed missing for hours.
$apiProcess = $null
if (-not (Test-ApiCurrent)) {
    $apiProcess = Start-Process `
        -FilePath 'powershell.exe' `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $apiScript) `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -PassThru
    Write-StackNote "Started the API launcher (PID $($apiProcess.Id))."
}
else {
    Write-StackNote 'API is already current; leaving it running.'
}

$frontendProcess = $null
if (-not (Test-Ready 'http://127.0.0.1:5173/' 5173)) {
    $frontendProcess = Start-Process `
        -FilePath 'powershell.exe' `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $frontendScript) `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -PassThru
    Write-StackNote "Started the frontend launcher (PID $($frontendProcess.Id))."
}
else {
    Write-StackNote 'Frontend is already serving; leaving it running.'
}

$deadline = [DateTimeOffset]::Now.AddSeconds($StartupTimeoutSeconds)
$apiReady = $false
$frontendReady = $false
$proxyReady = $false
$launcherDiedEarly = $false
do {
    Assert-WorkspacePortOwnership `
        -Port 8000 `
        -ProjectRoot $projectRoot `
        -ServiceName 'API' `
        -AllowLauncherAncestry `
        -AllowBehaviouralIdentity | Out-Null
    Assert-WorkspacePortOwnership -Port 5173 -ProjectRoot $projectRoot -ServiceName 'frontend' | Out-Null
    $apiReady = (Test-Ready 'http://127.0.0.1:8000/api/v1/health/ready' 8000) -and (Test-ApiCurrent)
    $frontendReady = Test-Ready 'http://127.0.0.1:5173/' 5173
    $proxyReady = Test-Ready 'http://127.0.0.1:5173/api/v1/health/ready' 5173
    if ($apiReady -and $frontendReady -and $proxyReady) { break }
    # A launcher that already exited can never make the stack ready. Stop waiting
    # for the full timeout and report immediately with its exit code.
    if ($apiProcess -and -not $apiReady) {
        $apiProcess.Refresh()
        if ($apiProcess.HasExited) { $launcherDiedEarly = $true; break }
    }
    if ($frontendProcess -and -not $frontendReady) {
        $frontendProcess.Refresh()
        if ($frontendProcess.HasExited) { $launcherDiedEarly = $true; break }
    }
    Start-Sleep -Milliseconds 500
} while ([DateTimeOffset]::Now -lt $deadline)

if (-not ($apiReady -and $frontendReady -and $proxyReady)) {
    # NOTE: this block must never use Write-Error. Under
    # $ErrorActionPreference = 'Stop' Write-Error raises a terminating error, so
    # the diagnostic below it never ran and the whole failure looked like a
    # silent timeout. Collect everything first, write it to the log, print it,
    # and only then exit with a non-zero code.
    $diagnosis = [System.Collections.Generic.List[string]]::new()
    $diagnosis.Add("Local stack did not become ready within $StartupTimeoutSeconds seconds.")
    $diagnosis.Add("apiReady=$apiReady frontendReady=$frontendReady proxyReady=$proxyReady")
    $diagnosis.Add("api launcher: $(Get-ProcessDiagnosis $apiProcess)")
    $diagnosis.Add("frontend launcher: $(Get-ProcessDiagnosis $frontendProcess)")
    if ($launcherDiedEarly) {
        $diagnosis.Add('Waiting stopped early because a launcher process exited.')
    }
    try {
        $identity = Get-WorkspacePortIdentity `
            -Port 8000 `
            -ProjectRoot $projectRoot `
            -AllowLauncherAncestry `
            -AllowBehaviouralIdentity
        $diagnosis.Add(
            "port 8000: listening=$($identity.Listening) owned=$($identity.OwnedByWorkspace) " +
            "evidence=$($identity.OwnershipEvidence) pid=$($identity.ProcessId)"
        )
        if ($identity.CommandLine) {
            $diagnosis.Add("port 8000 owner command line: $($identity.CommandLine)")
        }
    }
    catch {
        $diagnosis.Add("port 8000 identity probe failed: $($_.Exception.Message)")
    }
    foreach ($name in @(
            'stack.autostart.log',
            'api.autostart.log',
            'api.preflight.log',
            'migration.autostart.log',
            'frontend.autostart.log',
            'frontend.preflight.log'
        )) {
        $diagnosis.Add("--- $name (tail 40) ---")
        $path = Join-Path $logDir $name
        if (Test-Path -LiteralPath $path) {
            foreach ($line in @(Get-Content -LiteralPath $path -Tail 40)) {
                $diagnosis.Add([string]$line)
            }
        }
        else {
            $diagnosis.Add('  <file does not exist>')
        }
    }
    $diagnosis.Add('--- end of diagnosis ---')
    Write-StackLog -Path $stackLogPath -Text $diagnosis.ToArray()
    foreach ($line in $diagnosis) { Write-Host $line }
    exit 1
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $checkScript -RequireFrontend
if ($LASTEXITCODE -ne 0) {
    Write-StackNote "Post-startup service check failed with exit code $LASTEXITCODE."
    exit $LASTEXITCODE
}
Write-StackNote 'Local stack is ready: http://127.0.0.1:5173'
Write-Host 'Local stack is ready: http://127.0.0.1:5173'

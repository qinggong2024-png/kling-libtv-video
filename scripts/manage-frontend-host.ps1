param(
    [ValidateSet('Status', 'Serve', 'Install', 'Uninstall', 'Start', 'Stop')]
    [string]$Action = 'Status',
    [string]$ProjectRoot,
    [string]$HostAddress = '0.0.0.0',
    [int]$Port = 5173,
    [string]$NodePath,
    [string]$TaskName = 'LibTV Frontend Host',
    [int]$StartupTimeoutSeconds = 40
)

# Frontend-only host. It keeps the Vite entry point on the LAN up after logon
# and nothing else.
#
# Deliberate non-goals, because the neighbouring scripts do all three:
#   * it never runs `alembic upgrade`, so it cannot migrate production data;
#   * it never starts the local Runner, so it cannot spend money;
#   * it never touches port 8000, which belongs to the LibTVProductionApi
#     Windows service.
# Keep this file ASCII-only: Windows PowerShell 5.1 decodes a .ps1 without a BOM
# using the ANSI code page, so non-ASCII text here would be silently mangled.

$ErrorActionPreference = 'Stop'
if (-not $ProjectRoot) { $ProjectRoot = Split-Path -Parent $PSScriptRoot }
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$scriptPath = $MyInvocation.MyCommand.Path

. (Join-Path $PSScriptRoot 'local-instance-identity.ps1')
. (Join-Path $PSScriptRoot 'stack-logging.ps1')

$logTarget = Get-StackLogPath -ProjectRoot $ProjectRoot -Name 'frontend.host.log'
$frontendLogPath = $logTarget.Path

function Stop-FrontendStartup([string]$Message) {
    # Logged before throwing: the scheduled task runs this in a hidden window
    # with no output redirection, so an unlogged throw leaves no evidence.
    Write-StackLog -Path $frontendLogPath -Text @(
        ("[{0}] FAILED: {1}" -f [DateTimeOffset]::Now.ToString('o'), $Message)
    )
    throw $Message
}

function Resolve-NodeExecutable([string]$Explicit) {
    # A logon-triggered task does not inherit an interactive shell's PATH, and
    # this machine has no node under the machine PATH or Program Files. Probe
    # the explicit override, then every PATH scope, then return the absolute
    # path so the task can be pinned to it.
    $candidates = @()
    if ($Explicit) { $candidates += $Explicit }
    foreach ($scope in @('Machine', 'User')) {
        $value = [Environment]::GetEnvironmentVariable('Path', $scope)
        if (-not $value) { continue }
        foreach ($dir in ($value -split ';')) { $candidates += (Join-Path $dir.Trim() 'node.exe') }
    }
    foreach ($dir in ($env:PATH -split ';')) { $candidates += (Join-Path $dir.Trim() 'node.exe') }

    foreach ($candidate in $candidates) {
        if (-not $candidate) { continue }
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $version = $null
        try { $version = (& $candidate --version 2>&1 | Select-Object -First 1) }
        catch { continue }
        if ($LASTEXITCODE -eq 0 -and $version) {
            return [pscustomobject]@{
                Path = (Resolve-Path -LiteralPath $candidate).Path
                Version = [string]$version
            }
        }
    }
    return $null
}

function Get-ViteEntryPoint([string]$Root) {
    return (Join-Path $Root 'frontend\node_modules\vite\bin\vite.js')
}

function Test-FrontendHttp([int]$TargetPort) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$TargetPort/" -TimeoutSec 5
        return ($response.StatusCode -eq 200)
    }
    catch {
        return $false
    }
}

function Get-FrontendHostStatus {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    $identity = Get-WorkspacePortIdentity -Port $Port -ProjectRoot $ProjectRoot
    $taskState = 'NotInstalled'
    $lastRun = $null
    $lastResult = $null
    $triggerCount = 0
    if ($task) {
        $info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
        $taskState = [string]$task.State
        $lastRun = $info.LastRunTime
        $lastResult = '0x{0:X8}' -f [uint32]$info.LastTaskResult
        $triggerCount = @($task.Triggers).Count
    }
    return [pscustomobject]@{
        TaskName = $TaskName
        TaskState = $taskState
        TriggerCount = $triggerCount
        LastRunTime = $lastRun
        LastTaskResult = $lastResult
        Listening = $identity.Listening
        OwnedByWorkspace = $identity.OwnedByWorkspace
        ProcessId = $identity.ProcessId
        Serving = if ($identity.Listening) { Test-FrontendHttp -TargetPort $Port } else { $false }
        HostAddress = $HostAddress
        Port = $Port
        LogPath = $frontendLogPath
    }
}

function Invoke-FrontendServe {
    $frontendRoot = Join-Path $ProjectRoot 'frontend'
    Set-Location -LiteralPath $frontendRoot
    Write-StackLogHeader -Path $frontendLogPath -Component 'frontend-host' `
        -Detail "projectRoot=$ProjectRoot cwd=$frontendRoot host=$HostAddress port=$Port"

    # Vite resolves its project root from the working directory, exactly as
    # 'npm.cmd run dev --prefix frontend' does. Running it from the repository
    # root instead serves a directory without index.html and answers 404 on /.
    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

    $node = Resolve-NodeExecutable -Explicit $NodePath
    if (-not $node) {
        Stop-FrontendStartup 'node.exe was not found in -NodePath, the machine PATH, the user PATH or the process PATH.'
    }
    $viteEntry = Get-ViteEntryPoint -Root $ProjectRoot
    if (-not (Test-Path -LiteralPath $viteEntry -PathType Leaf)) {
        Stop-FrontendStartup "Vite entry point is missing: $viteEntry. Run 'npm.cmd install --prefix frontend' first."
    }
    Write-StackLog -Path $frontendLogPath -Text @(
        ("[{0}] node {1} ({2})" -f [DateTimeOffset]::Now.ToString('o'), $node.Path, $node.Version)
        ("[{0}] vite {1}" -f [DateTimeOffset]::Now.ToString('o'), $viteEntry)
    )

    # The port check only guards our own entry point; the API on 8000 is owned by
    # the Windows service and is never inspected or stopped here.
    $existing = Assert-WorkspacePortOwnership -Port $Port -ProjectRoot $ProjectRoot -ServiceName 'frontend'
    if ($existing.Listening) {
        if (Test-FrontendHttp -TargetPort $Port) {
            Write-StackLog -Path $frontendLogPath -Text @(
                ("[{0}] frontend already served by PID {1}; nothing to do" -f `
                    [DateTimeOffset]::Now.ToString('o'), $existing.ProcessId)
            )
            exit 0
        }
        Stop-FrontendStartup "Port $Port is owned by this workspace (PID $($existing.ProcessId)) but the frontend check failed."
    }

    $env:VITE_HOST = $HostAddress
    $env:VITE_API_PROXY = 'http://127.0.0.1:8000'

    # Vite is invoked through its node entry point instead of npm.cmd: npm.cmd
    # is a .cmd shim and it is not guaranteed to resolve in a non-interactive
    # task environment.
    #
    # Supervisor loop. Task Scheduler's restart-on-failure does not fire for a
    # task started manually, and a frontend that dies unattended is exactly the
    # outage this host exists to prevent, so the host restarts Vite itself. The
    # backoff is capped and resets once a run has stayed up long enough to count
    # as healthy, so a broken configuration degrades into slow retries instead
    # of a tight spin.
    $delay = 5
    while ($true) {
        $startedAt = Get-Date
        Write-StackLog -Path $frontendLogPath -Text @(
            ("[{0}] starting vite (host {1}, port {2})" -f `
                [DateTimeOffset]::Now.ToString('o'), $HostAddress, $Port)
        )
        & $node.Path $viteEntry '--host' $HostAddress '--port' ([string]$Port) '--strictPort' 2>&1 |
            Write-StackLogRecord -Path $frontendLogPath
        $exitCode = $LASTEXITCODE
        $uptimeSeconds = [int]((Get-Date) - $startedAt).TotalSeconds
        Write-StackLog -Path $frontendLogPath -Text @(
            ("[{0}] vite exited with code {1} after {2}s; restarting in {3}s" -f `
                [DateTimeOffset]::Now.ToString('o'), $exitCode, $uptimeSeconds, $delay)
        )
        Start-Sleep -Seconds $delay
        if ($uptimeSeconds -ge 120) { $delay = 5 } else { $delay = [Math]::Min(60, $delay * 2) }
    }
}

function Install-FrontendHost {
    $node = Resolve-NodeExecutable -Explicit $NodePath
    if (-not $node) {
        throw 'node.exe was not found. Pass -NodePath with the absolute path to node.exe.'
    }
    $viteEntry = Get-ViteEntryPoint -Root $ProjectRoot
    if (-not (Test-Path -LiteralPath $viteEntry -PathType Leaf)) {
        throw "Vite entry point is missing: $viteEntry. Run 'npm.cmd install --prefix frontend' first."
    }

    $powershell = Join-Path $PSHOME 'powershell.exe'
    # The absolute node path is recorded in the task so a future logon does not
    # depend on PATH resolution.
    $arguments = @(
        '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass',
        '-File', "`"$scriptPath`"",
        '-Action', 'Serve',
        '-ProjectRoot', "`"$ProjectRoot`"",
        '-HostAddress', $HostAddress,
        '-Port', ([string]$Port),
        '-NodePath', "`"$($node.Path)`""
    ) -join ' '

    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $taskAction = New-ScheduledTaskAction `
        -Execute $powershell `
        -Argument $arguments `
        -WorkingDirectory $ProjectRoot
    # AtLogOn is the primary trigger. The repeating trigger is a second line of
    # defence: it revives the host if the task process itself is killed, and
    # -MultipleInstances IgnoreNew keeps that from duplicating a healthy one.
    # No -RepetitionDuration: Task Scheduler rejects an "infinite" TimeSpan and
    # an omitted duration already means repeat indefinitely.
    $trigger = @(
        (New-ScheduledTaskTrigger -AtLogOn -User $currentUser)
        (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 1))
    )
    $principal = New-ScheduledTaskPrincipal `
        -UserId $currentUser `
        -LogonType Interactive `
        -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RestartCount 999 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -MultipleInstances IgnoreNew

    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $taskAction `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description 'Serve the LibTV Vite frontend on the LAN after logon, restarting Vite if it dies. Frontend only: no alembic upgrade, no Runner, no port 8000.' `
        -Force | Out-Null

    Start-ScheduledTask -TaskName $TaskName
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 2
        if (Test-FrontendHttp -TargetPort $Port) { break }
    }
    Get-FrontendHostStatus
}

function Stop-FrontendHost {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    $identity = Get-WorkspacePortIdentity -Port $Port -ProjectRoot $ProjectRoot
    if ($identity.Listening -and $identity.OwnedByWorkspace) {
        # Only a listener this workspace owns is ever stopped; a foreign process
        # on our port is reported, never killed.
        Stop-Process -Id $identity.ProcessId -ErrorAction SilentlyContinue
    }
    Get-FrontendHostStatus
}

switch ($Action) {
    'Status' { Get-FrontendHostStatus | Format-List }
    'Serve' { Invoke-FrontendServe }
    'Install' { Install-FrontendHost | Format-List }
    'Uninstall' {
        Stop-FrontendHost | Out-Null
        if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        }
        Get-FrontendHostStatus | Format-List
    }
    'Start' {
        Start-ScheduledTask -TaskName $TaskName
        Start-Sleep -Seconds 2
        Get-FrontendHostStatus | Format-List
    }
    'Stop' { Stop-FrontendHost | Format-List }
}

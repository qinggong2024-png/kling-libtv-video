function Test-WorkspaceProcessIdentity {
    param(
        [string]$CommandLine,
        [string]$ExecutablePath,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $resolvedRoot = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\', '/')
    $rootCandidates = @(
        $resolvedRoot,
        $resolvedRoot.Replace('\', '/')
    )
    foreach ($value in @($CommandLine, $ExecutablePath)) {
        if ([string]::IsNullOrWhiteSpace($value)) { continue }
        foreach ($candidate in $rootCandidates) {
            if ($value.IndexOf($candidate, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                return $true
            }
        }
    }
    return $false
}

function Get-AlembicRevisionIds {
    param(
        [object[]]$Output
    )

    return @(
        $Output |
            ForEach-Object {
                $match = [regex]::Match([string]$_, '^[0-9a-fA-F]{12}')
                if ($match.Success) { $match.Value.ToLowerInvariant() }
            } |
            Sort-Object -Unique
    )
}

function Get-WorkspaceSourceRevision {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $resolvedRoot = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\', '/')
    $sourceFiles = @(
        Get-ChildItem -LiteralPath (Join-Path $resolvedRoot 'backend\src') -File -Recurse -Filter '*.py'
        Get-ChildItem -LiteralPath (Join-Path $resolvedRoot 'backend\alembic') -File -Recurse -Filter '*.py'
        Get-Item -LiteralPath (Join-Path $resolvedRoot 'backend\alembic.ini')
        Get-Item -LiteralPath (Join-Path $resolvedRoot 'pyproject.toml')
        Get-Item -LiteralPath (Join-Path $resolvedRoot 'uv.lock')
    ) | Sort-Object FullName

    $manifest = foreach ($file in $sourceFiles) {
        $relativePath = $file.FullName.Substring($resolvedRoot.Length).TrimStart('\', '/').Replace('\', '/')
        $fileHash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$relativePath`0$fileHash"
    }
    $bytes = [Text.Encoding]::UTF8.GetBytes(($manifest -join "`n"))
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha256.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
    }
}

$script:StackProcessTableCache = $null
$script:StackProcessTableTakenAt = [DateTimeOffset]::MinValue
$script:StackPortIdentityCache = @{}
$script:StackApiRevisionCache = @{}

function Get-WorkspaceLauncherPaths {
    # Absolute paths of the launcher scripts that are allowed to own a port on
    # behalf of this workspace. Matching on these exact paths is what makes the
    # ancestry test below unforgeable: a random shell whose command line merely
    # mentions the project directory does not qualify.
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $root = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\', '/')
    return @(
        (Join-Path $root 'scripts\start-local-api.ps1'),
        (Join-Path $root 'scripts\start-local-stack.ps1'),
        (Join-Path $root 'scripts\start-lan-stack.ps1'),
        (Join-Path $root 'scripts\start-local-frontend.ps1'),
        (Join-Path $root 'scripts\watch-local-stack.ps1')
    )
}

function Get-StackProcessTable {
    # One Win32_Process snapshot instead of one query per ancestor hop: the
    # polling loops resolve identity several times a second. The snapshot is
    # short-lived on purpose, because watch-local-stack.ps1 runs for days and a
    # permanently cached table would describe processes that no longer exist.
    param(
        [switch]$Refresh,
        [double]$MaxAgeSeconds = 2
    )

    $now = [DateTimeOffset]::Now
    if (-not $Refresh -and $null -ne $script:StackProcessTableCache) {
        $age = ($now - $script:StackProcessTableTakenAt).TotalSeconds
        if ($age -le $MaxAgeSeconds) {
            return $script:StackProcessTableCache
        }
    }
    $index = @{}
    foreach ($process in @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)) {
        $index[[int]$process.ProcessId] = $process
    }
    $script:StackProcessTableCache = $index
    $script:StackProcessTableTakenAt = $now
    return $index
}

function Test-WorkspaceLauncherAncestry {
    # The listener process alone is often not identifiable: the API is started
    # as
    #     powershell.exe -File <workspace>\scripts\start-local-api.ps1
    #       -> cmd.exe /d /c "uv run uvicorn libtv_agent.app:create_app ..."
    #       -> uv.exe -> uvicorn.exe -> python.exe (holds port 8000)
    # so the real listener's Win32_Process.CommandLine contains NO workspace
    # path at all and its ExecutablePath lives in %APPDATA%\uv. Walking the
    # ancestor chain and looking for one of our own launcher scripts is the
    # reliable, path-based replacement.
    param(
        [Parameter(Mandatory = $true)]
        [int]$ProcessId,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [int]$MaxDepth = 12
    )

    if ($ProcessId -le 0) { return $false }
    $launchers = Get-WorkspaceLauncherPaths -ProjectRoot $ProjectRoot
    $table = Get-StackProcessTable
    $currentId = $ProcessId
    for ($depth = 0; $depth -lt $MaxDepth; $depth++) {
        $node = $table[$currentId]
        if (-not $node -or -not $node.ParentProcessId) { return $false }
        $parentId = [int]$node.ParentProcessId
        $parent = $table[$parentId]
        if (-not $parent) { return $false }
        $commandLine = [string]$parent.CommandLine
        if ($commandLine) {
            foreach ($launcher in $launchers) {
                if ($commandLine.IndexOf($launcher, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                    return $true
                }
            }
        }
        $currentId = $parentId
    }
    return $false
}

function Test-WorkspaceApiRevisionIdentity {
    # Behavioural fallback for when the launcher ancestry is already gone (the
    # wrapper process exited but the API kept running). The API reports the
    # SHA-256 of this workspace's own backend sources, which a foreign process
    # cannot produce.
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [int]$TimeoutSeconds = 3
    )

    $cacheKey = "$Port|$ProjectRoot"
    if ($script:StackApiRevisionCache.ContainsKey($cacheKey)) {
        return [bool]$script:StackApiRevisionCache[$cacheKey]
    }

    $matched = $false
    try {
        $status = Invoke-RestMethod `
            -Uri "http://127.0.0.1:$Port/api/v1/system/status" `
            -TimeoutSec $TimeoutSeconds
        $reported = [string]$status.sourceRevision
        if ($reported) {
            $expected = Get-WorkspaceSourceRevision -ProjectRoot $ProjectRoot
            $matched = $reported -eq $expected
        }
    }
    catch {
        $matched = $false
    }
    $script:StackApiRevisionCache[$cacheKey] = $matched
    return $matched
}

function Get-WorkspacePortIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [switch]$AllowLauncherAncestry,
        [switch]$AllowBehaviouralIdentity,
        # Opt-in only. start-local-api.ps1 waits for a port to be released in a
        # loop, and a cached identity would keep reporting the dead listener as
        # still listening, which turned a successful restart into a hard abort.
        [switch]$UseIdentityCache
    )

    $cacheKey = "$Port|$ProjectRoot"
    if ($UseIdentityCache -and $script:StackPortIdentityCache.ContainsKey($cacheKey)) {
        return $script:StackPortIdentityCache[$cacheKey]
    }

    $listener = $null
    $process = $null
    $fallbackProcess = $null
    for ($attempt = 0; $attempt -lt 3; $attempt++) {
        $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
            Sort-Object OwningProcess -Unique |
            Select-Object -First 1
        if (-not $listener) { break }
        $processId = [int]$listener.OwningProcess
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
        $fallbackProcess = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($process -or $fallbackProcess) { break }
        Start-Sleep -Milliseconds 100
    }
    if (-not $listener) {
        return [pscustomobject]@{
            Port = $Port
            Listening = $false
            OwnedByWorkspace = $false
            OwnershipEvidence = 'none'
            CommandLine = $null
            ProcessId = $null
            ProcessName = $null
            ExecutablePath = $null
        }
    }

    $processId = [int]$listener.OwningProcess
    $commandLine = if ($process) { [string]$process.CommandLine } else { $null }
    $executablePath = if ($process) { [string]$process.ExecutablePath } else { $null }

    # Ownership is established from the strongest available evidence. The old
    # behaviour (process command line only) reported the workspace's own API as
    # a foreign process whenever it had been launched through `uv run`, which
    # made the watchdog restart it forever without ever succeeding.
    $evidence = 'none'
    $owned = Test-WorkspaceProcessIdentity `
        -CommandLine $commandLine `
        -ExecutablePath $executablePath `
        -ProjectRoot $ProjectRoot
    if ($owned) {
        $evidence = 'process'
    }
    elseif ($AllowLauncherAncestry -and (Test-WorkspaceLauncherAncestry -ProcessId $processId -ProjectRoot $ProjectRoot)) {
        $owned = $true
        $evidence = 'launcher-ancestry'
    }
    elseif ($AllowBehaviouralIdentity -and (Test-WorkspaceApiRevisionIdentity -Port $Port -ProjectRoot $ProjectRoot)) {
        $owned = $true
        $evidence = 'api-source-revision'
    }

    $identity = [pscustomobject]@{
        Port = $Port
        Listening = $true
        OwnedByWorkspace = $owned
        OwnershipEvidence = $evidence
        CommandLine = $commandLine
        ProcessId = $processId
        ProcessName = if ($fallbackProcess) { $fallbackProcess.ProcessName } else { $null }
        ExecutablePath = $executablePath
    }
    if ($UseIdentityCache) {
        $script:StackPortIdentityCache[$cacheKey] = $identity
    }
    return $identity
}

function Assert-WorkspacePortOwnership {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$ServiceName,
        [switch]$AllowLauncherAncestry,
        [switch]$AllowBehaviouralIdentity,
        [switch]$UseIdentityCache
    )

    $identity = Get-WorkspacePortIdentity `
        -Port $Port `
        -ProjectRoot $ProjectRoot `
        -AllowLauncherAncestry:$AllowLauncherAncestry `
        -AllowBehaviouralIdentity:$AllowBehaviouralIdentity `
        -UseIdentityCache:$UseIdentityCache
    if ($identity.Listening -and -not $identity.OwnedByWorkspace) {
        $processDescription = if ($identity.ProcessName) {
            "$($identity.ProcessName) (PID $($identity.ProcessId))"
        }
        else {
            "PID $($identity.ProcessId)"
        }
        # Include the owning command line so the operator can act without
        # hunting for the process by hand.
        $detail = if ($identity.CommandLine) {
            " Its command line is: $($identity.CommandLine)"
        }
        else {
            ''
        }
        throw (
            "Port $Port is already owned by $processDescription, but that process does not " +
            "belong to this workspace ($ProjectRoot).$detail Refusing to reuse or stop it; close " +
            "the other $ServiceName instance or configure a different port."
        )
    }
    return $identity
}

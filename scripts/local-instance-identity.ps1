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

function Get-WorkspacePortIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

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
            ProcessId = $null
            ProcessName = $null
            ExecutablePath = $null
        }
    }

    $processId = [int]$listener.OwningProcess
    $commandLine = if ($process) { [string]$process.CommandLine } else { $null }
    $executablePath = if ($process) { [string]$process.ExecutablePath } else { $null }
    $owned = Test-WorkspaceProcessIdentity `
        -CommandLine $commandLine `
        -ExecutablePath $executablePath `
        -ProjectRoot $ProjectRoot

    return [pscustomobject]@{
        Port = $Port
        Listening = $true
        OwnedByWorkspace = $owned
        ProcessId = $processId
        ProcessName = if ($fallbackProcess) { $fallbackProcess.ProcessName } else { $null }
        ExecutablePath = $executablePath
    }
}

function Assert-WorkspacePortOwnership {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$ServiceName
    )

    $identity = Get-WorkspacePortIdentity -Port $Port -ProjectRoot $ProjectRoot
    if ($identity.Listening -and -not $identity.OwnedByWorkspace) {
        $processDescription = if ($identity.ProcessName) {
            "$($identity.ProcessName) (PID $($identity.ProcessId))"
        }
        else {
            "PID $($identity.ProcessId)"
        }
        throw (
            "Port $Port is already owned by $processDescription, but that process does not " +
            "belong to this workspace ($ProjectRoot). Refusing to reuse or stop it; close the " +
            "other $ServiceName instance or configure a different port."
        )
    }
    return $identity
}

param(
    [ValidateSet('Preflight', 'Install', 'Start', 'Stop', 'Restart', 'Uninstall', 'Status')]
    [string]$Action = 'Status',
    [ValidateSet('LibTVProductionApi')]
    [string]$ServiceName = 'LibTVProductionApi',
    [ValidateSet('NT SERVICE\LibTVProductionApi')]
    [string]$ServiceAccount = 'NT SERVICE\LibTVProductionApi',
    [string]$DataRoot,
    [string]$PythonPath
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = if ($PythonPath) { $PythonPath } else { Join-Path $projectRoot '.venv\Scripts\python.exe' }
$serviceScript = Join-Path $projectRoot 'backend\src\libtv_agent\api_windows_service.py'

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Administrator PowerShell is required."
    }
}

function Invoke-ApiPreflight {
    if (-not $DataRoot) { throw 'Pass -DataRoot pointing to the existing production configuration directory.' }
    $env:LIBTV_API_DATA_ROOT = (Resolve-Path -LiteralPath $DataRoot).Path
    if (-not (Test-Path -LiteralPath $python)) { throw "Python environment not found: $python" }
    if (-not (Test-Path -LiteralPath $serviceScript)) { throw "Service entry point not found: $serviceScript" }
    & $python $serviceScript --preflight
    if ($LASTEXITCODE -ne 0) { throw "API service preflight failed with exit code $LASTEXITCODE" }
}

switch ($Action) {
    'Preflight' { Invoke-ApiPreflight }
    'Status' {
        $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($service) { $service | Select-Object Name, Status, StartType, DisplayName }
        else { [pscustomobject]@{ Name = $ServiceName; Status = 'NotInstalled'; StartType = $null } }
    }
    'Install' {
        Assert-Administrator
        Invoke-ApiPreflight
        if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) { throw 'Service already exists; do not overwrite its configuration.' }
        $logRoot = Join-Path $env:LIBTV_API_DATA_ROOT 'var\logs'
        New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
        & $python $serviceScript --startup auto install
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        $registryPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName\Parameters"
        New-Item -Path $registryPath -Force | Out-Null
        New-ItemProperty -Path $registryPath -Name DataRoot -Value $env:LIBTV_API_DATA_ROOT -PropertyType String -Force | Out-Null
        & sc.exe config $ServiceName obj= $ServiceAccount password= ""
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/15000/restart/60000
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    'Start' {
        Assert-Administrator
        if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 8000 is already occupied; stop the verified foreground API first.' }
        Start-Service -Name $ServiceName
    }
    'Stop' { Assert-Administrator; Stop-Service -Name $ServiceName }
    'Restart' { Assert-Administrator; Restart-Service -Name $ServiceName }
    'Uninstall' {
        Assert-Administrator
        $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($service -and $service.Status -ne 'Stopped') { Stop-Service -Name $ServiceName }
        & $python $serviceScript remove
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}

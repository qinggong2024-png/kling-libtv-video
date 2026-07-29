param(
    [ValidateSet('Preflight', 'Install', 'Start', 'Stop', 'Restart', 'Uninstall', 'Status')]
    [string]$Action = 'Status',
    [ValidateSet('LibTVProductionRunner')]
    [string]$ServiceName = 'LibTVProductionRunner',
    [ValidateSet('NT SERVICE\LibTVProductionRunner')]
    [string]$ServiceAccount = 'NT SERVICE\LibTVProductionRunner'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$serviceScript = Join-Path $projectRoot 'backend\src\libtv_agent\runner\windows_service.py'
$runnerRoot = Join-Path $projectRoot 'var\runner'
$libtvConfigDir = Join-Path $projectRoot 'var\runtime\libtv'

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Administrator PowerShell is required. Re-run: powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Action $Action"
    }
}

function Invoke-RunnerPreflight {
    if (-not (Test-Path -LiteralPath $python)) { throw "Python environment not found: $python" }
    if (-not (Test-Path -LiteralPath $serviceScript)) { throw "Service entry point not found: $serviceScript" }
    & $python $serviceScript --preflight
    if ($LASTEXITCODE -ne 0) { throw "Runner preflight failed with exit code $LASTEXITCODE" }
}

switch ($Action) {
    'Preflight' {
        Invoke-RunnerPreflight
    }
    'Status' {
        $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($service) {
            $service | Select-Object Name, Status, StartType
        } else {
            [pscustomobject]@{ Name = $ServiceName; Status = 'NotInstalled'; StartType = $null }
        }
    }
    'Install' {
        Assert-Administrator
        $loginOperator = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        Invoke-RunnerPreflight
        New-Item -ItemType Directory -Force -Path $runnerRoot | Out-Null
        New-Item -ItemType Directory -Force -Path $libtvConfigDir | Out-Null
        & $python $serviceScript --startup auto install
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & sc.exe config $ServiceName obj= $ServiceAccount password= ""
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/15000/restart/60000
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & icacls.exe $runnerRoot /inheritance:r /grant:r "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" "${ServiceAccount}:(OI)(CI)M"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & icacls.exe $libtvConfigDir /inheritance:r /grant:r "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" "${ServiceAccount}:(OI)(CI)M" "${loginOperator}:(OI)(CI)F"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Get-Acl -LiteralPath $runnerRoot | Format-List Owner, AccessToString
        Get-Acl -LiteralPath $libtvConfigDir | Format-List Owner, AccessToString
    }
    'Start' { Assert-Administrator; Start-Service -Name $ServiceName }
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

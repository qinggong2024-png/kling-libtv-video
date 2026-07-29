[CmdletBinding()]
param(
    [string]$ConfigDir = '',
    [string]$ServiceName = 'LibTVProductionRunner',
    [switch]$RestartRunner
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $ConfigDir) {
    $ConfigDir = $env:LIBTV_CONFIG_DIR
    $dotenvPath = Join-Path $projectRoot '.env'
    if (-not $ConfigDir -and (Test-Path -LiteralPath $dotenvPath)) {
        $configLine = Get-Content -LiteralPath $dotenvPath |
            Where-Object { $_ -match '^\s*LIBTV_CONFIG_DIR\s*=' } |
            Select-Object -First 1
        if ($configLine) {
            $ConfigDir = ($configLine -split '=', 2)[1].Trim().Trim('"').Trim("'")
        }
    }
    if (-not $ConfigDir) {
        $ConfigDir = Join-Path $projectRoot 'var\runtime\libtv'
    }
}
if (-not [IO.Path]::IsPathRooted($ConfigDir)) {
    $ConfigDir = Join-Path $projectRoot $ConfigDir
}
$resolvedConfigDir = [IO.Path]::GetFullPath($ConfigDir)
New-Item -ItemType Directory -Force -Path $resolvedConfigDir | Out-Null
$env:LIBTV_CONFIG_DIR = $resolvedConfigDir

function Test-LibTVAccount {
    & libtv account info | Out-Host
    return $LASTEXITCODE -eq 0
}

Write-Host "Checking LibTV account with config directory: $resolvedConfigDir"
if (-not (Test-LibTVAccount)) {
    Write-Warning 'LibTV login is missing or expired. Opening the official browser login flow.'
    & libtv login web --open
    if ($LASTEXITCODE -ne 0) {
        throw "LibTV browser login failed with exit code $LASTEXITCODE"
    }
    if (-not (Test-LibTVAccount)) {
        throw 'LibTV login completed, but account verification still failed.'
    }
}

$runnerRestarted = $false
if ($RestartRunner) {
    $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($service) {
        Restart-Service -Name $ServiceName
        $runnerRestarted = $true
        Write-Host "Restarted Windows service: $ServiceName"
    } else {
        Write-Warning "Windows service is not installed: $ServiceName"
    }
}

[pscustomobject]@{
    status = 'AUTHENTICATED'
    configDir = $resolvedConfigDir
    runnerRestarted = $runnerRestarted
}

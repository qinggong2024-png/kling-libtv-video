param(
    [string]$ProjectRoot,
    [int]$ApiPort = 8000,
    [int]$FrontendPort = 5173,
    [string]$BaseAddress = '127.0.0.1',
    [string]$LanAddress
)

# Read-only readiness check for the small internal LAN deployment.
# This script never starts or stops processes, migrates the database, reads
# .env contents, or calls a generation provider.

$ErrorActionPreference = 'Stop'
if (-not $ProjectRoot) { $ProjectRoot = Split-Path -Parent $PSScriptRoot }
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path

$script:failed = 0

function Write-Check([string]$Name, [bool]$Passed, [string]$Detail) {
    $state = if ($Passed) { 'PASS' } else { 'FAIL' }
    $color = if ($Passed) { 'Green' } else { 'Red' }
    Write-Host ('[{0}] {1}: {2}' -f $state, $Name, $Detail) -ForegroundColor $color
    if (-not $Passed) { $script:failed++ }
}

function Test-Http([string]$Name, [string]$Uri) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 5
        Write-Check $Name ($response.StatusCode -eq 200) (
            '{0} returned HTTP {1}' -f $Uri, $response.StatusCode
        )
        return $response
    }
    catch {
        Write-Check $Name $false ('{0} failed: {1}' -f $Uri, $_.Exception.Message)
        return $null
    }
}

function Test-PathCheck([string]$RelativePath) {
    $path = Join-Path $ProjectRoot $RelativePath
    Write-Check ('file {0}' -f $RelativePath) (Test-Path -LiteralPath $path) $path
}

function Test-Port([string]$Name, [int]$Port) {
    try {
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop)
        if (-not $listeners) {
            Write-Check $Name $false ('no listener on TCP {0}' -f $Port)
            return
        }
        $owners = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
        Write-Check $Name $true ('TCP {0} listening; PID {1}' -f $Port, ($owners -join ', '))
    }
    catch {
        Write-Check $Name $false ('TCP {0} is not listening' -f $Port)
    }
}

Write-Host 'LibTV internal MVP readiness (read-only)'
Write-Host ('ProjectRoot: {0}' -f $ProjectRoot)

foreach ($required in @(
    'backend/src/libtv_agent',
    'frontend/index.html',
    'frontend/package.json',
    'pyproject.toml'
)) {
    Test-PathCheck $required
}

Test-Port 'api port' $ApiPort
Test-Port 'frontend port' $FrontendPort

$apiBase = 'http://{0}:{1}' -f $BaseAddress, $ApiPort
$frontendBase = 'http://{0}:{1}' -f $BaseAddress, $FrontendPort
$null = Test-Http 'api live' ($apiBase + '/api/v1/health/live')
$readyResponse = Test-Http 'api ready' ($apiBase + '/api/v1/health/ready')
$null = Test-Http 'frontend' ($frontendBase + '/')
$proxyResponse = Test-Http 'frontend api proxy' ($frontendBase + '/api/v1/health/ready')

if ($readyResponse) {
    try {
        $ready = $readyResponse.Content | ConvertFrom-Json
        $schema = [string]$ready.schemaVersion
        if (-not $schema) { $schema = 'reported' }
        Write-Host ('[INFO] API readiness payload: {0}' -f $schema)
    }
    catch {
        Write-Check 'api ready payload' $false 'response was not valid JSON'
    }
}

if ($proxyResponse) {
    Write-Host '[INFO] Frontend proxy is responding to the API readiness path.'
}

if ($LanAddress) {
    $lanResponse = Test-Http 'LAN frontend' ('http://{0}:{1}/' -f $LanAddress, $FrontendPort)
    if ($lanResponse) {
        Write-Host ('[INFO] LAN address is reachable: http://{0}:{1}' -f $LanAddress, $FrontendPort)
    }
}

if ($script:failed -gt 0) {
    Write-Host ('Internal MVP is NOT ready: {0} check(s) failed.' -f $script:failed) -ForegroundColor Red
    exit 1
}

Write-Host 'Internal MVP readiness checks passed.' -ForegroundColor Green
exit 0

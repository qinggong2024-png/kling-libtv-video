param(
    [string]$LanAddress,
    [int]$StartupTimeoutSeconds = 45
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $projectRoot 'var\runtime'
$secretPath = Join-Path $runtimeDir 'lan-session-secret.txt'
$startScript = Join-Path $PSScriptRoot 'start-local-stack.ps1'

function Get-PrimaryLanAddress {
    $configuration = Get-NetIPConfiguration |
        Where-Object { $_.NetAdapter.Status -eq 'Up' -and $null -ne $_.IPv4DefaultGateway } |
        Sort-Object { $_.NetAdapter.InterfaceMetric } |
        Select-Object -First 1
    if ($null -eq $configuration -or $null -eq $configuration.IPv4Address) {
        throw 'No active IPv4 network with a default gateway was found. Pass -LanAddress explicitly.'
    }
    return @($configuration.IPv4Address)[0].IPAddress
}

function Test-IPv4Address([string]$Value) {
    $parsed = $null
    return [Net.IPAddress]::TryParse($Value, [ref]$parsed) -and
        $parsed.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork -and
        -not [Net.IPAddress]::IsLoopback($parsed)
}

if (-not $LanAddress) { $LanAddress = Get-PrimaryLanAddress }
if (-not (Test-IPv4Address $LanAddress)) {
    throw "LanAddress must be a non-loopback IPv4 address: $LanAddress"
}

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
if (-not (Test-Path -LiteralPath $secretPath)) {
    $bytes = New-Object byte[] 48
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    [Convert]::ToBase64String($bytes) | Set-Content -Encoding utf8 -NoNewline -LiteralPath $secretPath
}
$sessionSecret = (Get-Content -Raw -LiteralPath $secretPath).Trim()
if ($sessionSecret.Length -lt 32) { throw "LAN session secret is invalid: $secretPath" }

$env:SHARED_AUTHENTICATION_ENABLED = 'true'
$env:SESSION_COOKIE_SECURE = 'false'
$env:SESSION_SECRET = $sessionSecret
$env:APP_PUBLIC_ORIGINS = "http://$LanAddress`:5173,http://127.0.0.1:5173,http://localhost:5173"
$env:VITE_API_PROXY = 'http://127.0.0.1:8000'
$env:VITE_HOST = '0.0.0.0'

& $startScript -StartupTimeoutSeconds $StartupTimeoutSeconds
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$status = Invoke-RestMethod -Uri 'http://127.0.0.1:5173/api/v1/system/status' -TimeoutSec 5
if (-not $status.sharedAuthentication) {
    throw 'The running API did not enable shared authentication. Stop the existing API and run this script again.'
}

$profile = Get-NetConnectionProfile -ErrorAction SilentlyContinue |
    Where-Object { $_.IPv4Connectivity -ne 'Disconnected' -and $_.InterfaceAlias -notlike '*Tailscale*' } |
    Select-Object -First 1

Write-Host ''
Write-Host 'LibTV production workspace is ready for other devices.' -ForegroundColor Green
Write-Host "Open on this computer: http://127.0.0.1:5173"
Write-Host "Open on another device: http://$LanAddress`:5173" -ForegroundColor Cyan
Write-Host 'Keep this computer awake and connected to the same network.'
if ($profile -and $profile.NetworkCategory -eq 'Public') {
    Write-Warning "The '$($profile.Name)' network is Public. Windows Firewall may block other devices. Change a trusted LAN to Private or allow inbound TCP 5173 for node.exe."
}

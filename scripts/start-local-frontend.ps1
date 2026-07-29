$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $projectRoot 'var\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Location $projectRoot

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw 'npm.cmd was not found on PATH. Install Node.js before starting the frontend.'
}
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\node_modules'))) {
    throw "Frontend dependencies are missing. Run 'npm.cmd install --prefix frontend' first."
}

$frontendPort = 5173
$existingListener = Get-NetTCPConnection -State Listen -LocalPort $frontendPort -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($existingListener) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$frontendPort/" -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            Write-Host "Frontend is already available on http://127.0.0.1:$frontendPort (PID $($existingListener.OwningProcess))."
            exit 0
        }
    }
    catch { }
    throw "Port $frontendPort is already owned by PID $($existingListener.OwningProcess), but the frontend check failed."
}

& cmd.exe /d /c "npm.cmd run build --prefix frontend 2>&1" |
    Tee-Object -FilePath (Join-Path $logDir 'frontend.preflight.log')
$preflightExitCode = $LASTEXITCODE
if ($preflightExitCode -ne 0) {
    throw 'Frontend type-check or build preflight failed. See var/logs/frontend.preflight.log.'
}

& cmd.exe /d /c "npm.cmd run dev --prefix frontend 2>&1" |
    Tee-Object -FilePath (Join-Path $logDir 'frontend.autostart.log')
$frontendExitCode = $LASTEXITCODE
if ($frontendExitCode -ne 0) {
    throw "Frontend stopped with exit code $frontendExitCode. See var/logs/frontend.autostart.log."
}

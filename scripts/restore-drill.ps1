param(
    [Parameter(Mandatory = $true)]
    [string]$BackupDirectory,
    [string]$ComposeProjectName = "libtv-restore-drill-$PID",
    [int]$PostgresPort = 55432,
    [int]$MinioPort = 59000,
    [int]$MinioConsolePort = 59001
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$backupPath = [IO.Path]::GetFullPath($BackupDirectory)
$drillBase = [IO.Path]::GetFullPath((Join-Path $projectRoot 'var\restore-drills'))
if ($ComposeProjectName -notmatch '^libtv-restore-drill-[A-Za-z0-9_-]+$') {
    throw 'ComposeProjectName must start with libtv-restore-drill-'
}
if (-not (Test-Path -LiteralPath (Join-Path $backupPath 'manifest.json'))) {
    throw 'backup manifest is missing'
}
New-Item -ItemType Directory -Force -Path $drillBase | Out-Null
$drillRoot = [IO.Path]::GetFullPath((Join-Path $drillBase $ComposeProjectName))
if (-not $drillRoot.StartsWith($drillBase + [IO.Path]::DirectorySeparatorChar)) {
    throw 'restore drill path escaped the isolated drill root'
}
New-Item -ItemType Directory -Force -Path $drillRoot | Out-Null
$reportRoot = Join-Path $projectRoot 'var\reports'
New-Item -ItemType Directory -Force -Path $reportRoot | Out-Null
$reportPath = Join-Path $reportRoot 'restore-drill.json'
$startedAt = [DateTimeOffset]::UtcNow
$checks = [ordered]@{}
$composeAttempted = $false

try {
    $manifest = Get-Content -Raw -LiteralPath (Join-Path $backupPath 'manifest.json') | ConvertFrom-Json
    foreach ($file in @($manifest.files)) {
        $path = [IO.Path]::GetFullPath((Join-Path $backupPath ([string]$file.path)))
        if (-not $path.StartsWith($backupPath + [IO.Path]::DirectorySeparatorChar)) { throw 'manifest path escapes backup root' }
        if (-not (Test-Path -LiteralPath $path)) { throw "backup file missing: $($file.path)" }
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
        if ($hash -ne [string]$file.sha256) { throw "backup hash mismatch: $($file.path)" }
    }
    $checks.backupIntegrity = [ordered]@{ status = 'PASS'; fileCount = @($manifest.files).Count }
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $serverVersion = (& docker info --format '{{.ServerVersion}}' 2>$null | Out-String).Trim() }
    catch { $serverVersion = '' }
    finally { $ErrorActionPreference = $previousErrorPreference }
    if ($LASTEXITCODE -ne 0 -or -not $serverVersion) {
        $checks.docker = [ordered]@{ status = 'BLOCKED'; reason = 'Docker Engine unavailable' }
        throw 'Docker Engine unavailable'
    }
    $checks.docker = [ordered]@{ status = 'PASS'; serverVersion = $serverVersion }

    $env:POSTGRES_DB = 'libtv_restore_drill'
    $env:POSTGRES_USER = 'libtv_restore_drill'
    $env:POSTGRES_PASSWORD = "restore-$([guid]::NewGuid().ToString('N'))"
    $env:POSTGRES_PORT = [string]$PostgresPort
    $env:POSTGRES_BIND_ADDRESS = '127.0.0.1'
    $env:MINIO_ROOT_USER = 'restore_drill'
    $env:MINIO_ROOT_PASSWORD = "restore-$([guid]::NewGuid().ToString('N'))"
    $env:MINIO_BUCKET = [string]$manifest.minio.bucket
    $env:MINIO_PORT = [string]$MinioPort
    $env:MINIO_CONSOLE_PORT = [string]$MinioConsolePort
    $env:MINIO_BIND_ADDRESS = '127.0.0.1'
    $env:MINIO_DATA_DIR = (Join-Path $drillRoot 'minio-data')
    $env:OBJECT_STORE_PREFIX = "restore-drill/$ComposeProjectName"
    $env:LIBTV_ADAPTER_MODE = 'fake'
    $env:AI_ADAPTER_MODE = 'fake'
    $env:PAID_SUBMISSIONS_PAUSED = 'true'
    $compose = @('compose', '--project-name', $ComposeProjectName, '-f', (Join-Path $projectRoot 'infra\compose.yaml'))
    $composeAttempted = $true
    & docker @compose up -d --wait postgres minio
    if ($LASTEXITCODE -ne 0) { throw 'isolated restore Compose startup failed' }
    & docker @compose run --rm minio-init
    if ($LASTEXITCODE -ne 0) { throw 'isolated restore MinIO initialization failed' }
    $checks.isolation = [ordered]@{
        status = 'PASS'; composeProject = $ComposeProjectName; paidSubmissionsPaused = $true
        libtvAdapterMode = 'fake'; objectPrefix = $env:OBJECT_STORE_PREFIX
    }

    $dumpPath = Join-Path $backupPath ([string]$manifest.database.file)
    & docker @compose cp $dumpPath 'postgres:/tmp/libtv-restore.dump'
    if ($LASTEXITCODE -ne 0) { throw 'copying database dump into drill failed' }
    & docker @compose exec -T postgres pg_restore --clean --if-exists --no-owner --no-privileges --username $env:POSTGRES_USER --dbname $env:POSTGRES_DB /tmp/libtv-restore.dump
    if ($LASTEXITCODE -ne 0) { throw 'pg_restore failed' }
    $checks.postgresqlRestore = [ordered]@{ status = 'PASS'; dumpSha256 = [string]$manifest.database.sha256 }

    $minioBackup = Join-Path $backupPath ([string]$manifest.minio.directory)
    $network = "${ComposeProjectName}_default"
    $bucket = [string]$manifest.minio.bucket
    if ($bucket -notmatch '^[a-z0-9][a-z0-9.-]+[a-z0-9]$') { throw 'backup MINIO bucket is invalid' }
    $mirrorCommand = 'mc alias set target http://minio:9000 "$MC_USER" "$MC_PASSWORD" >/dev/null && mc mirror --overwrite /backup "target/{BUCKET}"'.Replace('{BUCKET}', $bucket)
    & docker run --rm --network $network --entrypoint /bin/sh `
        -e "MC_USER=$($env:MINIO_ROOT_USER)" -e "MC_PASSWORD=$($env:MINIO_ROOT_PASSWORD)" `
        -v "${minioBackup}:/backup:ro" minio/mc -c `
        $mirrorCommand
    if ($LASTEXITCODE -ne 0) { throw 'MinIO restore failed' }
    $checks.minioRestore = [ordered]@{ status = 'PASS'; expectedObjectFiles = [int]$manifest.minio.objectFiles }

    $env:DATABASE_URL = "postgresql+asyncpg://$($env:POSTGRES_USER):$($env:POSTGRES_PASSWORD)@127.0.0.1:$PostgresPort/$($env:POSTGRES_DB)"
    $env:MINIO_ENDPOINT = "127.0.0.1:$MinioPort"
    $env:MINIO_ACCESS_KEY = $env:MINIO_ROOT_USER
    $env:MINIO_SECRET_KEY = $env:MINIO_ROOT_PASSWORD
    $env:MINIO_SECURE = 'false'
    Push-Location $projectRoot
    try { & uv run alembic -c backend/alembic.ini upgrade head }
    finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw 'Alembic verification failed after restore' }
    $verificationPath = Join-Path $drillRoot 'verification.json'
    Push-Location $projectRoot
    try { & uv run python scripts/verify_restore.py --expected-object-count ([int]$manifest.minio.objectFiles) --output $verificationPath }
    finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw 'independent restored data verification failed' }
    $checks.independentVerification = Get-Content -Raw -LiteralPath $verificationPath | ConvertFrom-Json
}
catch {
    if (-not $checks.error) { $checks.error = [ordered]@{ message = $_.Exception.Message } }
}
finally {
    if ($composeAttempted) {
        & docker compose --project-name $ComposeProjectName -f (Join-Path $projectRoot 'infra\compose.yaml') down --volumes | Out-Null
    }
    $statuses = @($checks.Values | Where-Object { $_ -is [System.Collections.IDictionary] -and $_.Contains('status') } | ForEach-Object { $_.status })
    $status = if ($statuses -contains 'FAIL') { 'FAIL' } elseif ($statuses -contains 'BLOCKED') { 'BLOCKED' } elseif ($checks.error) { 'FAIL' } elseif ($statuses -and @($statuses | Where-Object { $_ -ne 'PASS' }).Count -eq 0) { 'PASS' } else { 'INCOMPLETE' }
    $report = [ordered]@{
        schemaVersion = '1.0'; status = $status; startedAt = $startedAt.ToString('o')
        completedAt = [DateTimeOffset]::UtcNow.ToString('o'); independent = $true
        paidOperationsExecuted = $false; checks = $checks
    }
    $report | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 -LiteralPath $reportPath
    $report | ConvertTo-Json -Depth 8
    if ($status -ne 'PASS') { exit 1 }
}

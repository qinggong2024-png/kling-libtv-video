param(
    [ValidateSet('development', 'staging', 'production')]
    [string]$Environment = 'development',
    [string]$ComposeProjectName = 'libtv-production-agent',
    [string]$Destination
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot ".env.$Environment"
if (-not $Destination) {
    $Destination = Join-Path $projectRoot "var\backups\$Environment-$([DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssZ'))"
}
$destinationPath = [IO.Path]::GetFullPath($Destination)
New-Item -ItemType Directory -Force -Path $destinationPath | Out-Null

function Import-Environment([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { throw "Missing environment file: $Path" }
    Get-Content -LiteralPath $Path | ForEach-Object {
        if ($_ -match '^\s*([^#][A-Za-z0-9_]*)=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
        }
    }
}

Import-Environment $envFile
$previousErrorPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try { $serverVersion = (& docker info --format '{{.ServerVersion}}' 2>$null | Out-String).Trim() }
catch { $serverVersion = '' }
finally { $ErrorActionPreference = $previousErrorPreference }
if ($LASTEXITCODE -ne 0 -or -not $serverVersion) { throw 'Docker Engine unavailable' }
$compose = @('compose', '--project-name', $ComposeProjectName, '--env-file', $envFile, '-f', (Join-Path $projectRoot 'infra\compose.yaml'))
$dumpName = 'postgres.dump'
$dumpPath = Join-Path $destinationPath $dumpName
& docker @compose exec -T postgres pg_dump --format=custom --file=/tmp/libtv-phase2.dump --username $env:POSTGRES_USER $env:POSTGRES_DB
if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed' }
try {
    & docker @compose cp 'postgres:/tmp/libtv-phase2.dump' $dumpPath
    if ($LASTEXITCODE -ne 0) { throw 'copying PostgreSQL dump failed' }
}
finally {
    & docker @compose exec -T postgres rm -f /tmp/libtv-phase2.dump | Out-Null
}

$minioPath = Join-Path $destinationPath 'minio'
New-Item -ItemType Directory -Force -Path $minioPath | Out-Null
$network = "${ComposeProjectName}_default"
$bucket = if ($env:MINIO_BUCKET) { $env:MINIO_BUCKET } else { 'libtv-agent' }
if ($bucket -notmatch '^[a-z0-9][a-z0-9.-]+[a-z0-9]$') { throw 'MINIO_BUCKET is invalid' }
$mirrorCommand = 'mc alias set source http://minio:9000 "$MC_USER" "$MC_PASSWORD" >/dev/null && mc mirror --overwrite "source/{BUCKET}" /backup'.Replace('{BUCKET}', $bucket)
& docker run --rm --network $network --entrypoint /bin/sh `
    -e "MC_USER=$($env:MINIO_ROOT_USER)" -e "MC_PASSWORD=$($env:MINIO_ROOT_PASSWORD)" `
    -v "${minioPath}:/backup" minio/mc -c `
    $mirrorCommand
if ($LASTEXITCODE -ne 0) { throw 'MinIO logical backup failed' }

$files = Get-ChildItem -Recurse -File -LiteralPath $destinationPath | Where-Object { $_.Name -ne 'manifest.json' }
$destinationPrefix = $destinationPath.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$manifest = [ordered]@{
    schemaVersion = '1.0'
    environment = $Environment
    createdAt = [DateTimeOffset]::UtcNow.ToString('o')
    dockerServerVersion = $serverVersion
    secretValuesIncluded = $false
    database = [ordered]@{ file = $dumpName; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $dumpPath).Hash.ToLowerInvariant() }
    minio = [ordered]@{ directory = 'minio'; bucket = $bucket; objectFiles = @($files | Where-Object { $_.FullName.StartsWith($minioPath) }).Count }
    files = @($files | ForEach-Object {
        if (-not $_.FullName.StartsWith($destinationPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "backup file escaped destination: $($_.FullName)"
        }
        [ordered]@{
            path = $_.FullName.Substring($destinationPrefix.Length).Replace('\', '/')
            size = $_.Length
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
        }
    })
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 -LiteralPath (Join-Path $destinationPath 'manifest.json')
$manifest | ConvertTo-Json -Depth 8

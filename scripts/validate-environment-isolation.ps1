param([switch]$UseLocalFiles)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$names = @('development', 'staging', 'production')
$records = @()

function Read-DotEnv([string]$Path) {
    $values = @{}
    Get-Content -LiteralPath $Path | ForEach-Object {
        if ($_ -match '^\s*([^#][A-Za-z0-9_]*)=(.*)$') {
            $values[$Matches[1]] = $Matches[2].Trim()
        }
    }
    return $values
}

foreach ($name in $names) {
    $suffix = if ($UseLocalFiles) { '' } else { '.example' }
    $path = Join-Path $projectRoot ".env.$name$suffix"
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing environment file: $path" }
    $values = Read-DotEnv $path
    if ($values.APP_ENV -ne $name) { throw "$path APP_ENV must be $name" }
    if ($values.OBJECT_STORE_PREFIX -ne $name) {
        throw "$path OBJECT_STORE_PREFIX must be $name"
    }
    if ($values.AUTO_CONFIRM_LEVELS -ne 'PASS') {
        throw "$path must only allow PASS automatic confirmation"
    }
    if ($values.PAID_SUBMISSIONS_PAUSED -ne 'true') {
        throw "$path must default paid submissions to paused"
    }
    if ($UseLocalFiles -and ((Get-Content -Raw -LiteralPath $path) -match 'replace-with-|change-me-before-shared-use')) {
        throw "$path contains a placeholder"
    }
    $records += [pscustomobject]@{
        environment = $name
        databaseUrl = $values.DATABASE_URL
        objectPrefix = $values.OBJECT_STORE_PREFIX
        deploymentId = $values.DEPLOYMENT_ID
        workspaceId = $values.LIBTV_WORKSPACE_ID
        projectUuid = $values.LIBTV_PROJECT_UUID
        postgresPort = $values.POSTGRES_PORT
        minioPort = $values.MINIO_PORT
        secretFingerprint = if ($UseLocalFiles) {
            $bytes = [Text.Encoding]::UTF8.GetBytes("$($values.POSTGRES_PASSWORD)|$($values.MINIO_SECRET_KEY)|$($values.SESSION_SECRET)")
            $sha = [Security.Cryptography.SHA256]::Create()
            try { $hash = $sha.ComputeHash($bytes) } finally { $sha.Dispose() }
            (([BitConverter]::ToString($hash) -replace '-', '').Substring(0, 12)).ToLowerInvariant()
        } else { 'template' }
    }
}

foreach ($field in @('databaseUrl', 'objectPrefix', 'deploymentId', 'workspaceId', 'projectUuid', 'postgresPort', 'minioPort')) {
    $unique = @($records.$field | Sort-Object -Unique)
    if ($unique.Count -ne $names.Count) { throw "$field is not isolated across all environments" }
}
if ($UseLocalFiles -and (@($records.secretFingerprint | Sort-Object -Unique).Count -ne $names.Count)) {
    throw 'Environment secrets are not isolated'
}

[pscustomobject]@{
    status = 'PASS'
    checkedAt = [DateTimeOffset]::UtcNow.ToString('o')
    environments = @($records | ForEach-Object {
        [pscustomobject]@{
            environment = $_.environment
            objectPrefix = $_.objectPrefix
            deploymentId = $_.deploymentId
            postgresPort = $_.postgresPort
            minioPort = $_.minioPort
            secrets = if ($UseLocalFiles) { "isolated:$($_.secretFingerprint)" } else { 'not-evaluated-template' }
        }
    })
} | ConvertTo-Json -Depth 5

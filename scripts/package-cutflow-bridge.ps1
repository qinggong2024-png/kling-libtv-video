param(
    [Parameter(Mandatory = $true)]
    [string]$SourceRoot,
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,
    [Parameter(Mandatory = $true)]
    [string]$PatchPath
)

$ErrorActionPreference = 'Stop'
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
$PatchPath = (Resolve-Path -LiteralPath $PatchPath).Path
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$instructionPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'docs\CUTFLOW_ONE_MESSAGE_DEPLOYMENT.md'
$acceptancePath = Join-Path (Split-Path -Parent $PSScriptRoot) 'docs\REAL_CUTFLOW_LAN_DEPLOYMENT_RESULT.md'

$payloadPaths = @(
    'lib/libtv-bridge.mjs',
    'lib/libtv-bridge.d.mts',
    'app/api/integrations/libtv/route.ts',
    'app/api/integrations/libtv/[handoffId]/route.ts',
    'worker/libtv-bridge-worker.mjs',
    'tests/libtv-bridge.test.mjs',
    'tests/tsconfig.libtv-bridge.json',
    'docs/LIBTV_BRIDGE.md'
)
$dependencyPaths = @(
    'lib/atomic-json.mjs',
    'lib/tenant-paths.mjs',
    'lib/task-number.mjs'
)

if (Test-Path -LiteralPath $OutputDirectory) {
    throw 'Output directory already exists. Preserve it and choose a new directory.'
}
foreach ($relative in @($payloadPaths + $dependencyPaths)) {
    if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot $relative) -PathType Leaf)) {
        throw "Missing source file: $relative"
    }
}
foreach ($document in @($instructionPath, $acceptancePath)) {
    if (-not (Test-Path -LiteralPath $document -PathType Leaf)) {
        throw 'Required deployment documentation is missing.'
    }
}
$sourceHead = & git -C $SourceRoot rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Cannot identify Cutflow source baseline.' }

$null = New-Item -Path $OutputDirectory -ItemType Directory
$manifestFiles = @()
foreach ($relative in $payloadPaths) {
    $source = Join-Path $SourceRoot $relative
    $destination = Join-Path (Join-Path $OutputDirectory 'payload') $relative
    $null = New-Item -Path (Split-Path -Parent $destination) -ItemType Directory -Force
    Copy-Item -LiteralPath $source -Destination $destination
    $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    if ($sourceHash -ne (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash) {
        throw "Package copy verification failed: $relative"
    }
    $manifestFiles += [ordered]@{
        path = $relative
        sha256 = $sourceHash
        bytes = (Get-Item -LiteralPath $source).Length
    }
}

Copy-Item -LiteralPath $PatchPath -Destination (Join-Path $OutputDirectory 'cutflow-libtv-bridge.patch')
Copy-Item -LiteralPath $instructionPath -Destination (Join-Path $OutputDirectory 'CUTFLOW_ONE_MESSAGE_DEPLOYMENT.md')
Copy-Item -LiteralPath $acceptancePath -Destination (Join-Path $OutputDirectory 'REAL_CUTFLOW_LAN_DEPLOYMENT_RESULT.md')
$dependencies = @($dependencyPaths | ForEach-Object {
    [ordered]@{
        path = $_
        sha256 = (Get-FileHash -LiteralPath (Join-Path $SourceRoot $_) -Algorithm SHA256).Hash
    }
})
$manifest = [ordered]@{
    schemaVersion = 'cutflow-bridge-deployment/1'
    createdAt = [DateTimeOffset]::Now.ToString('o')
    sourceHead = $sourceHead.Trim()
    deploymentStatus = 'PREPARED_NOT_INSTALLED'
    files = $manifestFiles
    sourceDependencies = $dependencies
    patchSha256 = (Get-FileHash -LiteralPath $PatchPath -Algorithm SHA256).Hash
    notes = @(
        'Contains existing Bridge source and deployment instructions only.',
        'Dependency hashes describe the reviewed baseline; compare remote differences.',
        'No secrets, environment files, accounts, runtime state, or media are included.',
        'Do not copy the payload blindly over differing remote files.',
        'This command does not install, configure, restart, migrate, or submit jobs.'
    )
}
$encoding = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText(
    (Join-Path $OutputDirectory 'manifest.json'),
    ($manifest | ConvertTo-Json -Depth 8),
    $encoding
)
Write-Output ([pscustomobject]@{
    status = 'PREPARED_NOT_INSTALLED'
    packageDirectory = $OutputDirectory
    payloadFiles = $payloadPaths.Count
    manifestSha256 = (Get-FileHash -LiteralPath (Join-Path $OutputDirectory 'manifest.json') -Algorithm SHA256).Hash
} | ConvertTo-Json -Compress)

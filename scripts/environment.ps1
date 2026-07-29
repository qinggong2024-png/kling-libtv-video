param(
    [Parameter(Mandatory)]
    [ValidateSet('development', 'staging', 'production')]
    [string]$Environment,
    [Parameter(Mandatory)]
    [ValidateSet('Up', 'Down', 'Migrate', 'Status')]
    [string]$Action
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot ".env.$Environment"
$example = "$envFile.example"
$compose = Join-Path $projectRoot 'infra\compose.yaml'
$projectName = "libtv-agent-$Environment"

if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Missing $envFile. Create it locally from $example and replace every placeholder; do not commit it."
}
$content = Get-Content -Raw -LiteralPath $envFile
if ($content -match 'replace-with-|change-me-before-shared-use') {
    throw "$envFile still contains a placeholder secret or identifier"
}

function Invoke-Compose([string[]]$Arguments) {
    & docker compose --project-name $projectName --env-file $envFile -f $compose @Arguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

switch ($Action) {
    'Up' { Invoke-Compose @('up', '-d') }
    'Down' { Invoke-Compose @('down') }
    'Status' { Invoke-Compose @('ps') }
    'Migrate' {
        Get-Content -LiteralPath $envFile | ForEach-Object {
            if ($_ -match '^\s*([^#][A-Za-z0-9_]*)=(.*)$') {
                [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
            }
        }
        Push-Location $projectRoot
        try {
            & uv run alembic -c backend/alembic.ini upgrade head
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
        finally { Pop-Location }
    }
}

param([string]$ModelKey = 'kling-v3-omni')

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$evidenceRoot = Join-Path $projectRoot 'var\evidence\libtv-readonly'
$reportRoot = Join-Path $projectRoot 'var\reports'
New-Item -ItemType Directory -Force -Path $evidenceRoot, $reportRoot | Out-Null
$reportPath = Join-Path $reportRoot 'libtv-readonly-canary.json'
$startedAt = [DateTimeOffset]::UtcNow
$invocations = @()

function Get-HashPrefix([string]$Value) {
    if (-not $Value) { return $null }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $bytes = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)) }
    finally { $sha.Dispose() }
    return (([BitConverter]::ToString($bytes) -replace '-', '').Substring(0, 12)).ToLowerInvariant()
}

function Get-ProhibitedOperationEvidence {
    $commands = @($script:invocations | ForEach-Object { [string]$_.command })
    $nodeCreates = @($commands | Where-Object { $_ -match '^libtv node (?:create|add)\b|^libtv node .*\s--create(?:\s|$)' }).Count
    $uploads = @($commands | Where-Object { $_ -match '^libtv .*\bupload\b' }).Count
    $nodeRuns = @($commands | Where-Object { $_ -match '^libtv node .*\s--run(?:\s|$)' }).Count
    $unapproved = @($commands | Where-Object {
        $_ -notmatch '^libtv --version$' -and
        $_ -notmatch '^libtv account (?:info|list)(?:\s|$)' -and
        $_ -notmatch '^libtv workspace list(?:\s|$)' -and
        $_ -notmatch '^libtv project list(?:\s|$)' -and
        $_ -notmatch '^libtv model (?:search\s|[A-Za-z0-9._-]+$)'
    })
    return [ordered]@{
        nodesCreated = $nodeCreates
        uploads = $uploads
        nodeRuns = $nodeRuns
        paidOperations = $unapproved.Count
        unapprovedCommandCount = $unapproved.Count
        evidenceSource = 'invocations'
    }
}

function Invoke-LibTVJson([string]$Name, [string[]]$Arguments, [bool]$RetainSchema = $false) {
    $stdoutPath = Join-Path $evidenceRoot "$Name.stdout.json"
    $stderrPath = Join-Path $evidenceRoot "$Name.stderr.log"
    $watch = [Diagnostics.Stopwatch]::StartNew()
    & libtv @Arguments 1> $stdoutPath 2> $stderrPath
    $exitCode = $LASTEXITCODE
    $watch.Stop()
    $script:invocations += [pscustomobject]@{
        command = "libtv $($Arguments -join ' ')"
        exitCode = $exitCode
        durationMs = $watch.ElapsedMilliseconds
    }
    if ($exitCode -ne 0) {
        $message = if (Test-Path $stderrPath) { Get-Content -Raw -LiteralPath $stderrPath } else { 'unknown CLI error' }
        $message = $message -replace 'sk-[A-Za-z0-9_-]+', '[REDACTED]' -replace '[A-Za-z0-9_-]{24,}', '[REDACTED]'
        Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $stdoutPath, $stderrPath
        throw "$Name failed: $message"
    }
    $data = Get-Content -Raw -LiteralPath $stdoutPath | ConvertFrom-Json
    Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $stderrPath
    if (-not $RetainSchema) {
        [IO.File]::Delete($stdoutPath)
    }
    return $data
}

try {
    $versionText = (& libtv --version).Trim()
    $script:invocations += [pscustomobject]@{ command = 'libtv --version'; exitCode = $LASTEXITCODE; durationMs = $null }
    if ($LASTEXITCODE -ne 0) { throw 'libtv --version failed' }
    $cliCompatible = $versionText -eq '1.1.1'
    $accountInfo = Invoke-LibTVJson 'account-info' @('account', 'info')
    $accountList = Invoke-LibTVJson 'account-list' @('account', 'list')
    $workspaces = Invoke-LibTVJson 'workspace-list' @('workspace', 'list', '--page', '1', '--page-size', '20')
    $projects = Invoke-LibTVJson 'project-list' @('project', 'list', '--page', '1', '--page-size', '20')
    $modelSearch = Invoke-LibTVJson 'model-search' @('model', 'search', '--type', 'video', $ModelKey) $true
    $model = Invoke-LibTVJson 'model-schema' @('model', $ModelKey) $true

    $accountJson = $accountInfo | ConvertTo-Json -Depth 20 -Compress
    $balanceFieldPresent = $accountJson -match '(?i)"[^\"]*(balance|points|credit)[^\"]*"\s*:'
    $activeAccount = $accountInfo.activeAccount
    $accountId = if ($activeAccount.accountId) { [string]$activeAccount.accountId } else { [string]$accountInfo.user.id }
    $teamId = [string]$accountInfo.teamId
    $workspaceCount = @($workspaces.folders).Count
    $projectItems = if ($projects.projectMetaList) { @($projects.projectMetaList) } elseif ($projects.projects) { @($projects.projects) } elseif ($projects.list) { @($projects.list) } elseif ($projects.data) { @($projects.data) } else { @() }
    $properties = $model.schema.properties
    $modeItems = $properties.modeType.items
    $quality = if ($properties.quality_4k) { $properties.quality_4k } else { $properties.quality }
    $qualityValues = @($quality.enum | ForEach-Object { if ($_ -is [string]) { $_ } else { $_.value } })
    $soundValues = @($properties.enableSound.enum | ForEach-Object { if ($_ -is [string]) { $_ } else { $_.value } })
    $duration = $properties.duration
    $compatible = (
        $model.modelKey -eq $ModelKey -and
        $model.modality -eq 'video' -and
        [int]$modeItems.singleImage2video[1] -ge 1 -and
        [int]$modeItems.mixed2video[1] -ge 7 -and
        @($properties.ratio.enum) -contains '9:16' -and
        [int]$duration.min -le 10 -and [int]$duration.max -ge 10 -and
        $qualityValues -contains 'high' -and
        $soundValues -contains 'off' -and
        [int]$properties.prompt.maxLength -ge 2000
    )
    $prohibitedEvidence = Get-ProhibitedOperationEvidence
    $canaryPassed = $cliCompatible -and $compatible -and $prohibitedEvidence.paidOperations -eq 0
    $schemaBytes = [IO.File]::ReadAllBytes((Join-Path $evidenceRoot 'model-schema.stdout.json'))
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $schemaHash = $sha.ComputeHash($schemaBytes) } finally { $sha.Dispose() }
    $schemaFingerprint = (([BitConverter]::ToString($schemaHash) -replace '-', '').Substring(0, 16)).ToLowerInvariant()

    $report = [ordered]@{
        schemaVersion = '1.0'
        status = if ($canaryPassed -and $balanceFieldPresent) { 'PASS' } elseif ($canaryPassed) { 'PASS_WITH_LIMITATION' } else { 'FAIL' }
        canaryType = 'READ_ONLY'
        startedAt = $startedAt.ToString('o')
        completedAt = [DateTimeOffset]::UtcNow.ToString('o')
        cli = [ordered]@{ version = $versionText; expected = '1.1.1'; compatible = $cliCompatible }
        account = [ordered]@{
            readable = $true
            accountCount = @($accountList.accounts).Count
            activeAccountType = [string]$activeAccount.accountType
            accountIdHash = Get-HashPrefix $accountId
            teamIdHash = Get-HashPrefix $teamId
            rawIdentityRetained = $false
        }
        balance = [ordered]@{
            readable = $balanceFieldPresent
            limitation = if ($balanceFieldPresent) { $null } else { 'libtv CLI 1.1.1 exposes no balance command or balance field in account info' }
        }
        scope = [ordered]@{ workspaceListReadable = $true; firstPageWorkspaceCount = $workspaceCount; projectListReadable = $true; firstPageProjectCount = $projectItems.Count }
        modelRegistry = [ordered]@{
            searchMatchCount = @($modelSearch.matches).Count
            modelKey = $model.modelKey
            modality = $model.modality
            schemaFingerprint = $schemaFingerprint
            compatibleWithDefault10s9x16 = $compatible
            maxMixedReferences = [int]$modeItems.mixed2video[1]
            promptMaxLength = [int]$properties.prompt.maxLength
        }
        prohibitedOperations = $prohibitedEvidence
        invocations = $invocations
    }
    $report | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 -LiteralPath $reportPath
    $report | ConvertTo-Json -Depth 8
    if (-not $canaryPassed) { exit 1 }
}
catch {
    $report = [ordered]@{
        schemaVersion = '1.0'
        status = 'BLOCKED'
        canaryType = 'READ_ONLY'
        startedAt = $startedAt.ToString('o')
        completedAt = [DateTimeOffset]::UtcNow.ToString('o')
        error = $_.Exception.Message
        prohibitedOperations = Get-ProhibitedOperationEvidence
        invocations = $invocations
    }
    $report | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 -LiteralPath $reportPath
    $report | ConvertTo-Json -Depth 8
    exit 1
}

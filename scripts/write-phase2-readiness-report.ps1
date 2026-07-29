param(
    [ValidateSet('development', 'staging', 'production')]
    [string]$Environment = 'development'
)

$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$reportRoot = Join-Path $projectRoot 'var\reports'
New-Item -ItemType Directory -Force -Path $reportRoot | Out-Null

function Read-JsonReport([string]$Name) {
    $path = Join-Path $reportRoot $Name
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    try { return Get-Content -Raw -LiteralPath $path | ConvertFrom-Json }
    catch { return [pscustomobject]@{ status = 'INVALID'; error = $_.Exception.Message } }
}

function Import-Environment([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    Get-Content -LiteralPath $Path | ForEach-Object {
        if ($_ -match '^\s*([^#][A-Za-z0-9_]*)=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
        }
    }
    return $true
}

function Metric-Status([object]$Value, [string]$Rule, [double]$Threshold) {
    if ($null -eq $Value) { return 'NOT_RUN' }
    $number = [double]$Value
    $pass = switch ($Rule) {
        'EQ' { $number -eq $Threshold }
        'GE' { $number -ge $Threshold }
        'LE' { $number -le $Threshold }
        'LT' { $number -lt $Threshold }
    }
    return if ($pass) { 'PASS' } else { 'FAIL' }
}

$envFile = Join-Path $projectRoot ".env.$Environment"
$environmentLoaded = Import-Environment $envFile
$phaseEvidencePath = Join-Path $reportRoot 'phase2-machine-evidence.json'
Push-Location $projectRoot
try { & uv run python scripts/collect_phase2_evidence.py --output $phaseEvidencePath | Out-Null }
finally { Pop-Location }
$collectorExitCode = $LASTEXITCODE

$check = Read-JsonReport 'check.json'
$online = Read-JsonReport "online-$Environment.json"
$libtv = Read-JsonReport 'libtv-readonly-canary.json'
$restore = Read-JsonReport 'restore-drill.json'
$machine = Read-JsonReport 'phase2-machine-evidence.json'

$gitName = (& git config --get user.name 2>$null | Out-String).Trim()
$gitEmail = (& git config --get user.email 2>$null | Out-String).Trim()
$staged = @(& git diff --cached --name-only 2>$null | Where-Object { $_ })
$unstaged = @(& git diff --name-only 2>$null | Where-Object { $_ })
$untracked = @(& git ls-files --others --exclude-standard 2>$null | Where-Object { $_ })
$branch = (& git branch --show-current 2>$null | Out-String).Trim()
$head = (& git rev-parse --verify HEAD 2>$null | Out-String).Trim()
$gitEvidence = [ordered]@{
    branch = if ($branch) { $branch } else { $null }
    head = if ($head) { $head } else { $null }
    hasCommits = [bool]$head
    stagedFileCount = $staged.Count
    unstagedFileCount = $unstaged.Count
    untrackedFileCount = $untracked.Count
    userNameConfigured = [bool]$gitName
    userEmailConfigured = [bool]$gitEmail
}

$metricRules = [ordered]@{
    duplicateFormalGenerations = @('EQ', 0)
    crossParentTaskConnections = @('EQ', 0)
    crossUserProjectAllocations = @('EQ', 0)
    assetOrderErrors = @('EQ', 0)
    pointsReservationBypasses = @('EQ', 0)
    videoDecodeSuccessRate = @('GE', 1.0)
    targetDurationCompliance = @('GE', 1.0)
    aspectRatioCompliance = @('GE', 1.0)
    unknownAfterSubmitRate = @('LT', 0.01)
    systemRateLimitRate = @('LT', 0.02)
    backloggedSlotUtilization = @('GE', 0.80)
    lowRiskAutoCompletionRate = @('GE', 0.80)
}
$metrics = [ordered]@{}
foreach ($entry in $metricRules.GetEnumerator()) {
    $value = if ($machine -and $machine.acceptanceMetrics) { $machine.acceptanceMetrics.($entry.Key) } else { $null }
    $metrics[$entry.Key] = [ordered]@{
        value = $value
        status = Metric-Status $value $entry.Value[0] ([double]$entry.Value[1])
        rule = "$($entry.Value[0]) $($entry.Value[1])"
        source = 'var/reports/phase2-machine-evidence.json'
    }
}

$controlled = if ($machine -and $machine.controlledMvp) { $machine.controlledMvp } else { $null }
$realThresholds = [ordered]@{
    parentTasks = [ordered]@{ value = if ($controlled) { $controlled.parentTasks } else { $null }; required = 30 }
    videos = [ordered]@{ value = if ($controlled) { $controlled.videos } else { $null }; required = 60 }
    stableVideos = [ordered]@{ value = if ($controlled) { $controlled.stableVideos } else { $null }; required = 30 }
    dynamicVideos = [ordered]@{ value = if ($controlled) { $controlled.dynamicVideos } else { $null }; required = 30 }
    sameProjectConcurrency = [ordered]@{ value = if ($controlled) { $controlled.sameProjectConcurrency } else { $null }; required = 4 }
    globalConcurrency = [ordered]@{ value = if ($controlled) { $controlled.globalConcurrency } else { $null }; required = 12 }
    continuousRunHours = [ordered]@{ value = if ($controlled) { $controlled.continuousRunHours } else { $null }; required = 4 }
}
foreach ($item in $realThresholds.Values) {
    $item.status = if ($null -eq $item.value) { 'NOT_RUN' } elseif ([double]$item.value -ge [double]$item.required) { 'PASS' } else { 'FAIL' }
}
$userThreshold = [ordered]@{
    value = if ($controlled) { $controlled.users } else { $null }
    minimum = 1
    maximum = 2
}
$userThreshold.status = if ($null -eq $userThreshold.value) { 'NOT_RUN' } elseif ([double]$userThreshold.value -ge 1 -and [double]$userThreshold.value -le 2) { 'PASS' } else { 'FAIL' }
$realThresholds['users'] = $userThreshold

$alembicPath = Join-Path $reportRoot 'alembic-phase2.sql'
$alembicStepPassed = $check -and $check.steps -and $check.steps.alembicOfflineSql -and $check.steps.alembicOfflineSql.status -eq 'PASS'
$alembicEvidence = if ((Test-Path -LiteralPath $alembicPath) -and $alembicStepPassed) {
    [ordered]@{
        status = 'PASS'
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $alembicPath).Hash.ToLowerInvariant()
        sizeBytes = (Get-Item -LiteralPath $alembicPath).Length
    }
} else { [ordered]@{ status = 'NOT_RUN'; sha256 = $null; sizeBytes = $null } }

$authorizationPath = Join-Path $projectRoot 'var\evidence\paid-authorization.json'
$authorization = if (Test-Path -LiteralPath $authorizationPath) {
    try { Get-Content -Raw -LiteralPath $authorizationPath | ConvertFrom-Json }
    catch { [pscustomobject]@{ status = 'INVALID' } }
} else { $null }
$authorizationErrors = @()
$requiredAuthorizationFields = @(
    'model', 'openAiRequests', 'videoCount', 'stableVideos', 'dynamicVideos',
    'pointsCap', 'materials', 'users', 'windowStart', 'windowEnd',
    'stopConditions', 'rollback'
)
if ($authorization) {
    foreach ($field in $requiredAuthorizationFields) {
        if ($authorization.PSObject.Properties.Name -notcontains $field -or $null -eq $authorization.$field) {
            $authorizationErrors += "missing $field"
        }
    }
    try {
        $windowStart = [DateTimeOffset]$authorization.windowStart
        $windowEnd = [DateTimeOffset]$authorization.windowEnd
        $now = [DateTimeOffset]::UtcNow
        if ($windowEnd -le $windowStart) { $authorizationErrors += 'invalid authorization time window' }
        if ($now -lt $windowStart -or $now -gt $windowEnd) { $authorizationErrors += 'authorization is outside its time window' }
    }
    catch { $authorizationErrors += 'authorization time window is not parseable' }
    foreach ($field in @('openAiRequests', 'videoCount', 'stableVideos', 'dynamicVideos', 'pointsCap')) {
        if ($null -ne $authorization.$field) {
            try {
                if ([double]$authorization.$field -lt 0) { $authorizationErrors += "$field must be non-negative" }
            }
            catch { $authorizationErrors += "$field must be numeric" }
        }
    }
    foreach ($field in @('materials', 'users', 'stopConditions')) {
        if ($null -ne $authorization.$field -and @($authorization.$field).Count -eq 0) {
            $authorizationErrors += "$field must not be empty"
        }
    }
    if ([string]::IsNullOrWhiteSpace([string]$authorization.model)) { $authorizationErrors += 'model must not be empty' }
    if ($null -ne $authorization.videoCount -and $null -ne $authorization.stableVideos -and $null -ne $authorization.dynamicVideos -and ([double]$authorization.stableVideos + [double]$authorization.dynamicVideos) -gt [double]$authorization.videoCount) {
        $authorizationErrors += 'Stable and Dynamic quantities exceed videoCount'
    }
    $authorizedCaps = [ordered]@{
        openAiRequests = if ($machine -and $machine.realConsumption) { $machine.realConsumption.openAiRequests } else { $null }
        videoCount = if ($machine -and $machine.realConsumption) { $machine.realConsumption.videosGenerated } else { $null }
        pointsCap = if ($machine -and $machine.realConsumption) { $machine.realConsumption.libtvPoints } else { $null }
        stableVideos = if ($machine -and $machine.controlledMvp) { $machine.controlledMvp.stableVideos } else { $null }
        dynamicVideos = if ($machine -and $machine.controlledMvp) { $machine.controlledMvp.dynamicVideos } else { $null }
    }
    foreach ($entry in $authorizedCaps.GetEnumerator()) {
        if ($null -ne $entry.Value -and $null -ne $authorization.($entry.Key) -and [double]$entry.Value -gt [double]$authorization.($entry.Key)) {
            $authorizationErrors += "observed $($entry.Key) exceeds authorization cap"
        }
    }
}
$paidAuthorized = $authorization -and $authorization.status -eq 'APPROVED' -and $authorizationErrors.Count -eq 0

$verification = [ordered]@{
    fullCheck = if ($check) { $check } else { [ordered]@{ status = 'NOT_RUN' } }
    alembicOfflineSql = $alembicEvidence
    onlineInfrastructure = if ($online) { $online } else { [ordered]@{ status = 'NOT_RUN' } }
    libtvReadOnlyCanary = if ($libtv) { $libtv } else { [ordered]@{ status = 'NOT_RUN' } }
    independentRestoreDrill = if ($restore) { $restore } else { [ordered]@{ status = 'NOT_RUN' } }
    machineEvidence = if ($machine) { $machine.status } else { 'NOT_RUN' }
    machineEvidenceCollectorExitCode = $collectorExitCode
}

$noPaidGateStatuses = @(
    $verification.alembicOfflineSql.status,
    $verification.onlineInfrastructure.status,
    $verification.libtvReadOnlyCanary.status,
    $verification.independentRestoreDrill.status
)
$reportedSkips = if ($check -and $check.steps -and $check.steps.backendPytest) { @($check.steps.backendPytest.skippedTests) } else { @() }
$onlyResolvedOnlineSkips = $reportedSkips.Count -gt 0 -and @($reportedSkips | Where-Object { $_.className -notlike '*test_online_infrastructure*' }).Count -eq 0 -and $verification.onlineInfrastructure.status -eq 'PASS'
$fullCheckPassed = $verification.fullCheck.status -eq 'PASS' -or ($verification.fullCheck.status -eq 'PASS_WITH_SKIPS' -and $onlyResolvedOnlineSkips)
$machineEvidencePassed = $collectorExitCode -eq 0 -and $verification.machineEvidence -eq 'COLLECTED'
$noPaidGatesPassed = $environmentLoaded -and $fullCheckPassed -and $machineEvidencePassed -and @($noPaidGateStatuses | Where-Object { $_ -ne 'PASS' }).Count -eq 0
$metricStatuses = @($metrics.Values | ForEach-Object { $_.status })
$thresholdStatuses = @($realThresholds.Values | ForEach-Object { $_.status })
$phase2Complete = $paidAuthorized -and $noPaidGatesPassed -and $metricStatuses -notcontains 'FAIL' -and $metricStatuses -notcontains 'NOT_RUN' -and $thresholdStatuses -notcontains 'FAIL' -and $thresholdStatuses -notcontains 'NOT_RUN'

$blockers = @()
if (-not $gitEvidence.hasCommits) { $blockers += [ordered]@{ gate = 'PHASE_1_COMMIT'; status = 'BLOCKED'; reason = 'Repository has no commit' } }
if (-not $gitEvidence.userNameConfigured -or -not $gitEvidence.userEmailConfigured) { $blockers += [ordered]@{ gate = 'GIT_IDENTITY'; status = 'BLOCKED'; reason = 'git user.name and/or user.email is not configured' } }
if (-not $environmentLoaded) { $blockers += [ordered]@{ gate = 'ENVIRONMENT_CONFIGURATION'; status = 'BLOCKED'; reason = "Missing .env.$Environment" } }
foreach ($gate in @(
    @('FULL_CHECK', $(if ($fullCheckPassed) { 'PASS' } else { $verification.fullCheck.status })),
    @('ONLINE_INFRASTRUCTURE', $verification.onlineInfrastructure.status),
    @('LIBTV_READ_ONLY_CANARY', $verification.libtvReadOnlyCanary.status),
    @('RESTORE_DRILL', $verification.independentRestoreDrill.status),
    @('MACHINE_EVIDENCE', $verification.machineEvidence)
)) {
    if ($gate[1] -ne 'PASS' -and $gate[1] -ne 'COLLECTED') { $blockers += [ordered]@{ gate = $gate[0]; status = $gate[1]; reason = 'See referenced machine report' } }
}
if (-not $paidAuthorized) {
    $authorizationReason = if ($authorizationErrors.Count -gt 0) { $authorizationErrors -join '; ' } else { 'No approved paid-authorization evidence file' }
    $blockers += [ordered]@{ gate = 'PAID_CANARY'; status = 'NOT_AUTHORIZED'; reason = $authorizationReason }
}

$status = if ($phase2Complete) {
    'PHASE_2_COMPLETE'
} elseif ($noPaidGatesPassed -and -not $paidAuthorized) {
    'READY_FOR_CENTRAL_PAID_AUTHORIZATION'
} elseif ($noPaidGatesPassed) {
    'PAID_VALIDATION_IN_PROGRESS'
} else {
    'BLOCKED_BEFORE_PAID_GATE'
}
$report = [ordered]@{
    schemaVersion = '2.0'
    phase = 'PHASE_2_CONTROLLED_MVP'
    status = $status
    generatedAt = [DateTimeOffset]::UtcNow.ToString('o')
    paidAuthorizationReceived = [bool]$paidAuthorized
    paidAuthorization = [ordered]@{
        path = 'var/evidence/paid-authorization.json'
        status = if ($paidAuthorized) { 'VALID' } elseif ($authorization) { 'INVALID' } else { 'NOT_FOUND' }
        validationErrors = $authorizationErrors
    }
    noPaidGatesPassed = $noPaidGatesPassed
    phase2Complete = $phase2Complete
    git = $gitEvidence
    realConsumption = if ($machine -and $machine.realConsumption) { $machine.realConsumption } else { $null }
    controlledMvpThresholds = $realThresholds
    verification = $verification
    acceptanceMetrics = $metrics
    blockers = $blockers
    evidence = @(
        'var/reports/check.json',
        "var/reports/online-$Environment.json",
        'var/reports/libtv-readonly-canary.json',
        'var/reports/restore-drill.json',
        'var/reports/phase2-machine-evidence.json',
        'var/reports/alembic-phase2.sql'
    )
}
$destination = Join-Path $reportRoot 'phase2-readiness.json'
$report | ConvertTo-Json -Depth 14 | Set-Content -Encoding utf8 -LiteralPath $destination
$report | ConvertTo-Json -Depth 14

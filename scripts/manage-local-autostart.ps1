param(
    [ValidateSet('Install', 'Uninstall', 'Status')]
    [string]$Action = 'Status',
    [ValidateSet('Local', 'Lan')]
    [string]$Mode = 'Local',
    [string]$TaskName = 'LibTV Local Stack Watchdog'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$watchdogScript = Join-Path $PSScriptRoot 'watch-local-stack.ps1'
$powershell = Join-Path $PSHOME 'powershell.exe'
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$legacyTaskNames = @('LibTV Local API', 'LibTV Local Frontend')

function Get-AutostartStatus {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        return [pscustomobject]@{
            TaskName = $TaskName
            Installed = $false
            State = 'NotInstalled'
            LastRunTime = $null
            LastTaskResult = $null
        }
    }

    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    $arguments = @($task.Actions)[0].Arguments
    return [pscustomobject]@{
        TaskName = $TaskName
        Installed = $true
        State = [string]$task.State
        LastRunTime = $info.LastRunTime
        LastTaskResult = if ($task.State -eq 'Running') { 'Running' } else { '0x{0:X8}' -f [uint32]$info.LastTaskResult }
        User = $task.Principal.UserId
        Trigger = 'At user logon'
        ExecutionTimeLimit = [string]$task.Settings.ExecutionTimeLimit
        Mode = if ($arguments -match '(?i)-Mode\s+Lan') { 'Lan' } else { 'Local' }
        WatchdogScript = $watchdogScript
    }
}

switch ($Action) {
    'Install' {
        if (-not (Test-Path -LiteralPath $watchdogScript)) {
            throw "Watchdog script not found: $watchdogScript"
        }

        $arguments = "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$watchdogScript`" -Mode $Mode"
        $taskAction = New-ScheduledTaskAction `
            -Execute $powershell `
            -Argument $arguments `
            -WorkingDirectory $projectRoot
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
        $principal = New-ScheduledTaskPrincipal `
            -UserId $currentUser `
            -LogonType Interactive `
            -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -StartWhenAvailable `
            -RestartCount 999 `
            -RestartInterval (New-TimeSpan -Minutes 1) `
            -ExecutionTimeLimit ([TimeSpan]::Zero) `
            -MultipleInstances IgnoreNew

        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Register-ScheduledTask `
            -TaskName $TaskName `
            -Action $taskAction `
            -Trigger $trigger `
            -Principal $principal `
            -Settings $settings `
            -Description "Keep the LibTV API, runner, and frontend available after Windows logon ($Mode mode)." `
            -Force | Out-Null

        foreach ($legacyTaskName in $legacyTaskNames) {
            if (Get-ScheduledTask -TaskName $legacyTaskName -ErrorAction SilentlyContinue) {
                Stop-ScheduledTask -TaskName $legacyTaskName -ErrorAction SilentlyContinue
                Unregister-ScheduledTask -TaskName $legacyTaskName -Confirm:$false
            }
        }

        Start-ScheduledTask -TaskName $TaskName
        Start-Sleep -Seconds 2
        Get-AutostartStatus
    }
    'Uninstall' {
        if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
            Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        }
        Get-AutostartStatus
    }
    'Status' {
        Get-AutostartStatus
    }
}

# install_schedule.ps1 - Installs the ApplyAgent nightly refresh as a
# Windows Scheduled Task.
#
# Installs a single task that runs at 6:30 AM daily. If the laptop is asleep at
# 6:30, Windows will run it when the laptop next wakes up (provided "Run task as
# soon as possible after a scheduled start is missed" is enabled).
#
# Run once as your normal user (NOT as admin - the task runs as you):
#   powershell -ExecutionPolicy Bypass -File automation\install_schedule.ps1
#
# To uninstall:
#   schtasks /delete /tn "ApplyAgent_NightlyRefresh" /f

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)

# Use nightly_refresh.py (Python orchestrator) - works correctly with
# the scan_runner log capture. The old .ps1 version silently swallowed
# all output when run as a detached/scheduled process.
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }
$scriptPath = Join-Path $repoRoot "automation\nightly_refresh.py"

if (-not (Test-Path $scriptPath)) {
    Write-Error "nightly_refresh.py not found at $scriptPath"
    exit 1
}

$taskName = "ApplyAgent_NightlyRefresh"
$action = New-ScheduledTaskAction `
    -Execute $python `
    -Argument "`"$scriptPath`"" `
    -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -Daily -At 6:30AM
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 15)

# Unregister existing instance (idempotent install)
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "ApplyAgent: scrape + delta + morning brief at 6:30 AM daily" `
    -RunLevel Limited

Write-Host ""
Write-Host "Installed scheduled task '$taskName'."
Write-Host "  Runs:   daily at 6:30 AM"
Write-Host "  Python: $python"
Write-Host "  Script: $scriptPath"
Write-Host ""
Write-Host "Check status:   schtasks /query /tn $taskName /v /fo LIST"
Write-Host "Run now:        schtasks /run /tn $taskName"
Write-Host "Uninstall:      schtasks /delete /tn $taskName /f"

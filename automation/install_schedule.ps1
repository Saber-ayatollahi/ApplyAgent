# install_schedule.ps1 — Installs the ApplyAgent nightly refresh as a
# Windows Scheduled Task.
#
# Installs a single task that runs at 6:30 AM daily. If the laptop is asleep at
# 6:30, Windows will run it when the laptop next wakes up (provided "Run task as
# soon as possible after a scheduled start is missed" is enabled).
#
# Run once as your normal user (NOT as admin — the task runs as you):
#   powershell -ExecutionPolicy Bypass -File automation\install_schedule.ps1
#
# To uninstall:
#   schtasks /delete /tn "ApplyAgent_NightlyRefresh" /f

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)
$scriptPath = Join-Path $repoRoot "automation\nightly_refresh.ps1"

if (-not (Test-Path $scriptPath)) {
    Write-Error "nightly_refresh.ps1 not found at $scriptPath"
    exit 1
}

$taskName = "ApplyAgent_NightlyRefresh"
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
$trigger = New-ScheduledTaskTrigger -Daily -At 6:30AM
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
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
Write-Host "  Runs: daily at 6:30 AM"
Write-Host "  Script: $scriptPath"
Write-Host ""
Write-Host "Check status:   schtasks /query /tn $taskName /v /fo LIST"
Write-Host "Run now:        schtasks /run /tn $taskName"
Write-Host "Uninstall:      schtasks /delete /tn $taskName /f"

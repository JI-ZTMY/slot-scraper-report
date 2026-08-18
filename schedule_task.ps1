# Registers (or re-registers) a daily Windows scheduled task that runs
# publish.bat, which scrapes the configured stores and publishes the
# updated report to GitHub Pages.
#
# If double-clicking this file does nothing or shows a security warning,
# open PowerShell and run:
#   powershell -ExecutionPolicy Bypass -File schedule_task.ps1

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$publishBat = Join-Path $scriptDir "publish.bat"
$taskName = "SlotScraperDailyReport"

# Change this if you'd like a different time of day (24h format, "HH:mm").
$runTime = "09:00"

$action = New-ScheduledTaskAction -Execute $publishBat -WorkingDirectory $scriptDir
$trigger = New-ScheduledTaskTrigger -Daily -At $runTime
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
  -Description "Runs Slot Scraper's daily scrape and report update (publish.bat)"

Write-Host "Registered task '$taskName' to run daily at $runTime."
Write-Host "To change the time, edit `$runTime in this file and run it again, or edit the task in Task Scheduler."
Write-Host ""
Write-Host "To test it right now, run:"
Write-Host "  Start-ScheduledTask -TaskName $taskName"

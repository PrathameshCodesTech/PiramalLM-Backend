# ============================================================
# LM-MonoLithic — Register nightly_jobs.bat with Windows Task Scheduler
#
# Run once (as Administrator) from Backend\:
#   powershell -ExecutionPolicy Bypass -File scripts\register_scheduler.ps1
# ============================================================

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$BackendDir = Split-Path -Parent $ScriptDir
$BatFile    = Join-Path $ScriptDir "nightly_jobs.bat"
$TaskName   = "LMMonoLithic_NightlyJobs"

# Check if task already exists
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Task '$TaskName' already registered. Unregistering first..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Build the action
$Action  = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$BatFile`"" `
    -WorkingDirectory $BackendDir

# Trigger: daily at 00:05
$Trigger = New-ScheduledTaskTrigger -Daily -At "00:05"

# Settings
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable

# Register
Register-ScheduledTask `
    -TaskName  $TaskName `
    -Action    $Action `
    -Trigger   $Trigger `
    -Settings  $Settings `
    -Description "LM-MonoLithic: expire leases, generate invoices, process overdue, refresh AR summaries" `
    -RunLevel  Highest `
    -Force

Write-Host ""
Write-Host "Task '$TaskName' registered successfully." -ForegroundColor Green
Write-Host "It will run daily at 00:05."
Write-Host "Log file: $ScriptDir\nightly_jobs.log"
Write-Host ""
Write-Host "To run immediately for testing:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"

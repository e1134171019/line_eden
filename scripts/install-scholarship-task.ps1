[CmdletBinding()]
param(
    [string]$TaskName = "ScholarshipAgent",
    [ValidatePattern("^(?:[01]\d|2[0-3]):[0-5]\d$")]
    [string]$DailyAt = "08:00",
    [switch]$NoGemini,
    [switch]$RunNow
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RunnerPath = Join-Path $ProjectRoot "scripts/run-scholarship-agent.ps1"
$PythonPath = Join-Path $ProjectRoot ".venv/Scripts/python.exe"
$EnvPath = Join-Path $ProjectRoot ".env"
$ProfilePath = Join-Path $ProjectRoot "profile.json"
$PowerShellPath = (Get-Process -Id $PID).Path

foreach ($RequiredPath in @($RunnerPath, $PythonPath, $EnvPath, $ProfilePath, $PowerShellPath)) {
    if (-not (Test-Path $RequiredPath)) {
        throw "缺少排程必要檔案：$RequiredPath"
    }
}

$PowerShellArguments = @(
    "-NoProfile"
    "-ExecutionPolicy Bypass"
    "-File `"$RunnerPath`""
)
if ($NoGemini) {
    $PowerShellArguments += "-NoGemini"
}

$Action = New-ScheduledTaskAction `
    -Execute $PowerShellPath `
    -Argument ($PowerShellArguments -join " ")
$TriggerTime = [datetime]::ParseExact(
    $DailyAt,
    "HH:mm",
    [System.Globalization.CultureInfo]::InvariantCulture
)
$Trigger = New-ScheduledTaskTrigger -Daily -At $TriggerTime
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Principal = New-ScheduledTaskPrincipal `
    -UserId $CurrentUser `
    -LogonType Interactive `
    -RunLevel Limited
$Task = New-ScheduledTask `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "每天檢查獎學金公告，只推播明確符合目前背景的新公告。"

Register-ScheduledTask -TaskName $TaskName -InputObject $Task -Force | Out-Null
Write-Host "已建立工作排程：$TaskName"
Write-Host "每日執行時間：$DailyAt"
Write-Host "PowerShell 執行檔：$PowerShellPath"
Write-Host "Gemini：$(if ($NoGemini) { '停用' } else { '啟用' })"

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "已要求立即執行一次。"
}

Write-Host "檢查狀態："
Write-Host "  & ./scripts/show-scholarship-task-status.ps1"

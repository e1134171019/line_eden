[CmdletBinding()]
param(
    [string]$TaskName = "ScholarshipAgent"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$StatusPath = Join-Path $ProjectRoot "data/last_run.json"
$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($null -eq $Task) {
    Write-Host "工作排程：未安裝"
}
else {
    $TaskInfo = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host "工作排程：$TaskName"
    Write-Host "狀態：$($Task.State)"
    Write-Host "下次執行：$($TaskInfo.NextRunTime)"
    Write-Host "上次執行：$($TaskInfo.LastRunTime)"
    Write-Host "上次結果：$($TaskInfo.LastTaskResult)"
}

if (-not (Test-Path $StatusPath)) {
    Write-Host "尚未產生 data/last_run.json"
    exit 0
}

$Status = Get-Content $StatusPath -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Host ""
Write-Host "Agent 最後執行狀態：$($Status.status)"
Write-Host "開始：$($Status.started_at)"
Write-Host "完成：$($Status.finished_at)"
Write-Host "Exit code：$($Status.exit_code)"
Write-Host "Log：$($Status.log_file)"
if ($null -ne $Status.summary) {
    Write-Host "蒐集：$($Status.summary.collected)"
    Write-Host "待通知：$($Status.summary.pending)"
    Write-Host "已通知：$($Status.summary.notified)"
    Write-Host "Gemini 呼叫：$($Status.summary.gemini_calls)"
}

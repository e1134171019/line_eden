[CmdletBinding()]
param(
    [string]$TaskName = "ScholarshipAgent"
)

$ErrorActionPreference = "Stop"
$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $Task) {
    Write-Host "找不到工作排程：$TaskName"
    exit 0
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "已移除工作排程：$TaskName"

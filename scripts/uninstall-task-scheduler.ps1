# 卸载每日定时备份任务

[CmdletBinding()]
param(
    [string]$TaskName = 'ClaudeBackup-Daily'
)

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "✅ 已卸载任务: $TaskName"
} else {
    Write-Host "任务不存在: $TaskName"
}

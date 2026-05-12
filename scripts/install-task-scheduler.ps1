# 注册 Windows Task Scheduler 每日定时备份任务
# 用法：
#   .\install-task-scheduler.ps1                # 默认 23:30 + 自动反推 exe
#   .\install-task-scheduler.ps1 -Time 08:00    # 改时间
#   .\install-task-scheduler.ps1 -Exe <路径>    # 显式覆盖 exe
#
# 作用：
#   - 每天指定时间执行 ClaudeBackup scheduled-daily
#   - 错过补跑（Start When Available）
#   - 仅用户登录时跑，不强制接 AC 电源
#   - 完全独立于 Claude 进程

[CmdletBinding()]
param(
    [string]$Time = '23:30',
    [string]$Exe  = '',
    [string]$TaskName = 'ClaudeBackup-Daily'
)

if (-not $Exe) {
    $appRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..') -ErrorAction SilentlyContinue
    if ($appRoot -and (Test-Path (Join-Path $appRoot 'ClaudeBackup.exe'))) {
        $Exe = Join-Path $appRoot 'ClaudeBackup.exe'
    } else {
        foreach ($c in @(
            "$env:ProgramFiles\ClaudeBackup\ClaudeBackup.exe",
            "${env:ProgramFiles(x86)}\ClaudeBackup\ClaudeBackup.exe",
            'D:\Program Files\ClaudeBackup\ClaudeBackup.exe'
        )) { if (Test-Path $c) { $Exe = $c; break } }
    }
    if (-not $Exe) { Write-Error "找不到 ClaudeBackup.exe — 请显式 -Exe <路径>"; exit 1 }
    Write-Host "自动解析 Exe: $Exe"
}

if ($Time -notmatch '^\d{2}:\d{2}$') {
    Write-Error "Time 必须是 HH:MM 格式，例如 23:30"; exit 1
}

if (-not (Test-Path $Exe)) {
    Write-Warning "可执行文件不存在: $Exe"
    Write-Warning "可能 ClaudeBackup 还没打包安装。继续注册任务（路径以后存在即可）。"
}

$action  = New-ScheduledTaskAction -Execute $Exe -Argument 'scheduled-daily'

$trigger = New-ScheduledTaskTrigger -Daily -At $Time

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

$task = New-ScheduledTask `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description 'ClaudeBackup 每日变化检测 + 增量备份（NAS bare 镜像 + 时间快照 bundle）'

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "已存在同名任务，覆盖更新: $TaskName"
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName -InputObject $task | Out-Null

Write-Host ""
Write-Host "✅ 已注册任务: $TaskName"
Write-Host "   时间: 每日 $Time"
Write-Host "   命令: `"$Exe`" scheduled-daily"
Write-Host ""
Write-Host "查看任务：Get-ScheduledTask -TaskName $TaskName"
Write-Host "立即测试：Start-ScheduledTask -TaskName $TaskName"
Write-Host "卸载任务：.\uninstall-task-scheduler.ps1"

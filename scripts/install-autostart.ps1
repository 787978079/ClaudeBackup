# 注册登录自启动 — 启动文件夹放快捷方式（用户级，无需管理员）
#
# 启动参数 --tray：只起托盘不弹主窗
# 卸载：.\uninstall-autostart.ps1

[CmdletBinding()]
param(
    [string]$Exe = ''
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
}

$startup = [Environment]::GetFolderPath('Startup')
$lnkPath = Join-Path $startup 'ClaudeBackup.lnk'

if (-not (Test-Path $Exe)) {
    Write-Warning "目标 exe 不存在: $Exe（仍创建快捷方式，等 exe 出现即可生效）"
}

$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut($lnkPath)
$lnk.TargetPath = $Exe
$lnk.Arguments  = 'tray'
$lnk.WorkingDirectory = Split-Path -Parent $Exe
$lnk.Description = 'ClaudeBackup 系统托盘'
$lnk.IconLocation = "$Exe,0"
$lnk.WindowStyle = 7  # 最小化
$lnk.Save()

Write-Host "✅ 已创建自启动快捷方式: $lnkPath"
Write-Host "   下次登录会自动启动托盘。"
Write-Host "   现在立刻启动一次：& `"$Exe`" tray"

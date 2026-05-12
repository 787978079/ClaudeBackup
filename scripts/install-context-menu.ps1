# 注册资源管理器右键菜单（HKCU 用户级，无需管理员权限）
#
# 在 Windows 资源管理器里，文件夹上右键 + 文件夹背景上右键 都能看到
# "📦 Claude Backup" 子菜单，5 个子项调用 ClaudeBackup.exe 不同的 ui-action.
#
# 用法：
#   .\install-context-menu.ps1                  # 自动从脚本位置反推 exe
#   .\install-context-menu.ps1 -Exe <路径>      # 显式指定 exe
#
# 卸载：.\uninstall-context-menu.ps1

[CmdletBinding()]
param(
    [string]$Exe = ''
)

# 自动从脚本位置反推 exe 路径：
#   打包模式：脚本位于 {app}\_internal\scripts\，往上 2 级是 {app}，{app}\ClaudeBackup.exe
#   源码模式：传 -Exe 显式覆盖（dev 场景）
if (-not $Exe) {
    $appRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..') -ErrorAction SilentlyContinue
    if ($appRoot -and (Test-Path (Join-Path $appRoot 'ClaudeBackup.exe'))) {
        $Exe = Join-Path $appRoot 'ClaudeBackup.exe'
    } else {
        # 回退 — Program Files 同名子目录
        $candidates = @(
            "$env:ProgramFiles\ClaudeBackup\ClaudeBackup.exe",
            "${env:ProgramFiles(x86)}\ClaudeBackup\ClaudeBackup.exe",
            'D:\Program Files\ClaudeBackup\ClaudeBackup.exe'
        )
        foreach ($c in $candidates) {
            if (Test-Path $c) { $Exe = $c; break }
        }
    }
    if (-not $Exe) {
        Write-Error "找不到 ClaudeBackup.exe — 请显式传 -Exe <路径>"
        exit 1
    }
    Write-Host "自动解析 Exe: $Exe"
}

$ErrorActionPreference = 'Stop'

# 三个挂载点：文件夹、文件夹背景、目录树根
$mounts = @(
    'HKCU:\Software\Classes\Directory\shell\ClaudeBackup',
    'HKCU:\Software\Classes\Directory\Background\shell\ClaudeBackup',
    'HKCU:\Software\Classes\Drive\shell\ClaudeBackup'
)

# 子菜单项（顺序即显示顺序）
$subItems = @(
    @{ Id='register'; Label='把这个文件夹加入备份'; Action='register' },
    @{ Id='backup';   Label='立即备份这个项目';     Action='backup'   },
    @{ Id='release';  Label='发布这个版本到 GitHub…'; Action='release' },
    @{ Id='list';     Label='看看这个项目的所有备份'; Action='list'   },
    @{ Id='compare';  Label='对比两个备份…';         Action='compare' }
)

function Set-RegValue {
    param([string]$Path, [string]$Name, [string]$Value, [string]$Type = 'String')
    if (-not (Test-Path $Path)) {
        New-Item -Path $Path -Force | Out-Null
    }
    New-ItemProperty -Path $Path -Name $Name -Value $Value -PropertyType $Type -Force | Out-Null
}

function Install-MountPoint {
    param([string]$Root)

    # 主菜单项
    Set-RegValue -Path $Root -Name '(default)' -Value '📦 Claude Backup'
    Set-RegValue -Path $Root -Name 'MUIVerb' -Value '📦 Claude Backup'
    Set-RegValue -Path $Root -Name 'SubCommands' -Value ''  # 用 ExtendedSubCommandsKey 模式
    Set-RegValue -Path $Root -Name 'Icon' -Value $Exe

    # 子菜单容器
    $shellPath = "$Root\shell"
    if (-not (Test-Path $shellPath)) {
        New-Item -Path $shellPath -Force | Out-Null
    }

    foreach ($it in $subItems) {
        $itemPath = "$shellPath\$($it.Id)"
        Set-RegValue -Path $itemPath -Name 'MUIVerb' -Value $it.Label
        # %V 是右键命中的目录路径（背景右键也是当前文件夹）
        $cmd = "`"$Exe`" ui-action $($it.Action) --path `"%V`""
        Set-RegValue -Path "$itemPath\command" -Name '(default)' -Value $cmd
    }
}

foreach ($m in $mounts) {
    if (Test-Path $m) {
        Write-Host "已存在，覆盖: $m"
        Remove-Item $m -Recurse -Force
    }
    Install-MountPoint -Root $m
    Write-Host "已注册: $m"
}

Write-Host ""
Write-Host "✅ 资源管理器右键菜单注册完成。"
Write-Host "   随便找一个文件夹右键，应该能看到 '📦 Claude Backup' 子菜单。"
Write-Host ""
Write-Host "卸载：.\uninstall-context-menu.ps1"

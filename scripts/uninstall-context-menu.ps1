# 卸载资源管理器右键菜单

[CmdletBinding()] param()

$mounts = @(
    'HKCU:\Software\Classes\Directory\shell\ClaudeBackup',
    'HKCU:\Software\Classes\Directory\Background\shell\ClaudeBackup',
    'HKCU:\Software\Classes\Drive\shell\ClaudeBackup'
)

foreach ($m in $mounts) {
    if (Test-Path $m) {
        Remove-Item $m -Recurse -Force
        Write-Host "已移除: $m"
    } else {
        Write-Host "不存在: $m"
    }
}

Write-Host ""
Write-Host "✅ 已卸载右键菜单。"

# 移除自启动快捷方式

$startup = [Environment]::GetFolderPath('Startup')
$lnkPath = Join-Path $startup 'ClaudeBackup.lnk'

if (Test-Path $lnkPath) {
    Remove-Item $lnkPath -Force
    Write-Host "✅ 已移除: $lnkPath"
} else {
    Write-Host "快捷方式不存在: $lnkPath"
}

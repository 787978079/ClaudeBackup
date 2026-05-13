# PyInstaller 打包 ClaudeBackup
#
# 用法：
#   .\build.ps1                     # 打包到 <repo>\dist\
#   .\build.ps1 -Install            # 打包后再部署到 %ProgramFiles%\ClaudeBackup\（需管理员）
#   .\build.ps1 -Clean -Install     # 清旧构建 + 打包 + 部署
#
# 输出：
#   ClaudeBackup.exe         主程序（GUI / 托盘 / CLI 都从它走）
#   ClaudeBackup-cli.exe     可选的纯 CLI 版（控制台窗口）— Stop hook 路径用

[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$Install,
    [string]$InstallDir = ''
)

if (-not $InstallDir) { $InstallDir = Join-Path $env:ProgramFiles 'ClaudeBackup' }

$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

if ($Clean) {
    Write-Host '🧹 清理旧构建...'
    Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
    Get-ChildItem -Filter '*.spec' | Remove-Item -Force
}

# 1. 检查 pyinstaller
$pyi = & python -m PyInstaller --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host '📦 安装 PyInstaller...'
    python -m pip install pyinstaller
}

# 2. 打 GUI 主程序（windowed —— 双击不弹控制台）
$iconFile = "$repo\claude_backup\gui\assets\icons\claudebackup.ico"
if (-not (Test-Path $iconFile)) {
    Write-Host "⚠️ 找不到 $iconFile — 先跑 python scripts/generate_icons.py 生成"
    throw "图标缺失"
}
$versionFile = "$repo\installer\version_info.txt"
if (-not (Test-Path $versionFile)) {
    throw "找不到 $versionFile — 这是 exe 的 Windows 资源元数据"
}
# 只把朋友机上需要用到的 ps1 打进去（install/uninstall 六件套）；
# build.ps1 / deploy_*.ps1 / elevate_*.ps1 是开发期脚本，含 dev 路径硬编码，
# 不该泄露给最终用户。
$shippedScripts = @(
    'install-context-menu.ps1',
    'install-task-scheduler.ps1',
    'install-autostart.ps1',
    'uninstall-context-menu.ps1',
    'uninstall-task-scheduler.ps1',
    'uninstall-autostart.ps1'
)
$addDataArgs = @()
foreach ($s in $shippedScripts) {
    $p = "$repo\scripts\$s"
    if (-not (Test-Path $p)) { throw "缺少必备脚本 $p — 不允许打包" }
    $addDataArgs += @('--add-data', "$p;scripts")
}

Write-Host '🔨 打包 GUI: ClaudeBackup.exe'
python -m PyInstaller `
    --noconfirm `
    --windowed `
    --name 'ClaudeBackup' `
    --paths . `
    --collect-all PySide6 `
    --collect-all qtawesome `
    --add-data 'claude_backup/gui/assets;claude_backup/gui/assets' `
    @addDataArgs `
    --icon $iconFile `
    --version-file $versionFile `
    pyi-entry-gui.py
if ($LASTEXITCODE -ne 0) { throw "GUI 打包失败" }

# 3. 打 CLI（console）
Write-Host '🔨 打包 CLI: ClaudeBackup-cli.exe'
python -m PyInstaller `
    --noconfirm `
    --console `
    --name 'ClaudeBackup-cli' `
    --paths . `
    --collect-all PySide6 `
    --collect-all qtawesome `
    @addDataArgs `
    --icon $iconFile `
    --version-file $versionFile `
    pyi-entry-cli.py
if ($LASTEXITCODE -ne 0) { throw "CLI 打包失败" }

Write-Host ""
Write-Host "✅ 打包完成"
Write-Host "   GUI: $repo\dist\ClaudeBackup\ClaudeBackup.exe"
Write-Host "   CLI: $repo\dist\ClaudeBackup-cli\ClaudeBackup-cli.exe"

if ($Install) {
    Write-Host ""
    Write-Host "📥 部署到 $InstallDir..."
    if (-not (Test-Path $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }
    # 用 robocopy 同步
    robocopy "$repo\dist\ClaudeBackup" $InstallDir /MIR /NFL /NDL /NJH /NJS /NC /NS | Out-Null
    # CLI exe 也复制过去
    Copy-Item "$repo\dist\ClaudeBackup-cli\ClaudeBackup-cli.exe" "$InstallDir\ClaudeBackup-cli.exe" -Force
    Write-Host "✅ 已部署到 $InstallDir"
    Write-Host ""
    Write-Host "下一步："
    Write-Host "  .\install-task-scheduler.ps1"
    Write-Host "  .\install-context-menu.ps1"
    Write-Host "  .\install-autostart.ps1"
}

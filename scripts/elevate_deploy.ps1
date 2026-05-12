# Triggered by deploy.cmd. Pure ASCII to avoid PS5.1 GBK encoding issues.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 仓库根 = 本脚本所在目录的上一级（scripts/ 的 parent）
$repo = Split-Path -Parent $PSScriptRoot
$adminScript = Join-Path $repo 'scripts\deploy_admin.ps1'
$installRoot = Join-Path $env:ProgramFiles 'ClaudeBackup'
$installExe  = Join-Path $installRoot 'ClaudeBackup.exe'
$adminLog    = Join-Path $repo 'deploy_admin.log'

Write-Host ""
Write-Host "About to show UAC prompt. Please click [Yes]."
Write-Host ""

try {
    $proc = Start-Process -Verb RunAs -Wait -PassThru `
        -FilePath powershell.exe `
        -ArgumentList @(
            '-NoProfile',
            '-ExecutionPolicy', 'Bypass',
            '-File', $adminScript
        )
    Write-Host ("Child exit code: " + $proc.ExitCode)
} catch {
    Write-Host ("Launch failed (UAC cancelled?): " + $_.Exception.Message) -ForegroundColor Red
}

Write-Host ""
if (Test-Path $installExe) {
    Write-Host "[OK] Deployed successfully" -ForegroundColor Green
    $info = Get-Item $installExe
    Write-Host ("  Path : " + $info.FullName)
    Write-Host ("  Size : " + [math]::Round($info.Length/1MB,1) + " MB")
    $total = (Get-ChildItem $installRoot -Recurse | Measure-Object Length -Sum).Sum
    Write-Host ("  Total: " + [math]::Round($total/1MB,1) + " MB")
} else {
    Write-Host "[FAIL] Deployment failed" -ForegroundColor Red
    if (Test-Path $adminLog) {
        Write-Host "--- deploy_admin.log ---"
        Get-Content $adminLog
    } else {
        Write-Host "  No log generated. UAC was likely cancelled. Double-click deploy.cmd again."
    }
}

Write-Host ""
Read-Host "Press Enter to close"

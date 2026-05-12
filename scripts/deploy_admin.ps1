# Deploy dist\ClaudeBackup to D:\Program Files\ClaudeBackup (admin required).
# Triggered by Start-Process -Verb RunAs from elevate_deploy.ps1.
# Pure ASCII to avoid Windows PowerShell 5.1 ANSI/GBK encoding issues.

[CmdletBinding()] param(
    [string]$Src = '',
    [string]$Dst = '',
    [switch]$IncludeCli
)
$ErrorActionPreference = 'Stop'

# 仓库根 = 本脚本所在目录的 parent；默认 Src / Dst 均自动派生
$repo = Split-Path -Parent $PSScriptRoot
if (-not $Src) { $Src = Join-Path $repo 'dist\ClaudeBackup' }
if (-not $Dst) { $Dst = Join-Path $env:ProgramFiles 'ClaudeBackup' }

# Write everything to a log file so the parent can see failures
$log = Join-Path $repo 'deploy_admin.log'
Start-Transcript -Path $log -Force | Out-Null
trap {
    Write-Host ("[FATAL] " + $_.Exception.Message)
    Write-Host $_.ScriptStackTrace
    Stop-Transcript | Out-Null
    exit 1
}

if (-not (Test-Path $Src)) {
    Write-Error ("Source not found: " + $Src)
    exit 1
}

if (-not (Test-Path $Dst)) {
    New-Item -ItemType Directory -Path $Dst -Force | Out-Null
}

# Kill running ClaudeBackup processes so robocopy can replace .exe / .dll
Get-Process -Name "ClaudeBackup", "ClaudeBackup-cli" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host ("Stopping running process PID=" + $_.Id + " " + $_.ProcessName)
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 800

# robocopy /MIR: mirror sync (delete stale, add new)
robocopy $Src $Dst /MIR /NFL /NDL /NJH /NJS /NC /NS /R:2 /W:1 | Out-Null
$rc = $LASTEXITCODE
# robocopy 0-7 = success, >=8 = failure
if ($rc -ge 8) {
    Write-Error ("robocopy failed, exit=" + $rc)
    exit 1
}

# Optional: also deploy CLI (onedir CLI carries its own _internal/)
if ($IncludeCli) {
    $cliSrc = Join-Path $repo 'dist\ClaudeBackup-cli'
    if (Test-Path $cliSrc) {
        $cliDst = Join-Path $Dst 'cli'
        if (-not (Test-Path $cliDst)) { New-Item -ItemType Directory -Path $cliDst -Force | Out-Null }
        robocopy $cliSrc $cliDst /MIR /NFL /NDL /NJH /NJS /NC /NS | Out-Null
    }
}

# Marker file for parent to verify success
$marker = Join-Path $Dst '.deployed'
("deployed at " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) | Out-File $marker -Encoding utf8 -Force

Write-Host ("[OK] Deployed to " + $Dst)
Stop-Transcript | Out-Null
exit 0

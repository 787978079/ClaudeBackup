@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\elevate_deploy.ps1"
echo.
echo [cmd] PowerShell return code = %errorlevel%
echo [cmd] Press any key to close...
pause >nul

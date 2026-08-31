@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Stop-CarbonLab.ps1"
pause
endlocal

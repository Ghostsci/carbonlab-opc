@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Check-CarbonLab.ps1"
pause
endlocal

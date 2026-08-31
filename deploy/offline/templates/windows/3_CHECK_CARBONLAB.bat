@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Check-CarbonLab.ps1"
set "exitCode=%ERRORLEVEL%"
if not "%CARBONLAB_NO_PAUSE%"=="1" pause
endlocal & exit /b %exitCode%

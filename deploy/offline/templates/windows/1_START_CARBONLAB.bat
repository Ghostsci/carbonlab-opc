@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-CarbonLab.ps1"
set "exitCode=%ERRORLEVEL%"
if not "%exitCode%"=="0" if not "%CARBONLAB_NO_PAUSE%"=="1" pause
endlocal & exit /b %exitCode%

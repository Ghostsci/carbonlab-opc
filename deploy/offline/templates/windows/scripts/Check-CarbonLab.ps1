. (Join-Path $PSScriptRoot "Common.ps1")

$root = Get-DemoRoot
$diagnostics = Join-Path $root "diagnostics"
New-Item -ItemType Directory -Force -Path $diagnostics | Out-Null
$output = Join-Path $diagnostics ("check-{0}.txt" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
Import-DemoEnvironment -Path (Join-Path $root "config\demo.env")
$compose = Get-ComposeArguments -Root $root

& {
    "CarbonLab offline demo diagnostics"
    "time=$((Get-Date).ToString('o'))"
    "architecture=$env:PROCESSOR_ARCHITECTURE"
    "docker=$(& docker.exe --version 2>&1)"
    "compose=$(& docker.exe compose version 2>&1)"
    "`n--- containers ---"
    & docker.exe @compose ps 2>&1
    "`n--- backend health ---"
    try { Invoke-RestMethod -Uri "http://127.0.0.1:$env:BACKEND_PORT/api/health" -TimeoutSec 3 | ConvertTo-Json -Depth 5 } catch { $_ }
    "`n--- recent backend logs ---"
    & docker.exe @compose logs --tail=120 backend 2>&1
} | Tee-Object -FilePath $output

Write-Host "Diagnostics saved to: $output"

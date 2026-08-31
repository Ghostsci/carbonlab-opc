. (Join-Path $PSScriptRoot "Common.ps1")

$root = Get-DemoRoot
$diagnostics = Join-Path $root "diagnostics"
New-Item -ItemType Directory -Force -Path $diagnostics | Out-Null
$output = Join-Path $diagnostics ("check-{0}.txt" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
Import-DemoEnvironment -Path (Join-Path $root "config\demo.env")
$compose = Get-ComposeArguments -Root $root
$docker = $null
$dockerError = $null
try { $docker = Resolve-DockerExecutable } catch { $dockerError = $_.Exception.Message }

& {
    "CarbonLab offline demo diagnostics"
    "time=$((Get-Date).ToString('o'))"
    "architecture=$env:PROCESSOR_ARCHITECTURE"
    "docker_path=$(if ($docker) { $docker } else { 'not_found' })"
    "docker=$(if ($docker) { & $docker --version 2>&1 } else { $dockerError })"
    "compose=$(if ($docker) { & $docker compose version 2>&1 } else { 'unavailable' })"
    "`n--- containers ---"
    if ($docker) { & $docker @compose ps 2>&1 } else { "Docker unavailable" }
    "`n--- backend health ---"
    try { Invoke-RestMethod -Uri "http://127.0.0.1:$env:BACKEND_PORT/api/health" -TimeoutSec 3 | ConvertTo-Json -Depth 5 } catch { $_ }
    "`n--- recent backend logs ---"
    if ($docker) { & $docker @compose logs --tail=120 backend 2>&1 } else { "Docker unavailable" }
} | Tee-Object -FilePath $output

Write-Host "Diagnostics saved to: $output"

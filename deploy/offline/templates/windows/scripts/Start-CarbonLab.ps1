. (Join-Path $PSScriptRoot "Common.ps1")

try {
    $root = Get-DemoRoot
    Import-DemoEnvironment -Path (Join-Path $root "config\demo.env")
    $hostArchitecture = if ($env:PROCESSOR_ARCHITEW6432) {
        $env:PROCESSOR_ARCHITEW6432
    } else {
        $env:PROCESSOR_ARCHITECTURE
    }
    if ($hostArchitecture -ne "AMD64") {
        throw "This package targets a Windows x64 computer. Detected: $hostArchitecture"
    }
    Wait-DockerDesktop
    Import-OfflineImages -Root $root

    $compose = Get-ComposeArguments -Root $root
    Write-Host "Starting CarbonLab offline demo..."
    & docker.exe @compose up -d
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

    $healthUrl = "http://127.0.0.1:$env:BACKEND_PORT/api/health"
    for ($index = 0; $index -lt 120; $index++) {
        try {
            $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3
            if ($health.status -eq "ok") {
                $frontendUrl = "http://127.0.0.1:$env:FRONTEND_PORT/login"
                Write-Host "CarbonLab is ready: $frontendUrl"
                Write-Host "Click '一键进入演示' on the login page."
                Start-Process $frontendUrl
                exit 0
            }
        } catch { }
        Start-Sleep -Seconds 2
    }
    throw "Backend health check timed out. Run 3_CHECK_CARBONLAB.bat."
} catch {
    Write-Error $_
    exit 1
}

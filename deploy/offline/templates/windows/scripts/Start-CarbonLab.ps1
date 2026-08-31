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
    $docker = Resolve-DockerExecutable
    Wait-DockerDesktop -DockerExe $docker

    $healthUrl = "http://127.0.0.1:$env:BACKEND_PORT/api/health"
    $frontendUrl = "http://127.0.0.1:$env:FRONTEND_PORT/login"
    try {
        $existingHealth = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3
        $existingFrontend = Invoke-WebRequest -UseBasicParsing -Uri $frontendUrl -TimeoutSec 3
        if ($existingHealth.status -eq "ok" -and $existingFrontend.StatusCode -eq 200) {
            Write-Host "CarbonLab is already running: $frontendUrl"
            if ($env:CARBONLAB_NO_BROWSER -ne "1") { Start-Process $frontendUrl }
            exit 0
        }
    } catch { }

    Import-OfflineImages -Root $root -DockerExe $docker

    $compose = Get-ComposeArguments -Root $root
    Write-Host "Starting CarbonLab offline demo..."
    & $docker @compose up -d
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

    for ($index = 0; $index -lt 120; $index++) {
        try {
            $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3
            if ($health.status -eq "ok") {
                Write-Host "CarbonLab is ready: $frontendUrl"
                Write-Host "Click '一键进入演示' on the login page."
                if ($env:CARBONLAB_NO_BROWSER -ne "1") { Start-Process $frontendUrl }
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

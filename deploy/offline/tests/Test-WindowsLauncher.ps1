$ErrorActionPreference = "Stop"

function Assert-True {
    param(
        [Parameter(Mandatory = $true)][bool]$Condition,
        [Parameter(Mandatory = $true)][string]$Message
    )
    if (-not $Condition) { throw $Message }
}

function Assert-CrlfOnly {
    param([Parameter(Mandatory = $true)][string]$Path)
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    for ($index = 0; $index -lt $bytes.Length; $index++) {
        if ($bytes[$index] -eq 10 -and ($index -eq 0 -or $bytes[$index - 1] -ne 13)) {
            throw "File is not CRLF-only: $Path"
        }
    }
}

function Invoke-BatchFile {
    param([Parameter(Mandatory = $true)][string]$Path)
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $env:ComSpec /d /c "call `"$Path`"" 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = ($output | Out-String)
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$templateRoot = Join-Path $repoRoot "deploy\offline\templates\windows"
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "CarbonLab Windows Launcher 中文路径 {0}" -f [guid]::NewGuid().ToString("N")
)
$packageRoot = Join-Path $testRoot "零碳云 Windows 离线包"
$serverJob = $null
$serverPidFile = Join-Path $testRoot "server.pid"

try {
    New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null
    Copy-Item -Path (Join-Path $templateRoot "*") -Destination $packageRoot -Recurse -Force

    $scripts = Get-ChildItem -LiteralPath (Join-Path $packageRoot "scripts") -Filter "*.ps1"
    foreach ($script in $scripts) {
        $tokens = $null
        $parseErrors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile(
            $script.FullName,
            [ref]$tokens,
            [ref]$parseErrors
        )
        Assert-True -Condition ($parseErrors.Count -eq 0) -Message (
            "PowerShell parse failure in {0}: {1}" -f $script.Name, ($parseErrors | Out-String)
        )
        Assert-CrlfOnly -Path $script.FullName
        $bytes = [System.IO.File]::ReadAllBytes($script.FullName)
        Assert-True -Condition (
            $bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191
        ) -Message "PowerShell script must keep its UTF-8 BOM for Windows PowerShell 5.1: $($script.Name)"
    }
    foreach ($batch in Get-ChildItem -LiteralPath $packageRoot -Filter "*.bat") {
        Assert-CrlfOnly -Path $batch.FullName
    }

    New-Item -ItemType Directory -Force -Path (Join-Path $packageRoot "config") | Out-Null
    @"
# Synthetic CI-only values.
CARBONLAB_PLATFORM=linux/amd64
CARBONLAB_IMAGE_TAG=windows-launcher-smoke
FRONTEND_PORT=35173
BACKEND_PORT=38000
POSTGRES_PASSWORD=synthetic
POSTGRES_APP_USER=synthetic
POSTGRES_APP_PASSWORD=synthetic
JWT_SECRET=synthetic
CARBONLAB_DEMO_PASSWORD=synthetic
DEMO_FRONTEND_EMAIL=demo@example.invalid
DEMO_FRONTEND_PASSWORD=synthetic
"@ | Set-Content -LiteralPath (Join-Path $packageRoot "config\demo.env") -Encoding UTF8
    "services: {}" | Set-Content -LiteralPath (Join-Path $packageRoot "compose.offline.yml") -Encoding UTF8

    $fakeDocker = Join-Path $testRoot "Docker CLI with spaces\docker.exe"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $fakeDocker) | Out-Null
    $fakeDockerSource = @'
using System;
using System.IO;

public static class FakeDocker
{
    public static int Main(string[] args)
    {
        string log = Environment.GetEnvironmentVariable("FAKE_DOCKER_LOG");
        if (!String.IsNullOrWhiteSpace(log))
        {
            File.AppendAllText(log, String.Join("|", args) + Environment.NewLine);
        }
        if (args.Length > 0 && args[0] == "--version")
        {
            Console.WriteLine("Docker version 28.3.3, build carbonlab-ci");
        }
        else if (args.Length > 1 && args[0] == "compose" && args[1] == "version")
        {
            Console.WriteLine("Docker Compose version v2.39.0");
        }
        return 0;
    }
}
'@
    Add-Type -TypeDefinition $fakeDockerSource -Language CSharp -OutputAssembly $fakeDocker -OutputType ConsoleApplication

    $serverScript = Join-Path $testRoot "health_server.py"
    @'
import http.server
import json
import sys
import threading
import time

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/health"):
            payload = json.dumps({"status": "ok"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        else:
            payload = b"<html><body>CarbonLab login</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self, *_):
        pass

servers = [http.server.ThreadingHTTPServer(("127.0.0.1", int(port)), Handler) for port in sys.argv[1:]]
for server in servers:
    threading.Thread(target=server.serve_forever, daemon=True).start()
while True:
    time.sleep(60)
'@ | Set-Content -LiteralPath $serverScript -Encoding UTF8

    $dockerLog = Join-Path $testRoot "docker.log"
    $env:CARBONLAB_DOCKER_EXE = $fakeDocker
    $env:CARBONLAB_NO_BROWSER = "1"
    $env:CARBONLAB_NO_PAUSE = "1"
    $env:CARBONLAB_PROJECT_NAME = "carbonlab_windows_launcher_ci"
    $env:FAKE_DOCKER_LOG = $dockerLog
    $env:PROCESSOR_ARCHITECTURE = "AMD64"
    Remove-Item Env:PROCESSOR_ARCHITEW6432 -ErrorAction SilentlyContinue

    $python = (Get-Command python.exe -ErrorAction Stop).Source
    $serverJob = Start-Job -ScriptBlock {
        param($Python, $Script, $PidFile)
        Start-Sleep -Seconds 2
        $process = Start-Process -FilePath $Python -ArgumentList @("`"$Script`"", "35173", "38000") -PassThru -WindowStyle Hidden
        Set-Content -LiteralPath $PidFile -Value $process.Id -Encoding ASCII
        Wait-Process -Id $process.Id
    } -ArgumentList $python, $serverScript, $serverPidFile

    $start = Invoke-BatchFile -Path (Join-Path $packageRoot "1_START_CARBONLAB.bat")
    Assert-True -Condition ($start.ExitCode -eq 0) -Message "Start BAT failed: $($start.Output)"
    Assert-True -Condition (Test-Path -LiteralPath $dockerLog) -Message "Fake Docker was not invoked."
    $dockerCalls = Get-Content -LiteralPath $dockerLog
    Assert-True -Condition (($dockerCalls -join "`n") -match "compose\|.*\|up\|-d") -Message (
        "Start BAT did not invoke docker compose up -d. Calls:`n{0}" -f ($dockerCalls -join "`n")
    )
    Assert-True -Condition ($start.Output -match "CarbonLab is ready") -Message "Start BAT did not reach ready state."

    $upCountBefore = @($dockerCalls | Where-Object { $_ -match "compose\|.*\|up\|-d" }).Count
    $startAgain = Invoke-BatchFile -Path (Join-Path $packageRoot "1_START_CARBONLAB.bat")
    Assert-True -Condition ($startAgain.ExitCode -eq 0) -Message "Second start failed: $($startAgain.Output)"
    $upCountAfter = @(Get-Content -LiteralPath $dockerLog | Where-Object { $_ -match "compose\|.*\|up\|-d" }).Count
    Assert-True -Condition ($upCountAfter -eq $upCountBefore) -Message "Healthy existing instance was not reused."

    $check = Invoke-BatchFile -Path (Join-Path $packageRoot "3_CHECK_CARBONLAB.bat")
    Assert-True -Condition ($check.ExitCode -eq 0) -Message "Check BAT failed: $($check.Output)"
    $diagnostic = Get-ChildItem -LiteralPath (Join-Path $packageRoot "diagnostics") -Filter "check-*.txt" |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Assert-True -Condition ($null -ne $diagnostic) -Message "Check BAT did not create a diagnostic report."
    $diagnosticText = Get-Content -LiteralPath $diagnostic.FullName -Raw
    Assert-True -Condition ($diagnosticText -match ([regex]::Escape($fakeDocker))) -Message "Diagnostic report omitted Docker path."
    Assert-True -Condition ($diagnosticText -match '"status"\s*:\s*"ok"') -Message "Diagnostic report omitted backend health."

    $stop = Invoke-BatchFile -Path (Join-Path $packageRoot "2_STOP_CARBONLAB.bat")
    Assert-True -Condition ($stop.ExitCode -eq 0) -Message "Stop BAT failed: $($stop.Output)"
    Assert-True -Condition (((Get-Content -LiteralPath $dockerLog) -join "`n") -match "\|down$") -Message "Stop BAT did not invoke compose down."

    $env:PROCESSOR_ARCHITECTURE = "ARM64"
    $badArchitecture = Invoke-BatchFile -Path (Join-Path $packageRoot "1_START_CARBONLAB.bat")
    Assert-True -Condition ($badArchitecture.ExitCode -ne 0) -Message "BAT wrapper swallowed the PowerShell failure exit code."

    Write-Host "WINDOWS_LAUNCHER_SMOKE_PASS"
    Write-Host "package_path=$packageRoot"
    Write-Host "docker_path=$fakeDocker"
    Write-Host "diagnostic_path=$($diagnostic.FullName)"
} finally {
    if (Test-Path -LiteralPath $serverPidFile) {
        $serverPid = Get-Content -LiteralPath $serverPidFile -ErrorAction SilentlyContinue
        if ($serverPid) { Stop-Process -Id ([int]$serverPid) -Force -ErrorAction SilentlyContinue }
    }
    if ($serverJob) {
        Stop-Job -Job $serverJob -ErrorAction SilentlyContinue
        Remove-Job -Job $serverJob -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}

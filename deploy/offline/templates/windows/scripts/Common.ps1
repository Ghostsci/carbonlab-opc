$ErrorActionPreference = "Stop"

function Import-DemoEnvironment {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing environment file: $Path"
    }
    Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $pair = $line -split "=", 2
            if ($pair.Count -eq 2) {
                [Environment]::SetEnvironmentVariable($pair[0].Trim(), $pair[1], "Process")
            }
        }
    }
}

function Get-DemoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-ComposeArguments {
    param([Parameter(Mandatory = $true)][string]$Root)
    $projectName = if ($env:CARBONLAB_PROJECT_NAME) {
        $env:CARBONLAB_PROJECT_NAME
    } else {
        "carbonlab_competition_demo"
    }
    return @(
        "compose",
        "--env-file", (Join-Path $Root "config\demo.env"),
        "-f", (Join-Path $Root "compose.offline.yml"),
        "-p", $projectName
    )
}

function Resolve-DockerExecutable {
    $candidates = [System.Collections.Generic.List[string]]::new()
    if ($env:CARBONLAB_DOCKER_EXE) {
        $candidates.Add($env:CARBONLAB_DOCKER_EXE)
    }
    $command = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($command) {
        $commandPath = if ($command.Source) { $command.Source } else { $command.Path }
        if ($commandPath) { $candidates.Add($commandPath) }
    }
    if ($env:ProgramFiles) {
        $candidates.Add((Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"))
    }
    if ($env:LOCALAPPDATA) {
        $candidates.Add((Join-Path $env:LOCALAPPDATA "Programs\Docker\Docker\resources\bin\docker.exe"))
        $candidates.Add((Join-Path $env:LOCALAPPDATA "Docker\resources\bin\docker.exe"))
    }
    if ($env:USERPROFILE) {
        $candidates.Add((Join-Path $env:USERPROFILE ".docker\bin\docker.exe"))
    }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "Docker CLI was not found. Install Docker Desktop before going offline."
}

function Wait-DockerDesktop {
    param([Parameter(Mandatory = $true)][string]$DockerExe)

    & $DockerExe info *> $null
    if ($LASTEXITCODE -eq 0) { return }

    $dockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path -LiteralPath $dockerDesktop)) {
        throw "Docker Desktop is not installed. Install it before going offline."
    }
    Start-Process -FilePath $dockerDesktop | Out-Null
    Write-Host "Starting Docker Desktop..."
    for ($index = 0; $index -lt 120; $index++) {
        Start-Sleep -Seconds 2
        & $DockerExe info *> $null
        if ($LASTEXITCODE -eq 0) { return }
    }
    throw "Docker Desktop did not become ready within four minutes."
}

function Import-OfflineImages {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$DockerExe
    )
    $appImage = "carbonlab-offline-backend:$env:CARBONLAB_IMAGE_TAG"
    $databaseImage = "carbonlab-offline-postgres-slim:$env:CARBONLAB_IMAGE_TAG"
    & $DockerExe image inspect $appImage *> $null
    $appReady = $LASTEXITCODE -eq 0
    & $DockerExe image inspect $databaseImage *> $null
    $databaseReady = $LASTEXITCODE -eq 0
    if ($appReady -and $databaseReady) { return }

    $archive = Join-Path $Root "images\carbonlab-offline-images.tar.gz"
    if (-not (Test-Path -LiteralPath $archive)) {
        throw "Missing offline image archive: $archive"
    }
    $temporaryTar = Join-Path $env:TEMP "carbonlab-offline-images-$PID.tar"
    Write-Host "First start: importing offline images. This can take several minutes..."
    try {
        $input = [System.IO.File]::OpenRead($archive)
        try {
            $gzip = [System.IO.Compression.GzipStream]::new(
                $input,
                [System.IO.Compression.CompressionMode]::Decompress
            )
            try {
                $output = [System.IO.File]::Create($temporaryTar)
                try { $gzip.CopyTo($output) } finally { $output.Dispose() }
            } finally { $gzip.Dispose() }
        } finally { $input.Dispose() }
        & $DockerExe load --input $temporaryTar
        if ($LASTEXITCODE -ne 0) { throw "docker load failed" }
    } finally {
        Remove-Item -LiteralPath $temporaryTar -Force -ErrorAction SilentlyContinue
    }
}

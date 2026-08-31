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
    return @(
        "compose",
        "--env-file", (Join-Path $Root "config\demo.env"),
        "-f", (Join-Path $Root "compose.offline.yml"),
        "-p", "carbonlab_competition_demo"
    )
}

function Wait-DockerDesktop {
    if (Get-Command docker.exe -ErrorAction SilentlyContinue) {
        & docker.exe info *> $null
        if ($LASTEXITCODE -eq 0) { return }
    }

    $dockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path -LiteralPath $dockerDesktop)) {
        throw "Docker Desktop is not installed. Install it before going offline."
    }
    Start-Process -FilePath $dockerDesktop | Out-Null
    Write-Host "Starting Docker Desktop..."
    for ($index = 0; $index -lt 120; $index++) {
        Start-Sleep -Seconds 2
        & docker.exe info *> $null
        if ($LASTEXITCODE -eq 0) { return }
    }
    throw "Docker Desktop did not become ready within four minutes."
}

function Import-OfflineImages {
    param([Parameter(Mandatory = $true)][string]$Root)
    $appImage = "carbonlab-offline-backend:$env:CARBONLAB_IMAGE_TAG"
    $databaseImage = "carbonlab-offline-postgres-slim:$env:CARBONLAB_IMAGE_TAG"
    & docker.exe image inspect $appImage *> $null
    $appReady = $LASTEXITCODE -eq 0
    & docker.exe image inspect $databaseImage *> $null
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
        & docker.exe load --input $temporaryTar
        if ($LASTEXITCODE -ne 0) { throw "docker load failed" }
    } finally {
        Remove-Item -LiteralPath $temporaryTar -Force -ErrorAction SilentlyContinue
    }
}

. (Join-Path $PSScriptRoot "Common.ps1")

$root = Get-DemoRoot
Import-DemoEnvironment -Path (Join-Path $root "config\demo.env")
$compose = Get-ComposeArguments -Root $root
& docker.exe @compose down
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "CarbonLab stopped. Demo data is preserved."

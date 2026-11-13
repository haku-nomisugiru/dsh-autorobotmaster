$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
$version = (Get-Content -LiteralPath (Join-Path $studioRoot 'package.json') -Raw | ConvertFrom-Json).version
$packageName = "RoboMaster-Studio-v$version-win-x64"
$packageRoot = Join-Path $studioRoot "release\$packageName"
$exe = Join-Path $studioRoot 'src-tauri\target\release\robomaster-studio.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw '请先运行 build.ps1。' }
New-Item -ItemType Directory -Force $packageRoot | Out-Null
Copy-Item -LiteralPath $exe -Destination (Join-Path $packageRoot 'RoboMasterStudio.exe') -Force
Copy-Item -LiteralPath (Join-Path $studioRoot 'THIRD_PARTY_NOTICES.md') -Destination $packageRoot -Force
Copy-Item -LiteralPath (Join-Path $studioRoot 'docs\QUICKSTART.md') -Destination (Join-Path $packageRoot '快速开始.md') -Force
Copy-Item -LiteralPath (Join-Path $studioRoot 'docs\HERMES.md') -Destination $packageRoot -Force
Copy-Item -LiteralPath (Join-Path $studioRoot 'docs') -Destination $packageRoot -Recurse -Force
$launcher = @'
@echo off
set "ROBOMASTER_STUDIO_DATA_DIR=%~dp0data"
start "" "%~dp0RoboMasterStudio.exe"
'@
[IO.File]::WriteAllText((Join-Path $packageRoot 'Start-Studio.cmd'), $launcher, [Text.Encoding]::ASCII)
$packageExe = Join-Path $packageRoot 'RoboMasterStudio.exe'
$digest = (Get-FileHash -LiteralPath $packageExe -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText((Join-Path $packageRoot 'SHA256SUMS.txt'), "$digest  RoboMasterStudio.exe`n", [Text.Encoding]::ASCII)
Push-Location $studioRoot
try { python scripts\collect-licenses.py (Join-Path $packageRoot 'DEPENDENCY_LICENSES.txt'); if ($LASTEXITCODE) { throw 'License collection failed' } } finally { Pop-Location }
$archive = Join-Path $studioRoot "release\$packageName.zip"
# The portable installation may already contain the user's data. Stage only release files.
$stagingParent = Join-Path $studioRoot ('.local\package-stage-' + [guid]::NewGuid().ToString('N'))
$stagingRoot = Join-Path $stagingParent $packageName
New-Item -ItemType Directory -Force $stagingRoot | Out-Null
foreach ($name in @('RoboMasterStudio.exe', '快速开始.md', 'THIRD_PARTY_NOTICES.md', 'HERMES.md', 'Start-Studio.cmd', 'SHA256SUMS.txt', 'DEPENDENCY_LICENSES.txt', 'docs')) {
  Copy-Item -LiteralPath (Join-Path $packageRoot $name) -Destination $stagingRoot -Recurse -Force
}
Compress-Archive -LiteralPath $stagingRoot -DestinationPath $archive -Force
[pscustomobject]@{ Archive=$archive; Bytes=(Get-Item -LiteralPath $archive).Length; SHA256=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() } | ConvertTo-Json

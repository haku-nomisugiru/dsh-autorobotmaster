$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
$version = (Get-Content -LiteralPath (Join-Path $studioRoot 'package.json') -Raw | ConvertFrom-Json).version
$source = Join-Path $studioRoot "release\RoboMaster-Studio-Codex-v$version-win-x64"
$name = "RoboMaster-Studio-API-v$version-win-x64"
$packageRoot = Join-Path $studioRoot "release\$name"
if (-not (Test-Path -LiteralPath (Join-Path $source 'RoboMasterStudio.exe'))) { throw '请先运行 package-integrations.ps1 生成对应版本的 Codex 桌面包。' }
New-Item -ItemType Directory -Force $packageRoot | Out-Null
foreach ($file in @('RoboMasterStudio.exe','LICENSE','THIRD_PARTY_NOTICES.md','DEPENDENCY_LICENSES.txt','SHA256SUMS.txt')) {
  Copy-Item -LiteralPath (Join-Path $source $file) -Destination $packageRoot -Force
}
Copy-Item -LiteralPath (Join-Path $studioRoot 'docs\API.md') -Destination (Join-Path $packageRoot '使用说明.md') -Force
$launcher = @'
@echo off
set "ROBOMASTER_STUDIO_DATA_DIR=%~dp0data"
set "ROBOMASTER_STUDIO_PROVIDER=api"
start "" "%~dp0RoboMasterStudio.exe"
'@
[IO.File]::WriteAllText((Join-Path $packageRoot 'Start-API-Studio.cmd'), $launcher, [Text.Encoding]::ASCII)
$stage = Join-Path $studioRoot ('.local\api-package-' + [guid]::NewGuid().ToString('N'))
$stagingRoot = Join-Path $stage $name
New-Item -ItemType Directory -Force $stagingRoot | Out-Null
foreach ($file in @('RoboMasterStudio.exe','Start-API-Studio.cmd','使用说明.md','LICENSE','THIRD_PARTY_NOTICES.md','DEPENDENCY_LICENSES.txt','SHA256SUMS.txt')) {
  Copy-Item -LiteralPath (Join-Path $packageRoot $file) -Destination $stagingRoot
}
$archive = Join-Path $studioRoot "release\$name.zip"
Compress-Archive -LiteralPath $stagingRoot -DestinationPath $archive -Force
$apiHash = (Get-FileHash -LiteralPath (Join-Path $packageRoot 'RoboMasterStudio.exe') -Algorithm SHA256).Hash
$codexHash = (Get-FileHash -LiteralPath (Join-Path $source 'RoboMasterStudio.exe') -Algorithm SHA256).Hash
if ($apiHash -ne $codexHash) { throw 'API 与 Codex 版本的程序内容不一致。' }
[pscustomobject]@{Name="$name.zip";Bytes=(Get-Item -LiteralPath $archive).Length;SHA256=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant();ExeSHA256=$apiHash.ToLowerInvariant()} | ConvertTo-Json

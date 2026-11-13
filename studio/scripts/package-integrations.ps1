$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
$version = (Get-Content -LiteralPath (Join-Path $studioRoot 'package.json') -Raw | ConvertFrom-Json).version
$name = "RoboMaster-Studio-Codex-v$version-win-x64"
$packageRoot = Join-Path $studioRoot "release\$name"
$exe = Join-Path $studioRoot 'src-tauri\target\release\robomaster-studio.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw '请先运行 build.ps1。' }
New-Item -ItemType Directory -Force $packageRoot | Out-Null
Copy-Item -LiteralPath $exe -Destination (Join-Path $packageRoot 'RoboMasterStudio.exe') -Force
Copy-Item -LiteralPath (Join-Path $studioRoot 'docs\INTEGRATIONS.md') -Destination (Join-Path $packageRoot '使用说明.md') -Force
Copy-Item -LiteralPath (Join-Path $studioRoot 'THIRD_PARTY_NOTICES.md') -Destination $packageRoot -Force
Copy-Item -LiteralPath (Join-Path $studioRoot 'LICENSE') -Destination $packageRoot -Force
$launcher = @'
@echo off
set "ROBOMASTER_STUDIO_DATA_DIR=%~dp0data"
set "ROBOMASTER_STUDIO_PROVIDER=codex"
start "" "%~dp0RoboMasterStudio.exe"
'@
[IO.File]::WriteAllText((Join-Path $packageRoot 'Start-Codex-Studio.cmd'), $launcher, [Text.Encoding]::ASCII)
python (Join-Path $studioRoot 'scripts\collect-licenses.py') (Join-Path $packageRoot 'DEPENDENCY_LICENSES.txt')
if ($LASTEXITCODE) { throw 'License collection failed' }
$digest = (Get-FileHash -LiteralPath (Join-Path $packageRoot 'RoboMasterStudio.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText((Join-Path $packageRoot 'SHA256SUMS.txt'), "$digest  RoboMasterStudio.exe`n", [Text.Encoding]::ASCII)
# Never archive the portable application's user-created data directory.
$stage = Join-Path $studioRoot ('.local\integration-package-' + [guid]::NewGuid().ToString('N'))
$stagingRoot = Join-Path $stage $name
New-Item -ItemType Directory -Force $stagingRoot | Out-Null
foreach ($file in @('RoboMasterStudio.exe','Start-Codex-Studio.cmd','使用说明.md','LICENSE','THIRD_PARTY_NOTICES.md','DEPENDENCY_LICENSES.txt','SHA256SUMS.txt')) {
  Copy-Item -LiteralPath (Join-Path $packageRoot $file) -Destination $stagingRoot
}
Compress-Archive -LiteralPath $stagingRoot -DestinationPath (Join-Path $studioRoot "release\$name.zip") -Force
$pluginName = "RoboMaster-Studio-DSH-v$version"
$pluginRoot = Join-Path $studioRoot "release\$pluginName"
New-Item -ItemType Directory -Force $pluginRoot | Out-Null
foreach ($file in @('package.json','index.js','service.js','mcp.js','workflow.json','client.js','cordis.patch.yml','icon.svg','README.md','locale')) {
  Copy-Item -LiteralPath (Join-Path $studioRoot "plugins\dsh\$file") -Destination $pluginRoot -Recurse -Force
}
$pluginStage = Join-Path $stage $pluginName
Copy-Item -LiteralPath (Join-Path $studioRoot 'LICENSE') -Destination $pluginRoot -Force
New-Item -ItemType Directory -Force $pluginStage | Out-Null
foreach ($file in @('package.json','index.js','service.js','mcp.js','workflow.json','client.js','cordis.patch.yml','icon.svg','README.md','locale','LICENSE')) {
  Copy-Item -LiteralPath (Join-Path $pluginRoot $file) -Destination $pluginStage -Recurse -Force
}
Compress-Archive -LiteralPath $pluginStage -DestinationPath (Join-Path $studioRoot "release\$pluginName.zip") -Force
Get-FileHash -LiteralPath (Join-Path $studioRoot "release\$name.zip"),(Join-Path $studioRoot "release\$pluginName.zip") -Algorithm SHA256 | Select-Object Path,Hash | ConvertTo-Json

$ErrorActionPreference = 'Stop'
$studioExe = Join-Path $PSScriptRoot 'src-tauri\target\release\robomaster-studio.exe'
if (-not (Test-Path $studioExe)) { throw '请先执行 .\build.ps1 构建桌面程序。' }
Start-Process -FilePath $studioExe -WorkingDirectory $PSScriptRoot -WindowStyle Hidden

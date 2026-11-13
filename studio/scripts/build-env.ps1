$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
$env:CARGO_HOME = Join-Path $studioRoot '.local\cargo'
$env:npm_config_cache = Join-Path $studioRoot '.local\npm-cache'
$vswherePath = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
$toolchainRoot = if (Test-Path $vswherePath) { & $vswherePath -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath } else { $null }
if (-not $toolchainRoot -and (Test-Path 'D:\BuildTools\VC\Tools\MSVC')) { $toolchainRoot = 'D:\BuildTools' }
if ($toolchainRoot) {
  $vcToolchain = Get-ChildItem (Join-Path $toolchainRoot 'VC\Tools\MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1
  $kitBase = 'C:\Program Files (x86)\Windows Kits\10'
  $kitVersion = Get-ChildItem (Join-Path $kitBase 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1
  $vcBin = Join-Path $vcToolchain.FullName 'bin\Hostx64\x64'
  $env:PATH = "$vcBin;$(Join-Path $kitBase "bin\$($kitVersion.Name)\x64");$env:PATH"
  $env:LIB = "$(Join-Path $vcToolchain.FullName 'lib\x64');$(Join-Path $kitVersion.FullName 'um\x64');$(Join-Path $kitVersion.FullName 'ucrt\x64')"
  $env:INCLUDE = "$(Join-Path $vcToolchain.FullName 'include');$(Join-Path $kitBase "Include\$($kitVersion.Name)\ucrt");$(Join-Path $kitBase "Include\$($kitVersion.Name)\shared");$(Join-Path $kitBase "Include\$($kitVersion.Name)\um")"
  $env:CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER = Join-Path $vcBin 'link.exe'
  $env:CC = Join-Path $vcBin 'cl.exe'
  $env:CXX = Join-Path $vcBin 'cl.exe'
}

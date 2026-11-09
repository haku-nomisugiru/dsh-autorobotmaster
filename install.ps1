param([switch]$Elevated)
$ErrorActionPreference='Stop'
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  if($Elevated) { throw '无法获得 Windows 管理员权限。' }
  $shell=(Get-Process -Id $PID).Path
  $child=Start-Process -FilePath $shell -ArgumentList @('-NoProfile','-File',('"'+$PSCommandPath+'"'),'-Elevated') -Verb RunAs -WindowStyle Hidden -Wait -PassThru
  if($child.ExitCode -ne 0) { throw '管理员注册未完成，请检查 data\install-api-v1.0.0.log。' }
  exit 0
}
$build=Join-Path $PSScriptRoot 'build-v1.1.0'
$dll=Join-Path $build 'RoboMaster.Workbench.dll'
if(-not (Test-Path -LiteralPath $dll)) { & (Join-Path $PSScriptRoot 'build.ps1') }
$data=Join-Path $PSScriptRoot 'data'
New-Item -ItemType Directory -Path $data -Force | Out-Null
$regasm=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe'
$log=Join-Path $data 'install-api-v1.0.0.log'
& $regasm $dll /codebase ('/tlb:'+(Join-Path $build 'RoboMaster.Workbench.tlb')) 2>&1 | Tee-Object -FilePath $log
if($LASTEXITCODE -ne 0) { throw 'API版注册失败。请检查 data\install-api-v1.0.0.log。' }
Write-Output '已注册 RoboMaster 机械设计工作台 API版 v1.0.0。可在 SolidWorks 工具 > 加载项中启用。'

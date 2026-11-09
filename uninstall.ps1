param([switch]$Elevated)
$ErrorActionPreference='Stop'
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  if($Elevated) { throw '无法获得 Windows 管理员权限。' }
  $shell=(Get-Process -Id $PID).Path
  $child=Start-Process -FilePath $shell -ArgumentList @('-NoProfile','-File',('"'+$PSCommandPath+'"'),'-Elevated') -Verb RunAs -WindowStyle Hidden -Wait -PassThru
  if($child.ExitCode -ne 0) { throw '取消注册未完成，请使用管理员 PowerShell 重新运行 uninstall.ps1。' }
  exit 0
}
$build=Join-Path $PSScriptRoot 'build-v1.1.0'
$dll=Join-Path $build 'RoboMaster.Workbench.dll'
if(-not (Test-Path -LiteralPath $dll)) { throw 'API版程序集不存在，无法调用原生取消注册。' }
$regasm=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe'
& $regasm $dll /unregister ('/tlb:'+(Join-Path $build 'RoboMaster.Workbench.tlb'))
if($LASTEXITCODE -ne 0) { throw '取消注册失败，请先在 SolidWorks 卸载插件后重试。' }
Write-Output 'API版插件注册已移除；源码、模型、密钥配置和历史数据均保留。'

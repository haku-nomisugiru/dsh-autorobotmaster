param([switch]$Preview,[ValidateRange(340,1600)][int]$Width=460,[switch]$Wait)
$ErrorActionPreference='Stop'
$exe=Join-Path $PSScriptRoot 'build-v1.1.0\RoboMaster.Workbench.exe'
if(-not (Test-Path -LiteralPath $exe)) { & (Join-Path $PSScriptRoot 'build.ps1') }
$arguments=@('--width',[string]$Width)
if($Preview) { $arguments+='--preview' }
$parameters=@{FilePath=$exe;ArgumentList=$arguments;WindowStyle='Normal';WorkingDirectory=$PSScriptRoot;PassThru=$true}
if($Wait) { $parameters.Wait=$true }
$process=Start-Process @parameters
if($Wait -and $process.ExitCode -ne 0) { throw 'API版工作台窗口启动失败，请运行 diagnose.ps1。' }

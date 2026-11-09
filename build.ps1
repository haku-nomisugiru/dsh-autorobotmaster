param([string]$SolidWorksApiDir='D:\SOLIDWORKS\api\redist',[string]$Compiler,[string]$OutputDirectory="build-v1.1.0")
$ErrorActionPreference='Stop'
$taskRoot=$PSScriptRoot
if([string]::IsNullOrWhiteSpace($Compiler)) {
  $Compiler='D:\BuildTools\MSBuild\Current\Bin\Roslyn\csc.exe'
  if(-not (Test-Path -LiteralPath $Compiler)) { $found=Get-Command csc.exe -ErrorAction SilentlyContinue; if($found) { $Compiler=$found.Source } }
}
if(-not (Test-Path -LiteralPath $Compiler)) { throw '未找到 Roslyn C# 编译器。请用 -Compiler 指定 Visual Studio Build Tools 的 csc.exe。' }
foreach($name in @('SolidWorks.Interop.sldworks.dll','SolidWorks.Interop.swconst.dll','SolidWorks.Interop.swpublished.dll')) {
  if(-not (Test-Path -LiteralPath (Join-Path $SolidWorksApiDir $name))) { throw ('缺少 SolidWorks API 引用：'+$name+'。请用 -SolidWorksApiDir 指定 api\redist。') }
}
$build=Join-Path $taskRoot $OutputDirectory
New-Item -ItemType Directory -Path $build -Force | Out-Null
foreach($name in @('RoboMaster.Workbench.dll','RoboMaster.Workbench.exe')) {
  $target=Join-Path $build $name
  if(Test-Path -LiteralPath $target) {
    try { $probe=[IO.File]::Open($target,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None); $probe.Dispose() }
    catch { throw ('目标文件正在被占用，未覆盖：'+$target+'。请先关闭该版本的预览或在 SolidWorks 卸载该版本后重试。') }
  }
}
$key=Join-Path $build 'RoboMaster.Workbench.snk'
if(-not (Test-Path -LiteralPath $key)) {
  $previousKey=$null
  foreach($directory in @('build-v0.2.1','build-v0.2.0','build-v0.1.1','build')) {
    $candidate=Join-Path (Join-Path $taskRoot $directory) 'RoboMaster.Workbench.snk'
    if(Test-Path -LiteralPath $candidate) { $previousKey=$candidate; break }
  }
  if($previousKey) { Copy-Item -LiteralPath $previousKey -Destination $key }
  else { $rsa=New-Object System.Security.Cryptography.RSACryptoServiceProvider(2048); try { [IO.File]::WriteAllBytes($key,$rsa.ExportCspBlob($true)) } finally { $rsa.Dispose() } }
}
$refs=@('System.dll','System.Core.dll','System.Drawing.dll','System.Windows.Forms.dll','System.Web.Extensions.dll','Microsoft.CSharp.dll')
$refs+=@('SolidWorks.Interop.sldworks.dll','SolidWorks.Interop.swconst.dll','SolidWorks.Interop.swpublished.dll') | ForEach-Object { Join-Path $SolidWorksApiDir $_ }
$refArgs=@($refs | ForEach-Object { '/reference:'+$_ })
$sources=@(@('WorkbenchTheme.cs','Host.cs','WorkbenchControl.cs','KnowledgeDialog.cs','ApiSettingsDialog.cs','CadLibraryDialog.cs') | ForEach-Object { Join-Path (Join-Path $taskRoot 'native') $_ })
& $Compiler /nologo /target:library /platform:x64 /langversion:latest /optimize+ ('/keyfile:'+$key) ('/out:'+(Join-Path $build 'RoboMaster.Workbench.dll')) @refArgs @sources
if($LASTEXITCODE -ne 0) { throw 'API版插件编译失败' }
& $Compiler /nologo /target:winexe /platform:x64 /langversion:latest /optimize+ ('/out:'+(Join-Path $build 'RoboMaster.Workbench.exe')) @refArgs ('/reference:'+(Join-Path $build 'RoboMaster.Workbench.dll')) (Join-Path $taskRoot 'native\Program.cs')
if($LASTEXITCODE -ne 0) { throw 'API版独立窗口编译失败' }
foreach($name in @('SolidWorks.Interop.sldworks.dll','SolidWorks.Interop.swconst.dll','SolidWorks.Interop.swpublished.dll')) { Copy-Item -LiteralPath (Join-Path $SolidWorksApiDir $name) -Destination $build -Force }
Add-Type -AssemblyName System.Drawing
# Load bytes so this build process never locks the new DLL.
$assembly=[Reflection.Assembly]::Load([IO.File]::ReadAllBytes((Join-Path $build 'RoboMaster.Workbench.dll')))
$theme=$assembly.GetType('RoboMaster.Workbench.WorkbenchTheme')
$flags=[Reflection.BindingFlags]'Static,NonPublic'
$factory=$theme.GetMethod('CreatePixelIcon',$flags)
$taskpaneFactory=$theme.GetMethod('CreateTaskpaneIcon',$flags)
foreach($size in @(20,32,40,64,96,128)) {
  $tabIcon=$taskpaneFactory.Invoke($null,@($size))
  try { $tabIcon.Save((Join-Path $build ('taskpane-'+$size+'.png')),[Drawing.Imaging.ImageFormat]::Png) } finally { $tabIcon.Dispose() }
}
$icon=$factory.Invoke($null,@($false,20))
try { $icon.Save((Join-Path $build 'robomaster-pixel-20.png'),[Drawing.Imaging.ImageFormat]::Png) } finally { $icon.Dispose() }
@{version='1.1.0';edition='api';assembly='RoboMaster.Workbench.dll';guid='C2A4DB56-4E3E-4B76-B95B-230C758417A1'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $build 'build-version.json') -Encoding UTF8
Write-Output ("Build complete: "+$build+" (DLL + EXE; registration unchanged)")

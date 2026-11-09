$ErrorActionPreference='Stop'
$rootPath=Split-Path $PSScriptRoot -Parent
$dll=Join-Path $rootPath 'build-v1.1.0\RoboMaster.Workbench.dll'
$identity=[Reflection.AssemblyName]::GetAssemblyName($dll).FullName
$guid='{C2A4DB56-4E3E-4B76-B95B-230C758417A1}'
$progid='RoboMaster.MechanicalWorkbench'
$base='HKCU:\Software\Classes\CLSID\'+$guid
New-Item -Path $base -Force | Out-Null
Set-Item -Path $base -Value 'RoboMaster.Workbench.SwAddin'
$inproc=New-Item -Path ($base+'\InprocServer32') -Force
Set-Item -Path $inproc.PSPath -Value 'mscoree.dll'
$values=@{ThreadingModel='Both';Class='RoboMaster.Workbench.SwAddin';Assembly=$identity;RuntimeVersion='v4.0.30319';CodeBase=([uri]$dll).AbsoluteUri}
foreach($entry in $values.GetEnumerator()){New-ItemProperty -Path $inproc.PSPath -Name $entry.Key -Value $entry.Value -PropertyType String -Force | Out-Null}
New-Item -Path ($base+'\ProgId') -Force | Out-Null
Set-Item -Path ($base+'\ProgId') -Value $progid
$progKey='HKCU:\Software\Classes\'+$progid+'\CLSID'
New-Item -Path $progKey -Force | Out-Null
Set-Item -Path $progKey -Value $guid
Write-Output 'Registered version 1.1.0 for this Windows user. A running SolidWorks process keeps its already loaded .NET assembly until restart.'

param([switch]$Json)
$ErrorActionPreference='Stop'
$report=[ordered]@{edition='API';version='1.1.0'}
$settings=Join-Path $PSScriptRoot 'settings.json'
if(Test-Path -LiteralPath $settings) {
  $config=Get-Content -Raw -LiteralPath $settings | ConvertFrom-Json
  $report.Python=$config.python_executable
  $report.McpRepository=$config.mcp_repository
}
$build=Join-Path $PSScriptRoot 'build-v1.1.0'
$dll=Join-Path $build 'RoboMaster.Workbench.dll'
$report.AddinDll=Test-Path -LiteralPath $dll
$report.TypeLibrary=Test-Path -LiteralPath (Join-Path $build 'RoboMaster.Workbench.tlb')
if($report.AddinDll) { $report.AssemblyVersion=[Reflection.AssemblyName]::GetAssemblyName($dll).Version.ToString() }
$report.Registered=Test-Path -LiteralPath 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\SOLIDWORKS\Addins\{C2A4DB56-4E3E-4B76-B95B-230C758417A1}'
$diagnostic=Join-Path $PSScriptRoot 'data\addin-status.json'
if(Test-Path -LiteralPath $diagnostic) {
  $addin=Get-Content -Raw -LiteralPath $diagnostic | ConvertFrom-Json
  $report.AddinStatus=$addin | Select-Object status,workbench_version,solidworks_revision,taskpane_ready,callback_registered,event_count
}
$runtime=Join-Path $PSScriptRoot 'data\runtime.json'
if(Test-Path -LiteralPath $runtime) {
  $connection=Get-Content -Raw -LiteralPath $runtime | ConvertFrom-Json
  try {
    $api=Invoke-RestMethod -Uri ($connection.url+'/api/settings') -Headers @{'X-Workbench-Token'=$connection.token} -TimeoutSec 5
    $report.Api=$api | Select-Object protocol,base_url,model,structured_output,timeout_seconds,max_output_tokens,token_parameter,api_key_env,has_api_key,key_source
    $state=Invoke-RestMethod -Uri ($connection.url+'/api/state') -Headers @{'X-Workbench-Token'=$connection.token} -TimeoutSec 5
    $report.Workbench=$state | Select-Object phase,service,progress,session_document_budget
  } catch { $report.Service='API设置服务不可用，请启动API版工作台后重试。' }
} else { $report.Service='API版工作台尚未启动；诊断未启动服务或发送模型请求。' }
if($Json) { [pscustomobject]$report | ConvertTo-Json -Depth 7 } else { [pscustomobject]$report | Format-List }

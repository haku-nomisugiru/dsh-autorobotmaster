param(
    [Parameter(Mandatory=$true)][string]$SolidWorksApiDir,
    [Parameter(Mandatory=$true)][string]$McpRepository,
    [string]$PythonExecutable = 'python.exe',
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Desktop' -or [IntPtr]::Size -ne 8) {
    throw 'Run this script in 64-bit Windows PowerShell (powershell.exe).'
}
$build = Join-Path $PSScriptRoot 'build-v1.1.0'
$dll = Join-Path $build 'RoboMaster.Workbench.dll'
$exe = Join-Path $build 'RoboMaster.Workbench.exe'
if (!(Test-Path -LiteralPath $dll -PathType Leaf) -or !(Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw 'The Workbench binaries are missing. Extract the entire release ZIP first.'
}
$apiDir = (Resolve-Path -LiteralPath $SolidWorksApiDir).Path
$mcp = (Resolve-Path -LiteralPath $McpRepository).Path
$mcpRequirements = Join-Path $mcp 'requirements.txt'
if (!(Test-Path -LiteralPath (Join-Path $mcp 'mcp-server\server.py') -PathType Leaf) -or
    !(Test-Path -LiteralPath $mcpRequirements -PathType Leaf)) {
    throw 'McpRepository must be a checkout of solidworks-automation-skill.'
}

$dependencies = @(
    [Reflection.Assembly]::ReflectionOnlyLoadFrom($dll).GetReferencedAssemblies() |
        Where-Object { $_.Name -like 'SolidWorks.Interop.*' }
)
foreach ($dependency in $dependencies) {
    $dependencyPath = Join-Path $apiDir ($dependency.Name + '.dll')
    if (!(Test-Path -LiteralPath $dependencyPath -PathType Leaf)) {
        throw "Missing SolidWorks interop assembly: $dependencyPath"
    }
    if ([Reflection.AssemblyName]::GetAssemblyName($dependencyPath).FullName -ne $dependency.FullName) {
        throw "This build requires $($dependency.FullName). Use its matching SolidWorks API directory or build from source."
    }
}

$python = (Get-Command -Name $PythonExecutable -CommandType Application -ErrorAction Stop).Source
& $python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) and sys.maxsize > 2**32 else 1)'
if ($LASTEXITCODE -ne 0) { throw 'A 64-bit Python 3.10 or later is required.' }
$venv = Join-Path $PSScriptRoot '.venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'
if (!(Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    & $python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed.' }
}
& $venvPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt') -r $mcpRequirements
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }

foreach ($dependency in $dependencies) {
    $name = $dependency.Name + '.dll'
    Copy-Item -LiteralPath (Join-Path $apiDir $name) -Destination (Join-Path $build $name) -Force
}
$settings = Join-Path $PSScriptRoot 'settings.json'
if (!(Test-Path -LiteralPath $settings)) {
    $config = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $PSScriptRoot 'settings.example.json') | ConvertFrom-Json
    $config.python_executable = $venvPython
    $config.mcp_repository = $mcp
    $config.mcp_python = $venvPython
    [IO.File]::WriteAllText($settings, ($config | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
} else {
    Write-Output 'Kept settings.json. Review python_executable, mcp_python and mcp_repository if you moved the installation.'
}
if (!$PrepareOnly) { & (Join-Path $PSScriptRoot 'install.ps1') }
else { Write-Output 'Workbench files and Python dependencies prepared. COM registration was skipped.' }

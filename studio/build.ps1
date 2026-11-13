param([switch]$Dev,[switch]$Test)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\build-env.ps1')
Push-Location $PSScriptRoot
try {
  if (-not (Test-Path 'node_modules')) { npm.cmd ci; if ($LASTEXITCODE) { throw 'npm ci failed' } }
  if ($Test) {
    New-Item -ItemType Directory -Force (Join-Path $PSScriptRoot '.local\test-temp') | Out-Null
    $env:TEMP = Join-Path $PSScriptRoot '.local\test-temp'
    $env:TMP = $env:TEMP
    npm.cmd run build; if ($LASTEXITCODE) { throw 'Frontend build failed' }
    cargo test --manifest-path src-tauri/Cargo.toml; if ($LASTEXITCODE) { throw 'Rust tests failed' }
    npm.cmd run test:e2e; if ($LASTEXITCODE) { throw 'UI tests failed' }
  } elseif ($Dev) { npm.cmd run desktop } else { npm.cmd run package }
  if ($LASTEXITCODE) { throw "Build failed: $LASTEXITCODE" }
} finally { Pop-Location }

param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:TEMP = Join-Path $projectRoot '.tmp'
$env:TMP = $env:TEMP
$env:KITCHEN_PORT = [string]$Port
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Project Python environment is missing. See README.md.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) { & (Join-Path $PSScriptRoot 'build.ps1'); if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
Write-Host ('Open http://127.0.0.1:' + $Port)
Write-Host 'Offline mode by default. No DeepSeek calls without server opt-in and per-request consent.'
& $python -m kitchen

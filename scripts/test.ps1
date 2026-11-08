$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:TEMP = Join-Path $projectRoot '.tmp'
$env:TMP = $env:TEMP
$env:PYTHONIOENCODING = 'utf-8'
$env:KITCHEN_ENABLE_LIVE = '0'
& (Join-Path $projectRoot '.venv\Scripts\python.exe') -m pytest -q --basetemp (Join-Path $projectRoot '.tmp\pytest-run')
exit $LASTEXITCODE

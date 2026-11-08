$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$nodeRoot = Join-Path $projectRoot '.tools\node'
$env:PATH = $nodeRoot + ';' + $env:PATH
$env:TEMP = Join-Path $projectRoot '.tmp'
$env:TMP = $env:TEMP
$node = Join-Path $nodeRoot 'node.exe'
$npm = Join-Path $nodeRoot 'node_modules\npm\bin\npm-cli.js'
Push-Location (Join-Path $projectRoot 'frontend')
try { & $node $npm run build; exit $LASTEXITCODE } finally { Pop-Location }

param([ValidateRange(1024,65535)][int]$Port=8000,[switch]$RestartApi)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$config=Join-Path $projectRoot 'output/corpus-expansion/api-05/local-api.env'
if (-not (Test-Path -LiteralPath $config)) { throw 'Run python -m backend.real_data_checks1 --prepare-expansion first.' }
$allowed=@('ELASTICSEARCH_URL','ELASTICSEARCH_INDEX','VECTOR_INDEX','EMBEDDING_MODEL_DIR','SCHOLARLENS_PDF_MANIFEST','SCHOLARLENS_PDF_ROOTS_FILE','SCHOLARLENS_RUNTIME_DIR')
foreach ($line in Get-Content -LiteralPath $config -Encoding UTF8) {
    if ($line -match '^([A-Z_]+)=(.*)$' -and $Matches[1] -in $allowed) { [Environment]::SetEnvironmentVariable($Matches[1],$Matches[2],'Process') }
}
if (-not (Get-NetTCPConnection -LocalPort 9200 -State Listen -ErrorAction SilentlyContinue)) {
    & (Join-Path $PSScriptRoot 'start-elasticsearch.ps1')
}
$es=Invoke-RestMethod 'http://127.0.0.1:9200' -TimeoutSec 10
if ($es.cluster_name -ne 'scholarlens-local' -or $es.version.number -ne '8.19.23') { throw 'Expected local Elasticsearch 8.19.23.' }
if ($RestartApi) { & (Join-Path $PSScriptRoot 'stop-backend.ps1') -Port $Port }
if (-not (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) {
    & (Join-Path $PSScriptRoot 'start-backend1.ps1') -Port $Port
} else {
    $pidName=if ($Port -eq 8000) { 'api.pid' } else { "api-$Port.pid" }
    $pidFile=Join-Path $projectRoot "backend/.runtime/$pidName"
    if (-not (Test-Path -LiteralPath $pidFile)) { throw 'Port is occupied by an unrecorded process; preserved.' }
    $owner=Get-CimInstance Win32_Process -Filter "ProcessId=$([int](Get-Content -LiteralPath $pidFile))"
    if (-not $owner -or $owner.CommandLine -notlike '*uvicorn*backend.app1:app*' -or $owner.CommandLine -notlike "*--port $Port*") { throw 'Existing process does not match expansion API; preserved.' }
}
$stats=Invoke-RestMethod "http://127.0.0.1:$Port/api/stats" -TimeoutSec 30
if ($stats.indexed -ne 4000 -or $stats.status -ne 'real') { throw 'Expansion API did not return 4000 real papers.' }
$report=@{api_url="http://127.0.0.1:$Port"; indexed=$stats.indexed; status=$stats.status; index=$stats.index; keyword_alias=$env:ELASTICSEARCH_INDEX; vector_alias=$env:VECTOR_INDEX}
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $projectRoot 'output/corpus-expansion/api-05/startup-report.json') -Encoding UTF8
Write-Output "Expansion API: http://127.0.0.1:$Port/docs; papers=4000. No index rebuild or online deployment."

param([ValidateRange(1024,65535)][int]$Port=8000,[switch]$RestartApi)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$envFile=Join-Path $projectRoot '.env'
$allowed=@('ELASTICSEARCH_URL','ELASTICSEARCH_INDEX','ELASTICSEARCH_API_KEY','ELASTICSEARCH_CA_CERTS',
    'VECTOR_INDEX','EMBEDDING_MODEL_DIR','UPLOADS_INDEX','SCHOLARLENS_RUNTIME_DIR','CORS_ORIGINS',
    'SCHOLARLENS_PDF_ROOT','SCHOLARLENS_PDF_PATH_BASE','SCHOLARLENS_PDF_MANIFEST',
    'AI_API_KEY','AI_BASE_URL','AI_MODEL','AI_TIMEOUT_SECONDS','AI_MAX_OUTPUT_TOKENS','AI_TOKEN_PARAMETER','GROBID_URL',
    'EMAIL_BASE_URL','EMAIL_API_KEY','UPLOAD_VECTOR_INDEX')
if (Test-Path -LiteralPath $envFile) {
    foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
        if ($line -match '^\s*([A-Z_][A-Z0-9_]*)\s*=(.*)$') {
            $name=$Matches[1]
            if ($name -in $allowed) {
                $value=$Matches[2].Trim()
                if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                    $value=$value.Substring(1,$value.Length-2)
                }
                [Environment]::SetEnvironmentVariable($name,$value,'Process')
            }
        }
    }
}
if (-not (Get-NetTCPConnection -LocalPort 9200 -State Listen -ErrorAction SilentlyContinue)) {
    & (Join-Path $PSScriptRoot 'start-elasticsearch.ps1')
}
$es=Invoke-RestMethod 'http://127.0.0.1:9200' -TimeoutSec 10
if ($es.cluster_name -ne 'scholarlens-local' -or $es.version.number -ne '8.19.23') { throw 'Unexpected Elasticsearch instance; existing services were preserved.' }
if ($RestartApi -and (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) {
    & (Join-Path $PSScriptRoot 'stop-backend.ps1') -Port $Port
}
if (-not (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) {
    & (Join-Path $PSScriptRoot 'start-backend.ps1') -Port $Port
}
$stats=Invoke-RestMethod "http://127.0.0.1:$Port/api/stats" -TimeoutSec 15
$openapi=Invoke-RestMethod "http://127.0.0.1:$Port/openapi.json" -TimeoutSec 10
Write-Output "API http://127.0.0.1:$Port/docs version=$($openapi.info.version) papers=$($stats.indexed) status=$($stats.status)"
Write-Output 'No import or vector rebuild was performed. Use /api/capabilities for dependency status.'

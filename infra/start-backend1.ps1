param([ValidateRange(1024,65535)][int]$Port = 8000, [string]$Index = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$python = Join-Path $projectRoot 'backend/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Install backend dependencies first.' }
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw "Port $Port is already in use." }
$runtimeRoot = Join-Path $projectRoot 'backend/.runtime/expansion-api'
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
$pidName = if ($Port -eq 8000) { 'api.pid' } else { "api-$Port.pid" }
$oldIndex = $env:ELASTICSEARCH_INDEX
try {
    if ($Index) { $env:ELASTICSEARCH_INDEX = $Index }
    $proc = Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','backend.app1:app','--host','127.0.0.1','--port',"$Port") -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeRoot "api-$Port.stdout.log") -RedirectStandardError (Join-Path $runtimeRoot "api-$Port.stderr.log") -PassThru
    Set-Content -LiteralPath (Join-Path (Join-Path $projectRoot 'backend/.runtime') $pidName) -Value $proc.Id
} finally { $env:ELASTICSEARCH_INDEX = $oldIndex }
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    try {
        $null = Invoke-RestMethod "http://127.0.0.1:$Port/openapi.json" -TimeoutSec 2
        break
    } catch {
        if ($proc.HasExited) { throw "API exited; inspect backend/.runtime/api-$Port.stderr.log" }
        if ($attempt -eq 39) { throw 'API startup timed out.' }
        Start-Sleep -Milliseconds 250
    }
}
Write-Output "Started API PID $($proc.Id) at http://127.0.0.1:$Port/docs"

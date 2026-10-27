$ErrorActionPreference = 'Stop'
$runtimeRoot = Join-Path $PSScriptRoot '.runtime'
$installDir = Join-Path $runtimeRoot 'elasticsearch-8.19.23'
if (-not (Test-Path -LiteralPath (Join-Path $installDir 'bin/elasticsearch.bat'))) { throw 'Run infra/setup-elasticsearch.ps1 first.' }
$pidFile = Join-Path $runtimeRoot 'elasticsearch.pid'
if (Test-Path -LiteralPath $pidFile) {
    $savedPid = [int](Get-Content -LiteralPath $pidFile)
    $savedProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $savedPid" -ErrorAction SilentlyContinue
    if ($savedProcess -and $savedProcess.CommandLine -and $savedProcess.CommandLine.Contains($installDir)) {
        throw "Recorded Elasticsearch process $savedPid is still running."
    }
    # A PID may be reused after Windows restarts. Keep the stale record; never stop that process.
    if ($savedProcess) {
        Move-Item -LiteralPath $pidFile -Destination ($pidFile + '.stale-' + [guid]::NewGuid().ToString('N'))
    }
}
if (Get-NetTCPConnection -LocalPort 9200 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 9200 is already in use.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'elasticsearch.yml') -Destination (Join-Path $installDir 'config/elasticsearch.yml') -Force
$oldJava = $env:ES_JAVA_HOME
$oldOpts = $env:ES_JAVA_OPTS
try {
    $env:ES_JAVA_HOME = Join-Path $installDir 'jdk'
    $env:ES_JAVA_OPTS = '-Xms512m -Xmx512m'
    $proc = Start-Process -FilePath (Join-Path $installDir 'bin/elasticsearch.bat') -WorkingDirectory $installDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeRoot 'elasticsearch.stdout.log') -RedirectStandardError (Join-Path $runtimeRoot 'elasticsearch.stderr.log') -PassThru
    Set-Content -LiteralPath $pidFile -Value $proc.Id
} finally {
    $env:ES_JAVA_HOME = $oldJava
    $env:ES_JAVA_OPTS = $oldOpts
}
$ready = $false
for ($attempt = 0; $attempt -lt 90; $attempt++) {
    try {
        $info = Invoke-RestMethod 'http://127.0.0.1:9200' -TimeoutSec 2
        if ($info.cluster_name -eq 'scholarlens-local' -and $info.version.number -eq '8.19.23' -and $info.cluster_uuid -ne '_na_') {
            $health = Invoke-RestMethod 'http://127.0.0.1:9200/_cluster/health?wait_for_status=yellow&timeout=2s' -TimeoutSec 4
            if (-not $health.timed_out -and $health.status -in @('yellow','green')) { $ready = $true; break }
        }
    } catch { }
    if ($proc.HasExited) { throw 'Elasticsearch exited; inspect infra/.runtime/*.log.' }
    Start-Sleep -Milliseconds 500
}
if (-not $ready) { throw 'Elasticsearch is still starting; inspect infra/.runtime/*.log.' }
$info | ConvertTo-Json -Depth 5

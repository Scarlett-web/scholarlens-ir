$ErrorActionPreference = 'Stop'
$pidFile = Join-Path $PSScriptRoot '.runtime/elasticsearch.pid'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Output 'No recorded Elasticsearch process.'; return }
$savedPid = [int](Get-Content -LiteralPath $pidFile)
$proc = Get-CimInstance Win32_Process -Filter "ProcessId=$savedPid"
if ($proc) {
    if ($proc.CommandLine -notlike '*elasticsearch*') { throw 'Recorded PID no longer belongs to Elasticsearch.' }
    & taskkill.exe /PID $savedPid /T /F
    if ($LASTEXITCODE -ne 0) { throw 'Elasticsearch stop failed.' }
}
Remove-Item -LiteralPath $pidFile
Write-Output 'Stopped the recorded local Elasticsearch process; indexes preserved.'

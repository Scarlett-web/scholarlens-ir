param([ValidatePattern('^[a-zA-Z0-9_.-]+\.json$')][string]$State='vector-build.json',[ValidateRange(1,32)][int]$BatchSize=8,[ValidateRange(1,4)][int]$Workers=1)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$runtime=Join-Path $projectRoot 'backend/.runtime'
$python=Join-Path $projectRoot 'backend/.venv/Scripts/python.exe'
$statePath=Join-Path $runtime $State
$jobFile=Join-Path $runtime ($State+'.job.json')
if (Test-Path -LiteralPath $jobFile) {
    $previous=Get-Content -LiteralPath $jobFile -Raw | ConvertFrom-Json
    $process=Get-CimInstance Win32_Process -Filter "ProcessId = $($previous.pid)" -ErrorAction SilentlyContinue
    if ($process -and $process.CommandLine -like '*backend.vector_index*' -and $process.CommandLine.Contains($statePath)) {
        Write-Output "Existing vector build PID $($previous.pid) is running; no second build was started."
        return
    }
}
$null=Invoke-RestMethod 'http://127.0.0.1:9200' -TimeoutSec 10
$runId=[guid]::NewGuid().ToString('N')
$stdout=Join-Path $runtime "vector-build-$runId.stdout.log"
$stderr=Join-Path $runtime "vector-build-$runId.stderr.log"
$proc=Start-Process -FilePath $python -ArgumentList @('-m','backend.vector_index','--state',('"'+$statePath+'"'),'--batch-size',"$BatchSize",'--workers',"$Workers") -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
@{pid=$proc.Id;state=$statePath;stdout=$stdout;stderr=$stderr;started_at=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $jobFile -Encoding UTF8
Write-Output "Started resumable vector build PID $($proc.Id). Inspect the checkpoint and job JSON for progress/logs."

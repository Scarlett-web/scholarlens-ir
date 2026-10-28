[CmdletBinding()]
param(
  [string]$TargetUrl = "http://127.0.0.1:4173",
  [switch]$AllowLive,
  [int]$MaxPages = 30
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$report = Join-Path $PSScriptRoot "reports/$stamp"
New-Item -ItemType Directory -Force -Path $report | Out-Null

if ($TargetUrl -match "^https://scholarlens\.lingion\.cc\.cd" -and -not $AllowLive) {
  throw "线上目标需要显式指定 -AllowLive；默认只检查本机预览。"
}

$manifest = [ordered]@{
  target = $TargetUrl
  started_at = (Get-Date).ToUniversalTime().ToString("o")
  scope = if ($AllowLive) { "approved-read-only-live" } else { "local-preview" }
  tools = [ordered]@{}
}
function Run-Optional($name, $command, $arguments, $outFile) {
  $exe = Get-Command $command -ErrorAction SilentlyContinue
  if (-not $exe) { $manifest.tools[$name] = @{ status="not_installed"; command=$command }; return }
  $logFile = [IO.Path]::ChangeExtension($outFile, ".log")
  & $exe.Source @arguments 1> $logFile 2>&1
  $manifest.tools[$name] = @{ status=if ($LASTEXITCODE -eq 0) { "completed" } else { "findings_or_failed" }; command=$command; exit_code=$LASTEXITCODE; output=(Split-Path $outFile -Leaf); log=(Split-Path $logFile -Leaf) }
}

$frontend = Join-Path $root "frontend"
Push-Location $frontend
try {
  npm audit --omit=dev --json *> (Join-Path $report "npm-audit.json")
  $manifest.tools.npm_audit = @{ status=if ($LASTEXITCODE -eq 0) { "completed" } else { "findings_or_failed" }; output="npm-audit.json"; exit_code=$LASTEXITCODE }
} finally { Pop-Location }

$semgrepOut = Join-Path $report "semgrep.json"
$semgrepLog = Join-Path $report "semgrep.log"
$semgrep = Get-Command "semgrep" -ErrorAction SilentlyContinue
if (-not $semgrep) {
  $manifest.tools.semgrep = @{ status="not_installed"; command="semgrep" }
} else {
  # Semgrep writes its human-readable banner/findings to stdout even with --quiet.
  # Use --json-output so the report stays valid JSON and keep console output in the log.
  & $semgrep.Source "scan" "--quiet" "--config" (Join-Path $PSScriptRoot "semgrep.yml") "--json-output=$semgrepOut" "--exclude" "node_modules" "--exclude" "dist" "--exclude" "tools/audit" $root 1> $semgrepLog 2>&1
  $manifest.tools.semgrep = @{ status=if ($LASTEXITCODE -eq 0) { "completed" } else { "findings_or_failed" }; command="semgrep"; exit_code=$LASTEXITCODE; output=(Split-Path $semgrepOut -Leaf); log=(Split-Path $semgrepLog -Leaf) }
}
$gitleaksOut = Join-Path $report "gitleaks.json"
Run-Optional "gitleaks" "gitleaks" @("detect","--source=$root","--redact","--report-format","json","--report-path=$gitleaksOut","--no-banner") $gitleaksOut

$localBin = Join-Path $PSScriptRoot "node_modules/.bin"
$lighthouse = Join-Path $localBin "lighthouse.cmd"
if (Test-Path $lighthouse) {
  $lighthouseJson = Join-Path $report "lighthouse.json"
  $lighthouseLog = Join-Path $report "lighthouse.log"
  & $lighthouse $TargetUrl "--quiet" "--chrome-flags=--headless=new --no-sandbox" "--output=json" "--output-path=$lighthouseJson" *> $lighthouseLog
  $manifest.tools.lighthouse = @{ status=if ($LASTEXITCODE -eq 0) { "completed" } else { "failed" }; output="lighthouse.json"; exit_code=$LASTEXITCODE }
} else { $manifest.tools.lighthouse = @{ status="not_installed" } }

$squirrel = Join-Path $localBin "squirrel.cmd"
$squirrelNative = Join-Path $PSScriptRoot "node_modules/squirrelscan/bin/squirrel.exe"
if ((Test-Path $squirrel) -and (Test-Path $squirrelNative)) {
  & $squirrel audit $TargetUrl --offline --max-pages $MaxPages -f json -o (Join-Path $report "squirrelscan.json") *> (Join-Path $report "squirrelscan.log")
  $manifest.tools.squirrelscan = @{ status=if ($LASTEXITCODE -eq 0) { "completed" } else { "failed" }; output="squirrelscan.json"; exit_code=$LASTEXITCODE }
} else { $manifest.tools.squirrelscan = @{ status="not_available"; reason="package installed but native binary was unavailable" } }

$manifest.finished_at = (Get-Date).ToUniversalTime().ToString("o")
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $report "manifest.json") -Encoding utf8
Write-Output "Audit report: $report"

param([string]$Version = '8.19.23')
$ErrorActionPreference = 'Stop'
if ($Version -ne '8.19.23') { throw 'This configuration is verified with 8.19.23.' }
$runtimeRoot = Join-Path $PSScriptRoot '.runtime'
$archive = Join-Path $runtimeRoot "elasticsearch-$Version-windows-x86_64.zip"
$installDir = Join-Path $runtimeRoot "elasticsearch-$Version"
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
$url = "https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-$Version-windows-x86_64.zip"
$ProgressPreference = 'SilentlyContinue'
if (-not (Test-Path -LiteralPath $archive)) {
    $partial = "$archive.partial"
    Invoke-WebRequest -Uri $url -OutFile $partial -UseBasicParsing
    Move-Item -LiteralPath $partial -Destination $archive
}
$checksum = (Invoke-WebRequest -Uri "$url.sha512" -UseBasicParsing).Content
if ($checksum -is [byte[]]) { $checksum = [Text.Encoding]::ASCII.GetString($checksum) }
$expected = ([string]$checksum).Trim().Split(' ')[0].ToLowerInvariant()
$actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA512).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'Elasticsearch SHA-512 verification failed.' }
if (-not (Test-Path -LiteralPath (Join-Path $installDir 'bin/elasticsearch.bat'))) {
    Expand-Archive -LiteralPath $archive -DestinationPath $runtimeRoot
}
Write-Output "Verified Elasticsearch $Version at $installDir"

param(
  [string]$Version = "v24.14.1",
  [switch]$Force
)

$ErrorActionPreference = "Stop"

$cacheRoot = Join-Path $env:LOCALAPPDATA "lawyer5rp-tools"
$installRoot = Join-Path $cacheRoot "node-$Version-win-x64"
$nodeExe = Join-Path $installRoot "node.exe"

if (-not $Force -and (Test-Path $nodeExe)) {
  Write-Output $nodeExe
  exit 0
}

New-Item -ItemType Directory -Force -Path $cacheRoot | Out-Null

$archiveName = "node-$Version-win-x64.zip"
$archivePath = Join-Path $cacheRoot $archiveName
$downloadUrl = "https://nodejs.org/dist/$Version/$archiveName"
$extractRoot = Join-Path $cacheRoot "extract-$Version"

Invoke-WebRequest -Uri $downloadUrl -OutFile $archivePath

if (Test-Path $extractRoot) {
  Remove-Item -Recurse -Force $extractRoot
}
New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null
Expand-Archive -Path $archivePath -DestinationPath $extractRoot -Force

$expandedRoot = Join-Path $extractRoot "node-$Version-win-x64"
if (-not (Test-Path (Join-Path $expandedRoot "node.exe"))) {
  throw "Не удалось распаковать Node.js из $archivePath"
}

if (Test-Path $installRoot) {
  Remove-Item -Recurse -Force $installRoot
}
Move-Item -Path $expandedRoot -Destination $installRoot
Remove-Item -Recurse -Force $extractRoot

Write-Output $nodeExe

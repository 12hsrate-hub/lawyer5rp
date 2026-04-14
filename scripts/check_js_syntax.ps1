param(
  [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
  [string[]]$Paths = @(
    "web/ogp_web/static/pages/admin.js",
    "web/ogp_web/static/shared/admin_common.js",
    "web/ogp_web/static/shared/admin_catalog.js",
    "web/ogp_web/static/shared/admin_overview.js",
    "web/ogp_web/static/shared/admin_runtime_laws.js"
  )
)

$ErrorActionPreference = "Stop"

$repoRoot = git rev-parse --show-toplevel
if (-not $repoRoot) {
  throw "Не удалось определить корень репозитория"
}

$ensureScript = Join-Path $repoRoot "scripts/ensure_node.ps1"
$nodeExe = & powershell -NoProfile -ExecutionPolicy Bypass -File $ensureScript
if (-not $nodeExe -or -not (Test-Path $nodeExe)) {
  throw "Не удалось подготовить Node.js"
}

$resolved = @()
foreach ($path in $Paths) {
  $fullPath = Join-Path $repoRoot $path
  if (-not (Test-Path $fullPath)) {
    throw "Файл не найден: $path"
  }
  $resolved += $fullPath
}

foreach ($fullPath in $resolved) {
  & $nodeExe --check $fullPath
  if ($LASTEXITCODE -ne 0) {
    throw "Node syntax check failed for $fullPath"
  }
}

Write-Host "JS syntax check passed for $($resolved.Count) file(s)."

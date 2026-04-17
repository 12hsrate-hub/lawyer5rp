param(
    [string]$RepoPath = "",
    [string]$ProdSshHost = "lawyer5rp-prod",
    [string]$ProdRepoPath = "/srv/lawyer5rp-deploy/repo",
    [string]$HealthUrl = "http://127.0.0.1:8000/health"
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoPath)) {
    $RepoPath = Split-Path -Parent $PSScriptRoot
}

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "=== $Title ===" -ForegroundColor Cyan
}

function Get-GitValue {
    param(
        [string]$Path,
        [string[]]$GitArgs
    )

    Push-Location $Path
    try {
        $result = & git @GitArgs 2>&1
        return ($result | Select-Object -First 1).Trim()
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path (Join-Path $RepoPath ".git"))) {
    throw "Repository root not found at: $RepoPath"
}

Write-Section "Local repository"
Push-Location $RepoPath
try {
    & git fetch origin main | Out-Null
}
finally {
    Pop-Location
}

$localHead = Get-GitValue -Path $RepoPath -GitArgs @("rev-parse", "HEAD")
$originMain = Get-GitValue -Path $RepoPath -GitArgs @("rev-parse", "origin/main")

Write-Host "local HEAD:  $localHead"
Write-Host "origin/main: $originMain"

if ($localHead -ne $originMain) {
    throw "Local HEAD does not match origin/main. Push or update GitHub before deploy."
}

Write-Section "Deploy"
$deployCommand = @(
    "cd $ProdRepoPath",
    "git fetch origin",
    "git checkout main",
    "git reset --hard origin/main",
    "bash scripts/deploy_from_checkout.sh"
) -join " && "

$deployOutput = ssh $ProdSshHost $deployCommand
$deployLines = @($deployOutput | ForEach-Object { "$_".TrimEnd() })
$deployLines | Where-Object { $_ -ne "" } | ForEach-Object { Write-Host $_ }

Write-Section "Production"
$prodHead = ssh $ProdSshHost "cd $ProdRepoPath && git rev-parse HEAD"
$prodHealth = ssh $ProdSshHost "curl -sS $HealthUrl"
$prodHead = ($prodHead | Select-Object -First 1).Trim()
$prodHealth = ($prodHealth | Select-Object -First 1).Trim()

Write-Host "prod HEAD:   $prodHead"
Write-Host "health:      $prodHealth"

Write-Section "Summary"
if ($prodHead -ne $originMain) {
    throw "Deploy completed, but prod HEAD does not match origin/main."
}

Write-Host "Status: deploy completed successfully." -ForegroundColor Green

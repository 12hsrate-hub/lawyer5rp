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

function Normalize-Sha {
    param([object]$Value)

    if ($null -eq $Value) {
        return ""
    }

    if ($Value -is [System.Array]) {
        $Value = ($Value | ForEach-Object { "$_".Trim() } | Where-Object { $_ }) -join "`n"
    }
    else {
        $Value = "$Value"
    }

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ""
    }

    $match = [regex]::Match($Value, "[0-9a-fA-F]{40}")
    if ($match.Success) {
        return $match.Value.ToLowerInvariant()
    }

    return $Value.Trim().ToLowerInvariant()
}

Write-Section "Local repository"
if (-not (Test-Path (Join-Path $RepoPath ".git"))) {
    throw "Repository root not found at: $RepoPath"
}

Push-Location $RepoPath
try {
    & git fetch origin main | Out-Null
}
finally {
    Pop-Location
}
$localHead = Get-GitValue -Path $RepoPath -GitArgs @("rev-parse", "HEAD")
$originMain = Get-GitValue -Path $RepoPath -GitArgs @("rev-parse", "origin/main")
$remoteUrl = Get-GitValue -Path $RepoPath -GitArgs @("remote", "get-url", "origin")
$localHeadNormalized = Normalize-Sha $localHead
$originMainNormalized = Normalize-Sha $originMain

Write-Host "origin:      $remoteUrl"
Write-Host "local HEAD:  $localHead"
Write-Host "origin/main: $originMain"

Write-Section "Production"
try {
    $prodHead = ssh $ProdSshHost "cd $ProdRepoPath && git rev-parse HEAD"
    $prodHealth = ssh $ProdSshHost "curl -sS $HealthUrl"
    $prodHead = ($prodHead | Select-Object -First 1).Trim()
    $prodHealth = ($prodHealth | Select-Object -First 1).Trim()
    $prodHeadNormalized = Normalize-Sha $prodHead

    Write-Host "prod HEAD:   $prodHead"
    Write-Host "health:      $prodHealth"
}
catch {
    Write-Host "prod check failed: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "Tip: configure SSH alias '$ProdSshHost' in ~/.ssh/config first." -ForegroundColor Yellow
    exit 1
}

Write-Section "Summary"
$localMatchesOrigin = [string]::Equals(
    [string]$localHeadNormalized,
    [string]$originMainNormalized,
    [System.StringComparison]::OrdinalIgnoreCase
)
$originMatchesProd = [string]::Equals(
    [string]$originMainNormalized,
    [string]$prodHeadNormalized,
    [System.StringComparison]::OrdinalIgnoreCase
)

Write-Host "local == origin/main : $localMatchesOrigin"
Write-Host "origin/main == prod  : $originMatchesProd"

if ($localMatchesOrigin -and $originMatchesProd) {
    Write-Host "Status: everything is in sync." -ForegroundColor Green
    exit 0
}

Write-Host "normalized local:  $localHeadNormalized" -ForegroundColor DarkYellow
Write-Host "normalized origin: $originMainNormalized" -ForegroundColor DarkYellow
Write-Host "normalized prod:   $prodHeadNormalized" -ForegroundColor DarkYellow
Write-Host "Status: mismatch detected." -ForegroundColor Red
exit 2

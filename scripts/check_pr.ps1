param(
    [string]$RepoPath = "",
    [int]$PrNumber = 0,
    [string]$State = "open",
    [switch]$Checkout,
    [switch]$OpenInCode,
    [switch]$OpenOnGitHub,
    [switch]$Json
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

function Get-GhCommand {
    $ghCommand = Get-Command gh -ErrorAction SilentlyContinue
    if ($ghCommand) {
        return $ghCommand.Source
    }

    $fallback = "C:\Program Files\GitHub CLI\gh.exe"
    if (Test-Path -LiteralPath $fallback) {
        return $fallback
    }

    return $null
}

function Get-CodeCommand {
    $codeCommand = Get-Command code -ErrorAction SilentlyContinue
    if ($codeCommand) {
        return $codeCommand.Source
    }

    $fallback = "C:\Users\$env:USERNAME\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd"
    if (Test-Path -LiteralPath $fallback) {
        return $fallback
    }

    return $null
}

function Get-GitValue {
    param(
        [string]$Path,
        [string[]]$GitArgs
    )

    Push-Location $Path
    try {
        $result = & git @GitArgs 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw ($result | Out-String)
        }
        return ($result | Select-Object -First 1).Trim()
    }
    finally {
        Pop-Location
    }
}

function Get-RepoSlugFromRemote {
    param([string]$RemoteUrl)

    $repoSlug = $RemoteUrl
    $repoSlug = $repoSlug -replace '\.git$',''
    $repoSlug = $repoSlug -replace '^git@github\.com:',''
    $repoSlug = $repoSlug -replace '^https://([^@/]+@)?github\.com/',''
    return $repoSlug.Trim('/')
}

function Invoke-GhJson {
    param(
        [string]$GhPath,
        [string[]]$Arguments
    )

    $output = & $GhPath @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($output | Out-String)
    }

    if ([string]::IsNullOrWhiteSpace(($output | Out-String))) {
        return $null
    }

    return ($output | Out-String | ConvertFrom-Json)
}

function Get-CheckSummary {
    param([object[]]$Checks)

    $summary = [ordered]@{
        Pending = 0
        Success = 0
        Failure = 0
        Other = 0
    }

    foreach ($check in @($Checks)) {
        $status = "$($check.status)".ToUpperInvariant()
        $conclusion = "$($check.conclusion)".ToUpperInvariant()

        if ($status -ne "COMPLETED") {
            $summary.Pending++
            continue
        }

        switch ($conclusion) {
            "SUCCESS" { $summary.Success++ }
            "FAILURE" { $summary.Failure++ }
            "NEUTRAL" { $summary.Other++ }
            "CANCELLED" { $summary.Other++ }
            "SKIPPED" { $summary.Other++ }
            "TIMED_OUT" { $summary.Failure++ }
            "ACTION_REQUIRED" { $summary.Failure++ }
            default { $summary.Other++ }
        }
    }

    return [PSCustomObject]$summary
}

function Get-ReviewLabel {
    param([string]$Decision)

    switch ("$Decision") {
        "APPROVED" { return "approved" }
        "REVIEW_REQUIRED" { return "review-required" }
        "CHANGES_REQUESTED" { return "changes-requested" }
        default { return "no-decision" }
    }
}

function Write-PrList {
    param(
        [string]$RepoSlug,
        [object[]]$Prs
    )

    Write-Section "Pull Requests"
    if (-not $Prs -or $Prs.Count -eq 0) {
        Write-Host "No PRs found for state '$State'." -ForegroundColor Green
        return
    }

    $reportLines = @(
        "=== Pull Requests for $RepoSlug ($State) ===",
        ""
    )

    foreach ($pr in $Prs) {
        $draftLabel = if ($pr.isDraft) { "draft" } else { "ready" }
        $reviewLabel = Get-ReviewLabel -Decision $pr.reviewDecision
        $checkSummary = Get-CheckSummary -Checks $pr.statusCheckRollup
        $statusLine = "checks ok=$($checkSummary.Success) fail=$($checkSummary.Failure) pending=$($checkSummary.Pending)"

        Write-Host "#$($pr.number) [$draftLabel] [$reviewLabel] $($pr.title)"
        Write-Host "  $($pr.headRefName) -> $($pr.baseRefName) | $statusLine"
        Write-Host "  $($pr.url)"
        Write-Host ""

        $reportLines += "#$($pr.number) [$draftLabel] [$reviewLabel] $($pr.title)"
        $reportLines += "$($pr.headRefName) -> $($pr.baseRefName) | $statusLine"
        $reportLines += "$($pr.url)"
        $reportLines += ""
    }

    Set-Clipboard -Value (($reportLines -join "`r`n").Trim())
    Write-Host "List copied to clipboard." -ForegroundColor Green
}

function Write-PrDetails {
    param([object]$Pr)

    $reviewLabel = Get-ReviewLabel -Decision $Pr.reviewDecision
    $checkSummary = Get-CheckSummary -Checks $Pr.statusCheckRollup

    Write-Section "PR Summary"
    Write-Host "#$($Pr.number) $($Pr.title)"
    Write-Host "State:          $($Pr.state)"
    Write-Host "Draft:          $($Pr.isDraft)"
    Write-Host "Review:         $reviewLabel"
    Write-Host "Branch:         $($Pr.headRefName) -> $($Pr.baseRefName)"
    Write-Host "Author:         $($Pr.author.login)"
    Write-Host "Updated:        $($Pr.updatedAt)"
    Write-Host "URL:            $($Pr.url)"
    Write-Host "Checks:         success=$($checkSummary.Success) failure=$($checkSummary.Failure) pending=$($checkSummary.Pending) other=$($checkSummary.Other)"
    Write-Host "Changed files:  $($Pr.files.Count)"
    Write-Host "Commits:        $($Pr.commits.Count)"

    Write-Section "Changed Files"
    foreach ($file in @($Pr.files | Select-Object -First 30)) {
        Write-Host "$($file.path) [$($file.additions) + / $($file.deletions) -]"
    }
    if (@($Pr.files).Count -gt 30) {
        Write-Host "... and $(@($Pr.files).Count - 30) more files"
    }

    Write-Section "Status Checks"
    foreach ($check in @($Pr.statusCheckRollup)) {
        $workflowName = if ($check.workflowName) { $check.workflowName } else { "workflow" }
        $status = "$($check.status)".ToLowerInvariant()
        $conclusion = if ($check.conclusion) { "$($check.conclusion)".ToLowerInvariant() } else { "-" }
        Write-Host "$workflowName / $($check.name): $status / $conclusion"
        if ($check.detailsUrl) {
            Write-Host "  $($check.detailsUrl)"
        }
    }

    $reportLines = @(
        "=== PR #$($Pr.number) ===",
        "$($Pr.title)",
        "State: $($Pr.state)",
        "Draft: $($Pr.isDraft)",
        "Review: $reviewLabel",
        "Branch: $($Pr.headRefName) -> $($Pr.baseRefName)",
        "Author: $($Pr.author.login)",
        "Updated: $($Pr.updatedAt)",
        "URL: $($Pr.url)",
        "Checks: success=$($checkSummary.Success) failure=$($checkSummary.Failure) pending=$($checkSummary.Pending) other=$($checkSummary.Other)",
        ""
    )

    foreach ($file in @($Pr.files | Select-Object -First 30)) {
        $reportLines += "$($file.path) [$($file.additions) + / $($file.deletions) -]"
    }

    Set-Clipboard -Value (($reportLines -join "`r`n").Trim())
    Write-Host ""
    Write-Host "Summary copied to clipboard." -ForegroundColor Green
}

if (-not (Test-Path -LiteralPath (Join-Path $RepoPath ".git"))) {
    throw "Repository root not found at: $RepoPath"
}

$ghPath = Get-GhCommand
if (-not $ghPath) {
    throw "GitHub CLI (gh) is not installed."
}

$codePath = Get-CodeCommand
$remoteUrl = Get-GitValue -Path $RepoPath -GitArgs @("remote", "get-url", "origin")
$repoSlug = Get-RepoSlugFromRemote -RemoteUrl $remoteUrl

if ([string]::IsNullOrWhiteSpace($repoSlug) -or $repoSlug -notmatch '^[^/]+/[^/]+$') {
    throw "Origin is not a GitHub repository: $remoteUrl"
}

& $ghPath auth status | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI is not authenticated. Run 'gh auth login' first."
}

if ($PrNumber -le 0) {
    $prs = Invoke-GhJson -GhPath $ghPath -Arguments @(
        "pr", "list",
        "--repo", $repoSlug,
        "--state", $State,
        "--limit", "50",
        "--json", "number,title,isDraft,headRefName,baseRefName,reviewDecision,statusCheckRollup,url"
    )

    if ($Json) {
        $prs | ConvertTo-Json -Depth 8
        exit 0
    }

    Write-PrList -RepoSlug $repoSlug -Prs $prs
    Write-Host ""
    Write-Host "Tip: run .\\scripts\\check_pr.ps1 -PrNumber <n> -Checkout -OpenInCode to review a specific PR in the GitHub extension." -ForegroundColor Yellow
    exit 0
}

$pr = Invoke-GhJson -GhPath $ghPath -Arguments @(
    "pr", "view", "$PrNumber",
    "--repo", $repoSlug,
    "--json", "number,title,state,isDraft,headRefName,baseRefName,reviewDecision,author,updatedAt,url,statusCheckRollup,files,commits"
)

if ($Json) {
    $pr | ConvertTo-Json -Depth 10
    exit 0
}

Write-PrDetails -Pr $pr

if ($Checkout) {
    Write-Section "Checkout"
    Push-Location $RepoPath
    try {
        & $ghPath pr checkout "$PrNumber" --repo $repoSlug
        if ($LASTEXITCODE -ne 0) {
            throw "gh pr checkout failed."
        }
        $branchName = Get-GitValue -Path $RepoPath -GitArgs @("branch", "--show-current")
        Write-Host "Checked out branch: $branchName" -ForegroundColor Green
    }
    finally {
        Pop-Location
    }
}

if ($OpenInCode) {
    Write-Section "VS Code"
    if (-not $codePath) {
        Write-Host "VS Code CLI not found. Skipping open-in-code step." -ForegroundColor Yellow
    }
    else {
        & $codePath -r $RepoPath | Out-Null
        Write-Host "Opened repository in VS Code." -ForegroundColor Green
        Write-Host "In the GitHub Pull Requests extension, use Active Pull Request or PR #$PrNumber." -ForegroundColor Green
    }
}

if ($OpenOnGitHub) {
    Write-Section "Browser"
    Start-Process $pr.url | Out-Null
    Write-Host "Opened PR on GitHub." -ForegroundColor Green
}

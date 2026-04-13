param(
    [string]$RepoPath = "",
    [string]$CasesPath = "",
    [ValidateSet("local-python", "http")]
    [string]$Mode = "local-python",
    [string]$ServerCode = "blackberry",
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$Cookie = "",
    [string]$BearerToken = "",
    [int]$PauseMs = 0,
    [string]$OutFile = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoPath)) {
    $RepoPath = Split-Path -Parent $PSScriptRoot
}

if ([string]::IsNullOrWhiteSpace($CasesPath)) {
    $CasesPath = Join-Path $PSScriptRoot "suggest_cases_ogp_5.json"
}

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "=== $Title ===" -ForegroundColor Cyan
}

function Convert-ToJsonSafe {
    param([object]$Value)
    return ($Value | ConvertTo-Json -Depth 12)
}

function Get-StringValue {
    param([object]$Value)
    if ($null -eq $Value) {
        return ""
    }
    return [string]$Value
}

function Normalize-Preview {
    param([object]$Text, [int]$Limit = 140)
    $value = [string]$Text
    $value = [regex]::Replace($value, "\s+", " ").Trim()
    if ($value.Length -le $Limit) {
        return $value
    }
    return $value.Substring(0, $Limit - 3) + "..."
}

function Invoke-LocalPythonSuggestCases {
    param(
        [string]$RepoRoot,
        [string]$CasesFile,
        [string]$ServerCodeValue
    )

    $pythonScript = @'
import json
import sys
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
cases_path = Path(sys.argv[2]).resolve()
server_code = str(sys.argv[3] or "").strip() or "blackberry"

for candidate in (repo_root, repo_root / "web"):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)

from ogp_web.schemas import SuggestPayload
from ogp_web.services.ai_service import suggest_text_details

cases = json.loads(cases_path.read_text(encoding="utf-8"))
results = []

for index, case in enumerate(cases, start=1):
    payload = SuggestPayload(
        victim_name=str(case.get("victim_name", "") or ""),
        org=str(case.get("org", "") or ""),
        subject=str(case.get("subject", "") or ""),
        event_dt=str(case.get("event_dt", "") or ""),
        raw_desc=str(case.get("raw_desc", "") or ""),
        complaint_basis=str(case.get("complaint_basis", "") or ""),
        main_focus=str(case.get("main_focus", "") or ""),
    )
    result = suggest_text_details(payload, server_code=server_code)
    results.append(
        {
            "index": index,
            "case_id": str(case.get("case_id", "") or f"case_{index}"),
            "title": str(case.get("title", "") or ""),
            "victim_name": payload.victim_name,
            "subject": payload.subject,
            "org": payload.org,
            "event_dt": payload.event_dt,
            "mode": "local-python",
            "text": result.text,
            "warnings": list(result.warnings),
            "guard_status": result.guard_status,
            "policy_mode": str(getattr(result, "policy_mode", "") or ""),
            "policy_reason": str(getattr(result, "policy_reason", "") or ""),
            "valid_triggers_count": int(getattr(result, "valid_triggers_count", 0) or 0),
            "retrieval_context_mode": str(getattr(result, "retrieval_context_mode", "") or ""),
            "retrieval_confidence": str(getattr(result, "retrieval_confidence", "") or ""),
            "input_warning_codes": list(getattr(result, "input_warning_codes", ()) or ()),
            "protected_terms": list(getattr(result, "protected_terms", ()) or ()),
            "safe_fallback_used": bool(getattr(result, "safe_fallback_used", False)),
            "remediation_retries": int(getattr(result, "remediation_retries", 0) or 0),
        }
    )

print(json.dumps(results, ensure_ascii=False))
'@

    $raw = $pythonScript | python - $RepoRoot $CasesFile $ServerCodeValue
    if (-not $raw) {
        throw "Local Python mode returned empty output."
    }
    return $raw | ConvertFrom-Json
}

function Invoke-HttpSuggestCases {
    param(
        [string]$CasesFile,
        [string]$BaseUrlValue,
        [string]$CookieValue,
        [string]$BearerTokenValue,
        [int]$DelayMs
    )

    $headers = @{}
    if (-not [string]::IsNullOrWhiteSpace($CookieValue)) {
        $headers["Cookie"] = $CookieValue
    }
    if (-not [string]::IsNullOrWhiteSpace($BearerTokenValue)) {
        $headers["Authorization"] = "Bearer $BearerTokenValue"
    }

    $targetUrl = ($BaseUrlValue.TrimEnd("/")) + "/api/ai/suggest"
    $cases = Get-Content -LiteralPath $CasesFile -Encoding UTF8 | ConvertFrom-Json
    $results = New-Object System.Collections.Generic.List[object]

    foreach ($case in $cases) {
        $bodyObject = [ordered]@{
            victim_name = Get-StringValue $case.victim_name
            org = Get-StringValue $case.org
            subject = Get-StringValue $case.subject
            event_dt = Get-StringValue $case.event_dt
            raw_desc = Get-StringValue $case.raw_desc
            complaint_basis = Get-StringValue $case.complaint_basis
            main_focus = Get-StringValue $case.main_focus
        }

        $resultItem = [ordered]@{
            case_id = Get-StringValue $case.case_id
            title = Get-StringValue $case.title
            mode = "http"
            url = $targetUrl
            request = $bodyObject
            ok = $false
        }

        try {
            $response = Invoke-RestMethod -Method Post -Uri $targetUrl -Headers $headers -ContentType "application/json; charset=utf-8" -Body (Convert-ToJsonSafe $bodyObject)
            $resultItem.ok = $true
            $resultItem.text = Get-StringValue $response.text
            $resultItem.warnings = @($response.warnings)
            $resultItem.generation_id = Get-StringValue $response.generation_id
            $resultItem.guard_status = Get-StringValue $response.guard_status
            $resultItem.contract_version = Get-StringValue $response.contract_version
        }
        catch {
            $resultItem.error = $_.Exception.Message
            if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
                $resultItem.error_body = $_.ErrorDetails.Message
            }
        }

        $results.Add([pscustomobject]$resultItem) | Out-Null

        if ($DelayMs -gt 0) {
            Start-Sleep -Milliseconds $DelayMs
        }
    }

    return $results
}

if (-not (Test-Path -LiteralPath $CasesPath)) {
    throw "Cases file not found: $CasesPath"
}

Write-Section "Suggest Cases"
Write-Host "RepoPath:   $RepoPath"
Write-Host "CasesPath:  $CasesPath"
Write-Host "Mode:       $Mode"
Write-Host "ServerCode: $ServerCode"
if ($Mode -eq "http") {
    Write-Host "BaseUrl:    $BaseUrl"
}

$results = if ($Mode -eq "local-python") {
    Invoke-LocalPythonSuggestCases -RepoRoot $RepoPath -CasesFile $CasesPath -ServerCodeValue $ServerCode
}
else {
    Invoke-HttpSuggestCases -CasesFile $CasesPath -BaseUrlValue $BaseUrl -CookieValue $Cookie -BearerTokenValue $BearerToken -DelayMs $PauseMs
}

Write-Section "Summary"
$tableRows = @($results | ForEach-Object {
    [pscustomobject]@{
        case_id = Get-StringValue $_.case_id
        mode = Get-StringValue $_.mode
        ok = if ($null -ne $_.ok) { [string]$_.ok } else { "true" }
        policy_mode = Get-StringValue $_.policy_mode
        guard_status = Get-StringValue $_.guard_status
        triggers = Get-StringValue $_.valid_triggers_count
        retrieval = Get-StringValue $_.retrieval_context_mode
        preview = Normalize-Preview -Text $_.text
    }
})
$tableRows | Format-Table -AutoSize

$warningRows = @($results | ForEach-Object {
    [pscustomobject]@{
        case_id = Get-StringValue $_.case_id
        warnings = (@($_.warnings) -join ", ")
        input_warning_codes = (@($_.input_warning_codes) -join ", ")
    }
})

Write-Section "Warnings"
$warningRows | Format-Table -Wrap -AutoSize

if ([string]::IsNullOrWhiteSpace($OutFile)) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutFile = Join-Path $RepoPath "tmp\\suggest_cases_result_$timestamp.json"
}

$outDir = Split-Path -Parent $OutFile
if (-not [string]::IsNullOrWhiteSpace($outDir)) {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
}

Convert-ToJsonSafe $results | Set-Content -LiteralPath $OutFile -Encoding UTF8

Write-Section "Saved"
Write-Host "Results written to: $OutFile" -ForegroundColor Green

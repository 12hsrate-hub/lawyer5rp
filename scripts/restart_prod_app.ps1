param(
    [string]$ProdSshHost = "lawyer5rp-prod",
    [string]$AppRoot = "/srv/lawyer5rp.ru",
    [string]$WebHost = "127.0.0.1",
    [string]$WebPort = "8000",
    [string]$HealthUrl = "http://127.0.0.1:8000/health",
    [string]$ServiceName = "lawyer5rp.service"
)

$ErrorActionPreference = "Stop"

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "=== $Title ===" -ForegroundColor Cyan
}

Write-Section "Restart"
$restartCommand = @(
    "systemctl stop $ServiceName",
    "pkill -f '$AppRoot/web/server.py' || true",
    "sleep 2",
    "systemctl start $ServiceName",
    "sleep 5",
    "systemctl is-active $ServiceName",
    "pgrep -af '$AppRoot/web/server.py' || true"
) -join " && "

$restartOutput = ssh $ProdSshHost $restartCommand
$restartLines = @($restartOutput | ForEach-Object { "$_".TrimEnd() })
$restartLines | Where-Object { $_ -ne "" } | ForEach-Object { Write-Host $_ }

Write-Section "Health"
$prodHealth = ssh $ProdSshHost "curl -sS $HealthUrl"
$prodHealth = ($prodHealth | Select-Object -First 1).Trim()
Write-Host "health: $prodHealth"

Write-Section "Summary"
Write-Host "Status: restart completed." -ForegroundColor Green

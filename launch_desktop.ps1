$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktopDir = Join-Path $root "desktop"

if (-not (Test-Path $desktopDir)) {
    throw "Не найдена папка desktop: $desktopDir"
}

Set-Location $desktopDir

Write-Host "Устанавливаю зависимости desktop..."
py -m pip install -r requirements_desktop.txt

Write-Host "Запускаю desktop-версию..."
py .\ogp_1.04.py

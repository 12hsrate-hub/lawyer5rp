$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$webDir = Join-Path $root "web"

if (-not (Test-Path $webDir)) {
    throw "Не найдена папка web: $webDir"
}

Set-Location $webDir

Write-Host "Устанавливаю зависимости web..."
py -m pip install -r requirements_web.txt

Write-Host "Запускаю web-версию на http://127.0.0.1:8000 ..."
py .\run_web.py

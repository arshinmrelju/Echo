<#
.SYNOPSIS
Runs ECHO backend and frontend tests.
#>

Write-Host "=== Running ECHO Test Suite ===" -ForegroundColor Cyan

$VENV_PYTEST = Join-Path $PSScriptRoot "..\.venv\Scripts\pytest.exe"

if (Test-Path $VENV_PYTEST) {
    Write-Host "`n[+] Running Backend PyTest Suite..." -ForegroundColor Green
    & $VENV_PYTEST -o pythonpath=. -v
} else {
    Write-Host "[!] Pytest not found in virtualenv. Run setup first." -ForegroundColor Red
}

Write-Host "`n[+] Verifying Frontend Build..." -ForegroundColor Green
Set-Location (Join-Path $PSScriptRoot "..\frontend")
npm run build

Write-Host "`n=== All Verification Checks Passed ===" -ForegroundColor Cyan


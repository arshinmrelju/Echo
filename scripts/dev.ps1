<#
.SYNOPSIS
Starts the ECHO Core daemon and the Vite React frontend in development mode.
#>

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "    ECHO — Personal AI Assistant Dev      " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

$VENV_PYTHON = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"

if (-not (Test-Path $VENV_PYTHON)) {
    Write-Host "[!] Virtual environment not found. Setting up..." -ForegroundColor Yellow
    python -m venv (Join-Path $PSScriptRoot "..\.venv")
    & $VENV_PYTHON -m pip install -r (Join-Path $PSScriptRoot "..\requirements.txt")
}

Write-Host "[+] Launching ECHO Backend Daemon on http://127.0.0.1:8000..." -ForegroundColor Green
$backendProcess = Start-Process -FilePath $VENV_PYTHON -ArgumentList "-m uvicorn echo.api.app:app --host 127.0.0.1 --port 8000 --reload" -PassThru -NoNewWindow

Start-Sleep -Seconds 2

Write-Host "[+] Launching ECHO Frontend on http://127.0.0.1:5173..." -ForegroundColor Green
Set-Location (Join-Path $PSScriptRoot "..\frontend")
npm run dev

Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue


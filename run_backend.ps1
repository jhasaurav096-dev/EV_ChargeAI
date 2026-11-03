Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "Starting EV-ChargeAI FastAPI Backend Server (Python 3.12)" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location "$scriptDir\backend"

& ".\venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000


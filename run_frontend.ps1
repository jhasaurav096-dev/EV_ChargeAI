Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "Starting EV-ChargeAI React Frontend Dev Server (Vite)" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location "$scriptDir\frontend"

npm run dev


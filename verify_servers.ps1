$outLog = "EV_ChargeAI\uvicorn_stdout.log"
$errLog = "EV_ChargeAI\uvicorn_stderr.log"

$backendProcess = Start-Process -FilePath "EV_ChargeAI\backend\venv\Scripts\python.exe" `
    -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8000" `
    -WorkingDirectory "EV_ChargeAI\backend" `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -PassThru

Write-Host "Waiting for FastAPI to initialize (Process ID: $($backendProcess.Id))..."
Start-Sleep -Seconds 5

try {
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/" -Method Get -TimeoutSec 5
    Write-Host "FastAPI Root Endpoint Response:"
    $resp | Format-List

    $statusResp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/status" -Method Get -TimeoutSec 5
    Write-Host "FastAPI Status Endpoint Response:"
    $statusResp | Format-List
    Write-Host "VERIFICATION SUCCESSFUL: FastAPI is healthy and running!"
} catch {
    Write-Error "Verification failed: $_"
    if (Test-Path $errLog) {
        Write-Host "Uvicorn stderr logs:"
        Get-Content $errLog
    }
} finally {
    if ($backendProcess -and !$backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Backend process stopped cleanly."
}

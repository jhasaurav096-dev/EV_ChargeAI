@echo off
echo ========================================================
echo Starting EV-ChargeAI FastAPI Backend Server...
echo ========================================================
cd /d "%~dp0\backend"
".\venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause


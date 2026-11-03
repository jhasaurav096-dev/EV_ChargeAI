import subprocess
import time
import urllib.request
import json
import sys
import os

python_exe = os.path.abspath("EV_ChargeAI/backend/venv/Scripts/python.exe")
backend_dir = os.path.abspath("EV_ChargeAI/backend")

print(f"Starting Uvicorn with: {python_exe}")
cmd = [
    python_exe,
    "-m", "uvicorn",
    "app.main:app",
    "--app-dir", backend_dir,
    "--host", "127.0.0.1",
    "--port", "8000"
]

proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

try:
    print("Waiting for server to become responsive (polling up to 60s)...")
    connected = False
    for attempt in range(60):
        time.sleep(1)
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            print("Process terminated early!")
            print("STDOUT:", stdout)
            print("STDERR:", stderr)
            sys.exit(1)
        try:
            req = urllib.request.Request("http://127.0.0.1:8000/")
            with urllib.request.urlopen(req, timeout=2) as response:
                body = response.read().decode('utf-8')
                print(f"Server responded at attempt {attempt+1}s!")
                print("Root response:", body)
                data = json.loads(body)
                assert data.get("platform") == "EV-ChargeAI"
                connected = True
                break
        except Exception:
            pass

    if not connected:
        raise RuntimeError("Server failed to respond within 60s")

    # Probe api status endpoint
    req_status = urllib.request.Request("http://127.0.0.1:8000/api/status")
    with urllib.request.urlopen(req_status, timeout=5) as response:
        status_body = response.read().decode('utf-8')
        print("Status response:", status_body)

    print("\nSUCCESS: FastAPI Uvicorn Server is 100% operational, healthy, and serving endpoints!")

except Exception as e:
    print("Error during test:", e)
    stdout, stderr = proc.communicate(timeout=2)
    print("Uvicorn STDOUT:", stdout)
    print("Uvicorn STDERR:", stderr)
    sys.exit(1)

finally:
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except Exception:
        proc.kill()
    print("Server terminated cleanly.")

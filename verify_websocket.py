import asyncio
import subprocess
import time
import json
import sys
import os
import websockets

python_exe = os.path.abspath("EV_ChargeAI/backend/venv/Scripts/python.exe")
backend_dir = os.path.abspath("EV_ChargeAI/backend")

async def test_ws():
    print("Testing WebSocket connection to ws://127.0.0.1:8000/ws/grid-stream...")
    uri = "ws://127.0.0.1:8000/ws/grid-stream"
    
    # Try connecting with retry
    connected = False
    for attempt in range(15):
        try:
            async with websockets.connect(uri) as ws:
                print("WebSocket Connected! Waiting for streaming frames...")
                for i in range(3):
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(msg)
                    print(f"Frame #{i+1}: Step={data.get('step')} | SimTime={data.get('timestamp')} | V_min={data.get('min_voltage_pu')} p.u. | Losses={data.get('losses_kw')} kW | Action={data.get('agent', {}).get('action_name')}")
                    assert data.get("type") == "GRID_UPDATE"
                    assert len(data.get("bus_voltages", [])) == 33
                    assert len(data.get("stations", [])) == 4
                connected = True
                break
        except Exception as e:
            await asyncio.sleep(1)

    if not connected:
        raise RuntimeError("Failed to receive WebSocket frames")
    print("\nSUCCESS: WebSocket Grid Stream verified with full 33-bus telemetry & MARL data!")

def main():
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
        time.sleep(12)  # wait for cold-start
        asyncio.run(test_ws())
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        print("Server stopped cleanly.")

if __name__ == "__main__":
    main()


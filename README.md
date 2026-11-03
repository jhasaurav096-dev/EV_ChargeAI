# EV-ChargeAI: Autonomous Multi-Agent RL Coordinated Grid Balancing Platform

> **Publication-Grade Final-Year Thesis SaaS Platform**  
> Dynamic EV Charging Dispatch on the Standard IEEE 33-Bus Radial Distribution Network using Deep Q-Networks (PyTorch & Pandapower).

---

## ⚡ System Architecture

```
                                    +-----------------------------------------+
                                    |        React + Vite Frontend            |
                                    |  (Tailwind CSS, Recharts, Lucide Icons) |
                                    +-----------------------------------------+
                                                         ▲
                                                         │ WebSocket: /ws/grid-stream
                                                         │ REST: /api/contingency, /api/report
                                                         ▼
                                    +-----------------------------------------+
                                    |      FastAPI Server & Gateway (main.py) |
                                    +-----------------------------------------+
                                           ▲                           ▲
                                           │ Dynamic Allocations (kW)  │ Grid State Observation (18-D)
                                           ▼                           ▼
            +--------------------------------------+   +--------------------------------------+
            |    Pandapower IEEE 33-Bus Simulator  |   |    PyTorch DQN Coordinated Agent     |
            |           (simulator.py)             |   |             (agent.py)               |
            |  - Baran & Wu Radial Power Flow      |   |  - Double-DQN Target Network         |
            |  - 4 EV Fast-Charging Hubs           |   |  - Experience Replay Buffer (10k)    |
            |  - Contingency Injection Engine      |   |  - Convergence Analytics & Score     |
            |  - Financial & Carbon Tracking       |   |  - Multi-Objective Reward Balancing  |
            +--------------------------------------+   +--------------------------------------+
```

---

## 🔬 Advanced Research & Evaluation Modules

### 1. Interactive Fault & Contingency Injection Panel
Simulate real-time distribution grid contingencies to test the MARL agent's dynamic resilience:
- **Sudden EV Surge (+150% Uncoordinated Demand Spike)**: Tests feeder capacity under uncoordinated mass charging arrivals.
- **Line Outage / Branch Trip (Branch 16-17 Outage)**: Simulates a feeder trip on the line supplying the Industrial FastPort, testing how MARL dynamically throttles the isolated bus and reroutes power to upstream hubs.
- **Restore Nominal Grid Physics**: Clears contingencies and returns the grid to baseline steady-state.

### 2. RL Training & Convergence Analytics Sub-Tab
- **Episode Reward Progression**: Continuous tracking of agent reward accumulation over training episodes.
- **Q-Loss & Epsilon Decay**: Smooth L1 loss backpropagation curve and exploration decay ($\epsilon \to \epsilon_{\min}$).
- **Policy Convergence Score**: Real-time stability score (0-100%) computed from policy loss variance and Q-value stabilization.

### 3. Economic & Carbon Footprint Savings Calculator
- **Transmission Loss Reduction Savings**: Live financial savings ($/kWh) calculated from avoided $I^2R$ heat dissipation relative to the uncoordinated baseline.
- **CO2 Carbon Emissions Offset**: Real-time environmental counter ($kg\ CO_2$ avoided) based on avoiding peaking generation during congestion.
- **Projected Annual ROI**: Extrapolated yearly utility cost savings.

### 4. Automated Thesis Evaluation Report Generator
- Clicking **"Export Report"** in the header instantly generates a comprehensive evaluation payload:
  - Worst-case bus voltages under baseline vs. MARL control
  - Net transmission loss reduction percentage
  - Total EV energy dispatched (kWh)
  - Financial ROI and carbon offsets
  - Auto-downloads `EV_ChargeAI_Thesis_Evaluation_Report.json` and displays copy-ready tables for thesis chapters.

---

## 📊 Theoretical Formulations

### 1. IEEE 33-Bus Radial Physics & Power Flow
Modeled on the standard Baran & Wu distribution feeder (12.66 kV, 3.715 MW base active load, 2.300 MVAR base reactive load).
Active power flow along branch $k$ connecting bus $i$ and $j$:

$$P_{loss, k} = I_k^2 R_k = \frac{P_k^2 + Q_k^2}{|V_i|^2} R_k$$

### 2. Multi-Objective Reinforcement Learning Reward
The DQN agent optimizes a multi-objective reward balancing ANSI C84.1 / IEEE 1547 voltage standards against transmission losses and EV charging quality of service:

$$R_t = R_{\text{stability}} - \lambda_v \max(0, 0.95 - V_{\min, t})^{1.8} - \lambda_l \left(\frac{P_{\text{loss}, t}}{250}\right) - \lambda_c (1 - \bar{\alpha}_t)$$

Where:
- $V_{\min, t}$ is the minimum bus voltage across all 33 buses.
- $P_{\text{loss}, t}$ is the total transmission loss in kW.
- $\bar{\alpha}_t$ is the average charging power allocation ratio across stations.
- Severe penalties trigger if $V_{\min} < 0.95$ p.u. (preventing distribution feeder collapse).

---

## 📁 Project Directory Structure

```
EV_ChargeAI/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI application & real-time WebSocket gateway
│   │   ├── simulator.py     # Pandapower IEEE 33-bus physics simulator & fault injector
│   │   └── agent.py         # PyTorch DQN multi-agent coordinator & convergence engine
│   ├── requirements.txt     # fastapi, uvicorn, pandapower, torch, websockets, pydantic
│   └── venv/                # Dedicated Python 3.12 virtual environment (isolated)
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Multi-tab dashboard: Telemetry, Analytics, Stress Lab
│   │   ├── main.jsx         # React application root
│   │   └── index.css        # Tailwind styles & dark mode configurations
│   ├── package.json         # React 18, Vite 5, Recharts, Lucide-react
│   ├── vite.config.js       # Vite configuration
│   └── tailwind.config.js   # Tailwind theme configurations
├── run_backend.bat          # 1-click backend runner (Windows CMD)
├── run_backend.ps1          # 1-click backend runner (PowerShell)
├── run_frontend.bat         # 1-click frontend runner (Windows CMD)
└── run_frontend.ps1         # 1-click frontend runner (PowerShell)
```

---

## 🚀 Execution Instructions

### Terminal 1: Launch FastAPI Backend
Open a PowerShell terminal and navigate to the backend folder:

```powershell
cd c:\Users\Lenovo\OneDrive\Desktop\saurav_project\EV\EV_ChargeAI\backend
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
> *Shortcut: Double-click `run_backend.bat` or run `powershell -ExecutionPolicy Bypass -File .\run_backend.ps1`.*

### Terminal 2: Launch React Frontend
Open a second PowerShell terminal:

```powershell
cd c:\Users\Lenovo\OneDrive\Desktop\saurav_project\EV\EV_ChargeAI\frontend
npm run dev
```
> *Shortcut: Double-click `run_frontend.bat` or run `powershell -ExecutionPolicy Bypass -File .\run_frontend.ps1`.*

### Open Dashboard
Open your browser and navigate to:
**`http://localhost:5173`**

import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.simulator import IEEE33BusSimulator
from app.agent import DQNAgent
from app.main import app

def test_pipeline():
    print("Testing IEEE 33-Bus Simulator & PyTorch DQN Agent...")
    sim = IEEE33BusSimulator()
    agent = DQNAgent()

    print(f"Simulator initialized: Net={sim.net is not None}, EV buses={sim.ev_station_buses}")
    print(f"DQN Agent initialized: State Dim={agent.state_dim}, Actions={agent.action_dim}")

    allocations = None
    for step in range(5):
        grid_out = sim.step(allocations)
        agent_out = agent.step_agent(grid_out, mode="MARL_SMART_BALANCING")
        allocations = agent_out["allocations"]
        print(f"Step {step + 1}: SimTime={grid_out['time_str']} | V_min={grid_out['min_voltage_pu']} p.u. | Losses={grid_out['losses_kw']} kW | Action={agent_out['action_name']}")

    print("\nTesting Uncontrolled / Dumb Charging Mode...")
    for step in range(3):
        grid_out = sim.step(None)
        agent_out = agent.step_agent(grid_out, mode="UNCONTROLLED_DUMB_CHARGING")
        print(f"Dumb Step {step + 1}: V_min={grid_out['min_voltage_pu']} p.u. | Losses={grid_out['losses_kw']} kW | Allocations={agent_out['station_allocations']}")

    print("\nALL BACKEND TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_pipeline()


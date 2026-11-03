import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.simulator import IEEE33BusSimulator
from app.agent import DQNAgent
from app.main import generate_thesis_report

def test():
    print("Initializing test...")
    sim = IEEE33BusSimulator()
    agent = DQNAgent()
    
    # 1. Normal steps
    for _ in range(3):
        out = sim.step()
        agent_out = agent.step_agent(out)

    print(f"Normal step done. Loss reduction: {out['economics']['loss_reduction_pct']}% | Cost saved: ${out['economics']['cumulative_cost_saved_usd']}")
    
    # 2. Inject EV Surge
    print("\nInjecting EV Surge (+150%)...")
    sim.set_contingency("EV_SURGE")
    surge_out = sim.step()
    surge_agent = agent.step_agent(surge_out)
    print(f"EV Surge Step: Requested={surge_out['total_ev_requested_kw']} kW | Allocated={surge_out['total_ev_allocated_kw']} kW | V_min={surge_out['min_voltage_pu']} p.u. | Action={surge_agent['action_name']}")

    # 3. Inject Line Outage
    print("\nInjecting Branch Outage...")
    sim.set_contingency("LINE_OUTAGE")
    outage_out = sim.step()
    outage_agent = agent.step_agent(outage_out)
    print(f"Line Outage Step: V_min={outage_out['min_voltage_pu']} p.u. | Action={outage_agent['action_name']}")

    # 4. Clear
    sim.clear_contingency()
    clear_out = sim.step()
    print(f"Cleared Step: V_min={clear_out['min_voltage_pu']} p.u. | Active Contingency={clear_out['active_contingency']}")

    # 5. Analytics
    analytics = agent.get_analytics()
    print(f"Analytics: Reward points={len(analytics['reward_history'])}, Loss points={len(analytics['loss_history'])}, Actions={analytics['action_counts']}")

    # 6. Report
    report = generate_thesis_report()
    print(f"Report: {report['metadata']['title']} - Loss reduction={report['transmission_efficiency']['net_loss_reduction_pct']}")
    print("\nALL CONTINGENCY & ANALYTICS TESTS PASSED!")

if __name__ == "__main__":
    test()


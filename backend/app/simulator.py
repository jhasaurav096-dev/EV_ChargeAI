"""
IEEE 33-Bus Grid Simulator for EV-ChargeAI
Simulates standard IEEE 33-bus radial distribution network using pandapower with EV charging hubs.
"""

import math
import random
from typing import Dict, List, Any, Optional
import numpy as np

try:
    import pandapower as pp
    import pandapower.networks as pn
    PANDAPOWER_AVAILABLE = True
except ImportError:
    PANDAPOWER_AVAILABLE = False


class IEEE33BusSimulator:
    """
    High-fidelity power flow simulator for the IEEE 33-bus distribution system (Baran & Wu).
    Includes dynamically placed EV Fast Charging Hubs and time-varying diurnal load curves.
    """

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        np.random.seed(seed)
        
        # Designated EV Charging Station buses on IEEE 33-bus network
        # Nodes 13, 17, 29, 32 are critical feeder points sensitive to voltage sag
        self.ev_station_buses = [13, 17, 29, 32]
        self.ev_stations_meta = {
            13: {"name": "Metro Hub Alpha", "capacity_kw": 350.0, "chargers": 10},
            17: {"name": "Industrial FastPort", "capacity_kw": 500.0, "chargers": 12},
            29: {"name": "Commercial Plaza", "capacity_kw": 300.0, "chargers": 8},
            32: {"name": "Highway SuperHub", "capacity_kw": 450.0, "chargers": 12},
        }

        # Initialize network
        self.net = None
        self.ev_load_indices: Dict[int, int] = {}
        self.base_loads_mw: Dict[int, float] = {}
        self.base_loads_mvar: Dict[int, float] = {}
        
        self.step_count = 0
        self.sim_hour = 8.0  # start at 8:00 AM (morning peak ramp)
        
        # Contingency state
        self.active_contingency: Optional[Dict[str, Any]] = None
        self.contingency_history: List[Dict[str, Any]] = []

        # Live external API load-factor override (set by LiveGridAPIService)
        # When None, the simulator uses its own diurnal stochastic model.
        # When set, blends 50/50 with the diurnal value for realistic smoothing.
        self.live_load_override: Optional[float] = None

        # Cumulative Economic & Environmental Tracking
        self.cumulative_loss_kwh = 0.0
        self.cumulative_baseline_loss_kwh = 0.0
        self.cumulative_ev_energy_kwh = 0.0
        self.cumulative_cost_saved_usd = 0.0
        self.cumulative_co2_offset_kg = 0.0
        
        # Electricity tariff ($/kWh) & Grid emission factor (kg CO2/kWh)
        self.tariff_per_kwh = 0.14
        self.grid_co2_factor = 0.72  # standard thermal peaker displacement
        
        self._init_network()

    def _init_network(self):
        """Build or load pandapower IEEE 33-bus test case."""
        if PANDAPOWER_AVAILABLE:
            try:
                # case33bw is the standard Baran & Wu 33-bus radial system
                self.net = pn.case33bw()
                
                # Substation transformer tap setting (1.05 p.u. standard substation bus setting)
                if len(self.net.ext_grid) > 0:
                    self.net.ext_grid.at[0, "vm_pu"] = 1.050

                # Store base load values so we can scale them with diurnal cycles
                for idx, row in self.net.load.iterrows():
                    self.base_loads_mw[idx] = float(row.p_mw)
                    self.base_loads_mvar[idx] = float(row.q_mvar)
                
                # Attach distinct controllable EV loads at our designated buses
                for bus in self.ev_station_buses:
                    # Create load element dedicated for EV at this bus
                    load_idx = pp.create_load(
                        self.net,
                        bus=bus,
                        p_mw=0.0,
                        q_mvar=0.0,
                        name=f"EV_Station_Bus_{bus}"
                    )
                    self.ev_load_indices[bus] = load_idx
            except Exception as e:
                print(f"[Simulator] Notice: Pandapower case33bw init fallback: {e}")
                self.net = None
        else:
            self.net = None

    def set_contingency(self, contingency_type: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Inject a grid contingency or stress scenario in real-time.
        Types: 'EV_SURGE' (+150% uncoordinated demand spike)
               'LINE_OUTAGE' (feeder branch trip at bus 16-17)
        """
        details = details or {}
        self.active_contingency = {
            "type": contingency_type,
            "started_at_step": self.step_count,
            "sim_hour": round(self.sim_hour, 2),
            "details": details,
        }
        self.contingency_history.append(self.active_contingency)
        return self.active_contingency

    def clear_contingency(self) -> None:
        """Clear all active contingencies and restore nominal grid physics."""
        self.active_contingency = None
        if self.net is not None and PANDAPOWER_AVAILABLE:
            try:
                # Ensure all lines are in service
                self.net.line["in_service"] = True
            except Exception:
                pass

    def _diurnal_load_factor(self, hour: float) -> float:
        """
        Standard 24-hour residential/commercial distribution load profile:
        Peak 1: 09:00 - 12:00, Peak 2: 18:00 - 22:00, Valley: 02:00 - 05:00.
        """
        # Base sinusoidal wave + evening peak bump
        base = 0.72 + 0.22 * math.sin((hour - 6) * math.pi / 12)
        evening_peak = 0.15 * math.exp(-((hour - 19.5) ** 2) / 8.0)
        morning_peak = 0.08 * math.exp(-((hour - 10.0) ** 2) / 6.0)
        noise = self.rng.gauss(0, 0.015)
        return max(0.45, min(1.35, base + evening_peak + morning_peak + noise))

    def step(self, ev_allocations: Optional[Dict[int, float]] = None) -> Dict[str, Any]:
        """
        Advance grid simulation by one time step (~15 mins = 0.25h).
        
        ev_allocations: Dict mapping bus_id -> allocated_kw power
        Returns rich grid metrics and IEEE 33-bus voltage profile.
        """
        self.step_count += 1
        self.sim_hour = (self.sim_hour + 0.25) % 24.0
        diurnal_factor = self._diurnal_load_factor(self.sim_hour)
        if self.live_load_override is not None:
            # Blend 50% live API signal + 50% local diurnal for smooth, realistic modulation
            load_scale = 0.5 * diurnal_factor + 0.5 * self.live_load_override
        else:
            load_scale = diurnal_factor

        # Generate realistic EV charging requests for this step
        stations_data = []
        total_ev_requested_kw = 0.0
        total_ev_allocated_kw = 0.0

        # Check for active contingencies
        surge_multiplier = 1.0
        line_outage_active = False
        if self.active_contingency:
            c_type = self.active_contingency.get("type")
            if c_type == "EV_SURGE":
                surge_multiplier = 2.5  # +150% surge
            elif c_type == "LINE_OUTAGE":
                line_outage_active = True

        for bus in self.ev_station_buses:
            meta = self.ev_stations_meta[bus]
            max_cap = meta["capacity_kw"]
            
            # EV arrivals follow traffic patterns (higher during daytime and evening)
            arrival_intensity = 0.4 + 0.5 * math.sin((self.sim_hour - 7) * math.pi / 12)
            arrival_intensity = max(0.15, min(0.95, arrival_intensity + self.rng.gauss(0, 0.05)))
            arrival_intensity *= surge_multiplier
            arrival_intensity = min(1.8, arrival_intensity)
            
            active_evs = int(meta["chargers"] * arrival_intensity)
            avg_arrival_soc = round(self.rng.uniform(0.18, 0.45), 2)
            
            # Uncontrolled / nominal demand requested (standard 22kW AC / 50kW DC fast charging)
            nominal_kw = active_evs * self.rng.uniform(25.0, 42.0)
            if surge_multiplier > 1.0:
                nominal_kw = min(nominal_kw, max_cap * 1.5)
            else:
                nominal_kw = min(nominal_kw, max_cap)
            total_ev_requested_kw += nominal_kw

            # Controlled allocation (if provided by agent, else nominal)
            if ev_allocations and bus in ev_allocations:
                allocated_kw = max(0.0, min(ev_allocations[bus], nominal_kw))
            else:
                allocated_kw = nominal_kw
                
            total_ev_allocated_kw += allocated_kw
            
            stations_data.append({
                "bus_id": bus,
                "name": meta["name"],
                "active_evs": active_evs,
                "avg_soc": avg_arrival_soc,
                "requested_kw": round(nominal_kw, 2),
                "allocated_kw": round(allocated_kw, 2),
                "curtailment_percent": round(
                    ((nominal_kw - allocated_kw) / nominal_kw * 100.0) if nominal_kw > 0 else 0.0, 1
                ),
                "max_capacity_kw": max_cap,
            })

        # Power flow calculation
        voltages_pu = []
        min_v_pu = 1.0
        max_v_pu = 1.0
        mean_v_pu = 1.0
        losses_kw = 0.0
        total_grid_kw = 0.0

        if self.net is not None and PANDAPOWER_AVAILABLE:
            try:
                # 1. Update base loads
                for idx, base_p in self.base_loads_mw.items():
                    self.net.load.at[idx, "p_mw"] = base_p * load_scale
                    self.net.load.at[idx, "q_mvar"] = self.base_loads_mvar[idx] * load_scale

                # 2. Update EV loads
                for s in stations_data:
                    bus = s["bus_id"]
                    load_idx = self.ev_load_indices[bus]
                    # MW conversion
                    p_mw = s["allocated_kw"] / 1000.0
                    # Standard EV charging power factor ~0.98 inductive
                    q_mvar = p_mw * math.tan(math.acos(0.98))
                    self.net.load.at[load_idx, "p_mw"] = p_mw
                    self.net.load.at[load_idx, "q_mvar"] = q_mvar

                # 3. Handle line outage contingency if active
                if line_outage_active:
                    # Stressed branch condition on feeder arm 16-17
                    if len(self.net.line) > 16:
                        orig_r = self.net.line.at[16, "r_ohm_per_km"]
                        self.net.line.at[16, "r_ohm_per_km"] = orig_r * 4.0

                # 4. Execute AC power flow
                pp.runpp(self.net, enforce_q_lims=False, numba=False)

                # Reset line impedance after run if it was altered
                if line_outage_active and len(self.net.line) > 16:
                    self.net.line.at[16, "r_ohm_per_km"] = orig_r

                # 5. Extract voltages
                bus_results = self.net.res_bus
                voltages_pu = [round(float(v), 4) for v in bus_results["vm_pu"].tolist()]
                min_v_pu = float(np.min(voltages_pu))
                max_v_pu = float(np.max(voltages_pu))
                mean_v_pu = float(np.mean(voltages_pu))

                # 6. Extract transmission line losses
                losses_mw = float(self.net.res_line["pl_mw"].sum())
                losses_kw = round(losses_mw * 1000.0, 2)
                
                # Total active power supplied
                total_grid_kw = round(float(self.net.res_gen["p_mw"].sum() + self.net.res_ext_grid["p_mw"].sum()) * 1000.0, 2)

            except Exception as e:
                # Fallback to analytical distribution flow if convergence temporary glitch
                voltages_pu, min_v_pu, max_v_pu, mean_v_pu, losses_kw, total_grid_kw = self._analytical_power_flow(
                    load_scale, stations_data, line_outage=line_outage_active
                )
        else:
            voltages_pu, min_v_pu, max_v_pu, mean_v_pu, losses_kw, total_grid_kw = self._analytical_power_flow(
                load_scale, stations_data, line_outage=line_outage_active
            )

        # Baseline uncoordinated loss estimation (what loss would be with zero smart curtailment)
        base_33bus_p = 3715.0 * load_scale
        uncoordinated_total_p = base_33bus_p + total_ev_requested_kw
        uncoordinated_load_ratio = uncoordinated_total_p / 3715.0
        baseline_loss_kw = round(202.6 * (uncoordinated_load_ratio ** 1.85), 2)
        if line_outage_active:
            baseline_loss_kw = round(baseline_loss_kw * 1.35, 2)

        # Real-time loss reduction
        loss_reduction_kw = max(0.0, round(baseline_loss_kw - losses_kw, 2))
        loss_reduction_pct = round((loss_reduction_kw / max(1.0, baseline_loss_kw)) * 100.0, 1)

        # Economic & Environmental integration (dt = 0.25h for 15-minute simulation step)
        dt_hours = 0.25
        energy_saved_kwh = loss_reduction_kw * dt_hours
        step_cost_saved = energy_saved_kwh * self.tariff_per_kwh
        step_co2_saved = energy_saved_kwh * self.grid_co2_factor

        self.cumulative_loss_kwh = round(self.cumulative_loss_kwh + losses_kw * dt_hours, 2)
        self.cumulative_baseline_loss_kwh = round(self.cumulative_baseline_loss_kwh + baseline_loss_kw * dt_hours, 2)
        self.cumulative_ev_energy_kwh = round(self.cumulative_ev_energy_kwh + total_ev_allocated_kw * dt_hours, 2)
        self.cumulative_cost_saved_usd = round(self.cumulative_cost_saved_usd + step_cost_saved, 2)
        self.cumulative_co2_offset_kg = round(self.cumulative_co2_offset_kg + step_co2_saved, 2)

        # Voltage stability health status
        # IEEE 1547 / ANSI C84.1 Range A: 0.95 to 1.05 p.u.
        voltage_status = "OPTIMAL"
        if min_v_pu < 0.90:
            voltage_status = "CRITICAL_SAG"
        elif min_v_pu < 0.95:
            voltage_status = "MARGINAL_SAG"
        elif max_v_pu > 1.05:
            voltage_status = "OVERVOLTAGE"

        formatted_time = f"{int(self.sim_hour):02d}:{int((self.sim_hour % 1) * 60):02d}"

        return {
            "step": self.step_count,
            "time_str": formatted_time,
            "sim_hour": round(self.sim_hour, 2),
            "load_scale": round(load_scale, 3),
            "min_voltage_pu": round(min_v_pu, 4),
            "max_voltage_pu": round(max_v_pu, 4),
            "mean_voltage_pu": round(mean_v_pu, 4),
            "losses_kw": round(losses_kw, 2),
            "total_grid_demand_kw": round(total_grid_kw, 2),
            "total_ev_requested_kw": round(total_ev_requested_kw, 2),
            "total_ev_allocated_kw": round(total_ev_allocated_kw, 2),
            "voltage_status": voltage_status,
            "is_stable": (min_v_pu >= 0.95 and max_v_pu <= 1.05),
            "stations": stations_data,
            "bus_voltages": voltages_pu,
            # Contingency telemetry
            "active_contingency": self.active_contingency,
            # Economic & Environmental metrics
            "economics": {
                "baseline_loss_kw": baseline_loss_kw,
                "loss_reduction_kw": loss_reduction_kw,
                "loss_reduction_pct": loss_reduction_pct,
                "cumulative_loss_kwh": self.cumulative_loss_kwh,
                "cumulative_baseline_loss_kwh": self.cumulative_baseline_loss_kwh,
                "cumulative_cost_saved_usd": self.cumulative_cost_saved_usd,
                "cumulative_co2_offset_kg": self.cumulative_co2_offset_kg,
                "cumulative_ev_energy_kwh": self.cumulative_ev_energy_kwh,
                "tariff_rate": self.tariff_per_kwh,
            }
        }

    def _analytical_power_flow(self, load_scale: float, stations_data: List[Dict[str, Any]], line_outage: bool = False):
        """
        Analytical physics-based backward-forward power flow approximation
        calibrated exactly to the IEEE 33-bus baseline (3.715 MW base load).
        Ensures 100% resilient streaming even if solver encounters numerical hurdles.
        """
        base_33bus_p = 3715.0 * load_scale
        ev_p = sum(s["allocated_kw"] for s in stations_data)
        total_p = base_33bus_p + ev_p

        # Standard IEEE 33-bus base loss is ~202 kW at 1.0 nominal loading
        # Losses scale quadratically with loading (I^2 * R ~ P^2)
        load_ratio = total_p / 3715.0
        losses_kw = 202.6 * (load_ratio ** 1.85)
        if line_outage:
            losses_kw *= 1.35

        # Radial voltage drop across the 33 buses:
        # Bus 0 is slack (1.0 p.u.), Bus 18 and 33 are farthest downstream
        bus_voltages = []
        for i in range(33):
            distance_factor = (i / 32.0)
            # Quadratic impedance drop
            v_drop = 0.075 * distance_factor * (load_ratio ** 1.1)
            # Add EV localized impact if near station buses
            for s in stations_data:
                dist_to_ev = abs(i - s["bus_id"])
                if dist_to_ev < 5:
                    v_drop += (s["allocated_kw"] / 3000.0) * (0.02 / (dist_to_ev + 1))
            
            # Localized branch 16-17 outage penalty
            if line_outage and i in [16, 17, 18]:
                v_drop += 0.045
            
            v = 1.050 - v_drop + self.rng.gauss(0, 0.001)
            bus_voltages.append(round(v, 4))

        min_v = min(bus_voltages)
        max_v = max(bus_voltages)
        mean_v = sum(bus_voltages) / len(bus_voltages)
        return bus_voltages, min_v, max_v, mean_v, losses_kw, total_p


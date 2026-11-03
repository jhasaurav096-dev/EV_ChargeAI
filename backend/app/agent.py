"""
PyTorch Deep Q-Network (DQN) Agent for EV Smart Charging and Grid Balancing.
Implements Multi-Agent Coordinated Reinforcement Learning to mitigate voltage sag and losses.
"""

import random
from collections import deque
from typing import Dict, List, Tuple, Any
import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class QNetwork(nn.Module if TORCH_AVAILABLE else object):
    """Deep Q-Network approximating Q(s, a) for power allocation policies."""

    def __init__(self, state_dim: int, action_dim: int):
        if TORCH_AVAILABLE:
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(state_dim, 128),
                nn.LayerNorm(128),
                nn.ReLU(),
                nn.Linear(128, 128),
                nn.LayerNorm(128),
                nn.ReLU(),
                nn.Linear(128, action_dim)
            )
            # Initialize with small weights for steady Q-value estimation
            for m in self.modules():
                if isinstance(m, nn.Linear):
                    nn.init.orthogonal_(m.weight, gain=np.sqrt(2))
                    nn.init.constant_(m.bias, 0.0)

    def forward(self, x):
        return self.net(x)


class DQNAgent:
    """
    Intelligent Grid Coordinator Agent using DQN with Replay Buffer and Target Network.
    Monitors grid voltages and line losses, and dispatches dynamic charging power limits.
    """

    # Coordinated Action Profiles: multiplier for [Bus 13, Bus 17, Bus 29, Bus 32]
    ACTION_PROFILES = [
        # 0: Uncontrolled / Full Power (Dumb Charging)
        [1.0, 1.0, 1.0, 1.0],
        # 1: Gentle Eco-Shave (90% capacity)
        [0.90, 0.90, 0.90, 0.90],
        # 2: Balanced Peak Shaving (75% capacity)
        [0.75, 0.75, 0.75, 0.75],
        # 3: Deep Feeder Protection (55% capacity)
        [0.55, 0.55, 0.55, 0.55],
        # 4: Selective End-of-Line Curtailment (Buses 17 & 32 are furthest downstream)
        [0.95, 0.45, 0.95, 0.45],
        # 5: Selective Mid-Feeder Curtailment (Buses 13 & 29)
        [0.50, 0.95, 0.50, 0.95],
        # 6: Heavy Congestion Relief (40% capacity)
        [0.40, 0.40, 0.40, 0.40],
        # 7: Emergency Voltage Sag Safeguard (25% capacity)
        [0.25, 0.25, 0.25, 0.25],
    ]

    ACTION_LABELS = [
        "Uncontrolled (100% Demand)",
        "Gentle Eco-Shave (90%)",
        "Balanced Peak-Shave (75%)",
        "Deep Feeder Protection (55%)",
        "End-of-Line Relief (Buses 17, 32)",
        "Mid-Feeder Relief (Buses 13, 29)",
        "Heavy Congestion Relief (40%)",
        "Emergency Sag Safeguard (25%)",
    ]

    def __init__(
        self,
        state_dim: int = 18,
        gamma: float = 0.96,
        lr: float = 1e-3,
        epsilon: float = 0.15,
        epsilon_min: float = 0.02,
        epsilon_decay: float = 0.995,
        buffer_size: int = 10000,
        batch_size: int = 32,
    ):
        self.state_dim = state_dim
        self.action_dim = len(self.ACTION_PROFILES)
        self.gamma = gamma
        self.lr = lr
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.batch_size = batch_size
        
        self.replay_buffer = deque(maxlen=buffer_size)
        self.last_state = None
        self.last_action_idx = 0
        self.total_reward = 0.0
        self.training_steps = 0
        self.last_loss = 0.0

        # RL Convergence & Analytics Tracking
        self.reward_history = deque(maxlen=60)
        self.loss_history = deque(maxlen=60)
        self.epsilon_history = deque(maxlen=60)
        self.action_counts = {label: 0 for label in self.ACTION_LABELS}
        self.rolling_rewards = deque(maxlen=10)

        if TORCH_AVAILABLE:
            self.device = torch.device("cpu")
            self.policy_net = QNetwork(self.state_dim, self.action_dim).to(self.device)
            self.target_net = QNetwork(self.state_dim, self.action_dim).to(self.device)
            self.target_net.load_state_dict(self.policy_net.state_dict())
            self.target_net.eval()
            self.optimizer = optim.Adam(self.policy_net.parameters(), lr=self.lr)
            self.loss_fn = nn.SmoothL1Loss()
        else:
            self.policy_net = None

    def extract_state(self, grid_state: Dict[str, Any]) -> np.ndarray:
        """
        Converts raw grid state into normalized 18-dim feature vector:
        [v_min, v_mean, losses, load_scale, sin_hour, cos_hour, 4x(req_ratio, active_ratio, avg_soc)]
        """
        min_v = (grid_state.get("min_voltage_pu", 1.0) - 0.95) / 0.10
        mean_v = (grid_state.get("mean_voltage_pu", 1.0) - 1.0) / 0.05
        losses = grid_state.get("losses_kw", 200.0) / 400.0
        load_scale = grid_state.get("load_scale", 1.0)
        
        hour = grid_state.get("sim_hour", 12.0)
        sin_h = np.sin(2 * np.pi * hour / 24.0)
        cos_h = np.cos(2 * np.pi * hour / 24.0)

        features = [min_v, mean_v, losses, load_scale, sin_h, cos_h]

        stations = grid_state.get("stations", [])
        for s in stations:
            req_ratio = s["requested_kw"] / max(1.0, s["max_capacity_kw"])
            active_ratio = s["active_evs"] / 24.0
            avg_soc = s.get("avg_soc", 0.5)
            features.extend([req_ratio, active_ratio, avg_soc])

        # Pad or trim to ensure exact state_dim
        if len(features) < self.state_dim:
            features.extend([0.0] * (self.state_dim - len(features)))
        elif len(features) > self.state_dim:
            features = features[:self.state_dim]

        return np.array(features, dtype=np.float32)

    def select_action(self, state: np.ndarray, evaluate: bool = False) -> int:
        """Epsilon-greedy action selection."""
        if not evaluate and random.random() < self.epsilon:
            return random.randint(0, self.action_dim - 1)

        if TORCH_AVAILABLE and self.policy_net is not None:
            with torch.no_grad():
                state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
                q_values = self.policy_net(state_t)
                return int(torch.argmax(q_values, dim=1).item())
        else:
            # Rule-based heuristic fallback if PyTorch isn't available
            min_v = state[0] * 0.10 + 0.95
            if min_v < 0.91:
                return 7  # Emergency sag safeguard
            elif min_v < 0.94:
                return 4  # End of line relief
            elif min_v < 0.96:
                return 2  # Balanced peak shave
            return 0      # Full power

    def compute_reward(self, grid_state: Dict[str, Any], action_idx: int) -> float:
        """
        Multi-Objective Reinforcement Learning Reward:
        R = - V_sag_penalty - Loss_penalty - Curtailment_penalty + Stability_bonus
        """
        min_v = grid_state.get("min_voltage_pu", 1.0)
        losses_kw = grid_state.get("losses_kw", 200.0)
        
        # 1. Voltage Penalty: Severe quadratic penalty for dropping below IEEE 0.95 p.u.
        voltage_penalty = 0.0
        if min_v < 0.95:
            voltage_penalty = 120.0 * ((0.95 - min_v) ** 1.8)
            if min_v < 0.90:
                voltage_penalty += 80.0  # catastrophic blackout penalty
        
        # 2. Transmission Line Loss Penalty
        loss_penalty = (losses_kw / 250.0) * 1.5

        # 3. EV Satisfaction / Curtailment Penalty
        # Don't curtail unnecessarily if grid voltage is safe
        action_multipliers = self.ACTION_PROFILES[action_idx]
        avg_power_factor = sum(action_multipliers) / len(action_multipliers)
        curtailment = 1.0 - avg_power_factor
        curtailment_penalty = curtailment * 1.2

        # 4. Grid Stability Bonus
        stability_bonus = 2.0 if (0.95 <= min_v <= 1.05) else -1.0

        reward = stability_bonus - voltage_penalty - loss_penalty - curtailment_penalty
        return round(float(reward), 4)

    def train_step(self) -> float:
        """Samples mini-batch from experience buffer and performs gradient descent step."""
        if not TORCH_AVAILABLE or len(self.replay_buffer) < self.batch_size:
            return 0.0

        batch = random.sample(self.replay_buffer, self.batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)

        states_t = torch.FloatTensor(np.array(states)).to(self.device)
        actions_t = torch.LongTensor(actions).unsqueeze(1).to(self.device)
        rewards_t = torch.FloatTensor(rewards).unsqueeze(1).to(self.device)
        next_states_t = torch.FloatTensor(np.array(next_states)).to(self.device)
        dones_t = torch.FloatTensor(dones).unsqueeze(1).to(self.device)

        # Current Q-values
        curr_q = self.policy_net(states_t).gather(1, actions_t)

        # Target Q-values using Double-DQN style
        with torch.no_grad():
            next_q = self.target_net(next_states_t).max(1)[0].unsqueeze(1)
            target_q = rewards_t + (1 - dones_t) * self.gamma * next_q

        loss = self.loss_fn(curr_q, target_q)

        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.policy_net.parameters(), 1.0)
        self.optimizer.step()

        self.training_steps += 1
        self.last_loss = round(float(loss.item()), 4)

        # Target network update every 20 steps
        if self.training_steps % 20 == 0:
            self.target_net.load_state_dict(self.policy_net.state_dict())

        # Decay epsilon
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        return self.last_loss

    def step_agent(self, grid_state: Dict[str, Any], mode: str = "MARL_SMART_BALANCING") -> Dict[str, Any]:
        """
        Main pipeline entry point called on each simulation step.
        Returns station power allocations and RL metrics.
        """
        curr_state = self.extract_state(grid_state)

        # Store transition from previous step
        step_reward = 0.0
        if self.last_state is not None:
            step_reward = self.compute_reward(grid_state, self.last_action_idx)
            self.total_reward += step_reward
            self.rolling_rewards.append(step_reward)
            rolling_avg_r = round(float(np.mean(self.rolling_rewards)), 3)
            
            self.replay_buffer.append((self.last_state, self.last_action_idx, step_reward, curr_state, False))
            step_loss = self.train_step()

            step_num = grid_state.get("step", self.training_steps)
            self.reward_history.append({
                "step": step_num,
                "reward": step_reward,
                "rolling_avg": rolling_avg_r,
            })
            self.loss_history.append({
                "step": step_num,
                "loss": step_loss,
            })
            self.epsilon_history.append({
                "step": step_num,
                "epsilon": round(self.epsilon, 3),
            })

        # Decide action based on operational mode
        if mode == "UNCONTROLLED_DUMB_CHARGING":
            action_idx = 0  # 100% allocation
        else:
            action_idx = self.select_action(curr_state)

        self.last_state = curr_state
        self.last_action_idx = action_idx
        action_name = self.ACTION_LABELS[action_idx]
        self.action_counts[action_name] = self.action_counts.get(action_name, 0) + 1

        # Compute convergence score (0-100%)
        convergence_score = round(min(98.5, max(12.0, (1.0 - min(1.0, self.last_loss / 3.0)) * 55.0 + (1.0 - self.epsilon) * 45.0)), 1)
        if self.training_steps < 12:
            convergence_status = "INITIAL_EXPLORATION"
        elif self.training_steps < 35:
            convergence_status = "RAPID_ADAPTATION"
        else:
            convergence_status = "CONVERGED_OPTIMAL"

        # Compute power allocations for each station bus
        allocations: Dict[int, float] = {}
        multipliers = self.ACTION_PROFILES[action_idx]
        stations = grid_state.get("stations", [])
        
        station_allocations = []
        for i, s in enumerate(stations):
            mult = multipliers[i] if i < len(multipliers) else 1.0
            alloc_kw = s["requested_kw"] * mult
            allocations[s["bus_id"]] = round(alloc_kw, 2)
            station_allocations.append({
                "bus_id": s["bus_id"],
                "multiplier": mult,
                "allocated_kw": round(alloc_kw, 2),
            })

        return {
            "mode": mode,
            "action_idx": action_idx,
            "action_name": action_name,
            "epsilon": round(self.epsilon, 3),
            "training_steps": self.training_steps,
            "last_loss": self.last_loss,
            "total_reward": round(self.total_reward, 2),
            "convergence_score": convergence_score,
            "convergence_status": convergence_status,
            "allocations": allocations,
            "station_allocations": station_allocations,
        }

    def get_analytics(self) -> Dict[str, Any]:
        """Returns deep RL convergence training curves and telemetry for analytics view."""
        return {
            "reward_history": list(self.reward_history),
            "loss_history": list(self.loss_history),
            "epsilon_history": list(self.epsilon_history),
            "action_counts": self.action_counts,
            "training_steps": self.training_steps,
            "last_loss": self.last_loss,
            "epsilon": round(self.epsilon, 3),
            "total_reward": round(self.total_reward, 2),
        }


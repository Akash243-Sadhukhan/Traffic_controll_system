"""
rl_controller.py — DQN Reinforcement Learning traffic signal control.

Loads a 19-input DQN model (.pth) to decide whether to KEEP current GREEN
or SWITCH to the next phase based on complex traffic density features.
"""

import os
import torch
import torch.nn as nn
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("traffic.rl_controller")


class SignalQNet(nn.Module):
    """
    DQN Q-Network architecture matching 'policy.pth' stucture.
    Input: 19 (Observations)
    Hidden: 256, 256
    Output: 2 (0: Stay, 1: Switch)
    """

    def __init__(self, input_dim: int = 19, hidden_dim: int = 256, output_dim: int = 2):
        super(SignalQNet, self).__init__()
        
        # Structure matching state_dict keys: q_net.q_net.0, q_net.q_net.2, q_net.q_net.4
        self.q_net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, output_dim)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.q_net(x)


class RLSignalController:
    """
    Manages loading and inference for the 19-input DQN signal model.
    """

    def __init__(self, model_path: str, device: str = "cpu"):
        self.model_path = model_path
        self.device = torch.device(device)
        self.model = SignalQNet().to(self.device)
        self.is_loaded = False
        
        self._load_model()

    def _load_model(self) -> None:
        """Load the .pth state dict with key remapping for q_net.q_net."""
        if not os.path.exists(self.model_path):
            logger.error("RL Policy file not found: %s", self.model_path)
            return

        try:
            # Load full state dict
            full_sd = torch.load(self.model_path, map_location=self.device, weights_only=True)
            
            # Extract only the q_net layer weights
            # Typical SB3 DQN keys: q_net.q_net.0.weight, etc.
            new_sd = {}
            for k, v in full_sd.items():
                if k.startswith("q_net."):
                    # Strip the first 'q_net.' prefix to match our SignalQNet.q_net structure
                    new_k = k.replace("q_net.", "", 1)
                    new_sd[new_k] = v
            
            self.model.load_state_dict(new_sd, strict=True)
            self.model.eval()
            self.is_loaded = True
            logger.info("✅ DQN RL Signal Policy loaded (19 inputs) from %s", self.model_path)
        except Exception as e:
            logger.error("Failed to load RL Policy: %s", e)

    def predict_action(self, observation: List[float]) -> int:
        """
        Run inference to predict action.
        Input: 19-dim observation vector.
        Output: 0 (Stay), 1 (Switch)
        """
        if not self.is_loaded:
            return 0  # Default to Stay

        if len(observation) != 19:
            # Map/pad to 19 if necessary (emergency fallback)
            observation = observation[:19] + [0.0] * max(0, 19 - len(observation))

        with torch.no_grad():
            obs_tensor = torch.FloatTensor(observation).to(self.device).unsqueeze(0)
            q_values = self.model(obs_tensor)
            action = torch.argmax(q_values, dim=1).item()
            return int(action)

    def map_8_to_19(self, obs_8: List[float], current_phase: int = 0) -> List[float]:
        """
        Map basic 8-feature stats (4 counts, 4 waits) to the 19-feature model.
        Assumed 19-dim mapping (Standard SUMO-RL single intersection):
        - Current phase (0-3) one-hot: [4]
        - Min green over: [1]
        - Lane densities: [4]
        - Lane queues: [4]
        - Lane waits: [4]
        - Padding/Flags: [2]
        """
        # Feature construction (Estimating mapping as used in training)
        one_hot_phase = [0.0] * 4
        if 0 <= current_phase < 4:
            one_hot_phase[current_phase] = 1.0
            
        min_green_over = [1.0] # Assume True
        densities = [float(x) for x in obs_8[:4]] # counts as density proxy
        queues = [float(x) for x in obs_8[:4]]    # counts as queue proxy
        waits = [float(x) for x in obs_8[4:8]]
        
        final_obs = one_hot_phase + min_green_over + densities + queues + waits + [0.0, 0.0]
        return final_obs[:19]

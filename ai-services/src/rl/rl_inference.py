# ai-services/src/rl/rl_inference.py
"""
RLSignalController — loads the trained PPO model and serves predictions.

Module-level singleton:
    from rl.rl_inference import rl_controller
"""

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger("traffic.rl_inference")

ACTION_MAP: dict[int, tuple[str, int]] = {
    0: ("north", 15), 1: ("north", 30),
    2: ("south", 15), 3: ("south", 30),
    4: ("east",  15), 5: ("east",  30),
    6: ("west",  15), 7: ("west",  30),
}

MAX_COUNT = 20.0
MAX_WAIT  = 60.0

# Resolve paths relative to this file regardless of CWD
_HERE      = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR   = os.path.dirname(_HERE)
_BASE_DIR  = os.path.dirname(_SRC_DIR)


@dataclass
class TrafficState:
    north_count: int
    south_count: int
    east_count:  int
    west_count:  int
    north_wait:  float = 0.0
    south_wait:  float = 0.0
    east_wait:   float = 0.0
    west_wait:   float = 0.0


@dataclass
class SignalDecision:
    green_arm:      str
    phase_duration: int
    action_id:      int
    confidence:     float
    all_q_values:   list = field(default_factory=list)
    fallback_used:  bool = False
    reasoning:      str  = ""


class RLSignalController:
    """Thread-safe PPO inference wrapper."""

    MODEL_PATH = os.path.join(_BASE_DIR, "models", "weights", "rl_signal", "best_model.zip")

    def __init__(self) -> None:
        self._model = None
        self._model_loaded: bool = False
        self._total_decisions: int = 0
        self._lock = threading.Lock()
        self._load_model()

    # ── Model lifecycle ───────────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Load the PPO model. Fails gracefully if not found."""
        if not os.path.exists(self.MODEL_PATH):
            logger.warning(
                "RL model not found at %s — falling back to heuristic. "
                "Run: python src/rl/train_rl_model.py",
                self.MODEL_PATH,
            )
            self._model_loaded = False
            return

        try:
            from stable_baselines3 import PPO  # lazy import — optional dependency
            with self._lock:
                self._model = PPO.load(self.MODEL_PATH)
                self._model_loaded = True
            logger.info("RL model loaded from %s", self.MODEL_PATH)
        except Exception as exc:
            logger.warning("Failed to load RL model: %s", exc)
            self._model_loaded = False

    def reload_model(self) -> bool:
        """Hot-reload model from disk. Returns True on success."""
        try:
            from stable_baselines3 import PPO
            model = PPO.load(self.MODEL_PATH)
            with self._lock:
                self._model = model
                self._model_loaded = True
            logger.info("RL model hot-reloaded successfully.")
            return True
        except Exception as exc:
            logger.warning("Model reload failed: %s", exc)
            return False

    # ── Inference ─────────────────────────────────────────────────────────────

    def predict(self, state: TrafficState) -> SignalDecision:
        """Convert TrafficState → observation → action → SignalDecision."""
        obs = self._state_to_obs(state)

        if not self._model_loaded or self._model is None:
            return self._fallback_decision(state)

        try:
            with self._lock:
                action_arr, _ = self._model.predict(obs, deterministic=True)
            action_id = int(action_arr)
        except Exception as exc:
            logger.warning("Model predict() failed: %s", exc)
            return self._fallback_decision(state)

        green_arm, phase_duration = ACTION_MAP[action_id]

        # Attempt to extract per-action Q-values for the dashboard
        q_values = self._get_q_values(obs)
        confidence = float(max(q_values)) if q_values else 0.0

        self._total_decisions += 1
        reasoning = (
            f"{green_arm} queue={getattr(state, f'{green_arm}_count')} — "
            f"action {action_id} → green for {phase_duration}s"
        )
        return SignalDecision(
            green_arm=green_arm,
            phase_duration=phase_duration,
            action_id=action_id,
            confidence=round(confidence, 4),
            all_q_values=q_values,
            fallback_used=False,
            reasoning=reasoning,
        )

    def _state_to_obs(self, state: TrafficState) -> np.ndarray:
        return np.array([
            min(state.north_count / MAX_COUNT, 1.0),
            min(state.south_count / MAX_COUNT, 1.0),
            min(state.east_count  / MAX_COUNT, 1.0),
            min(state.west_count  / MAX_COUNT, 1.0),
            min(state.north_wait  / MAX_WAIT,  1.0),
            min(state.south_wait  / MAX_WAIT,  1.0),
            min(state.east_wait   / MAX_WAIT,  1.0),
            min(state.west_wait   / MAX_WAIT,  1.0),
        ], dtype=np.float32)

    def _get_q_values(self, obs: np.ndarray) -> list[float]:
        """Extract per-action values from the policy network."""
        try:
            import torch
            with self._lock:
                policy = self._model.policy  # type: ignore[union-attr]
            obs_tensor = torch.tensor(obs[None], dtype=torch.float32)
            with torch.no_grad():
                dist = policy.get_distribution(obs_tensor)
                logits = dist.distribution.logits.squeeze(0).tolist()
            return [round(float(v), 4) for v in logits]
        except Exception:
            return [0.0] * 8

    def _fallback_decision(self, state: TrafficState) -> SignalDecision:
        """Heuristic: give green to the arm with the most vehicles."""
        counts = {
            "north": state.north_count,
            "south": state.south_count,
            "east":  state.east_count,
            "west":  state.west_count,
        }
        green_arm = max(counts, key=lambda a: counts[a])
        action_id = {"north": 1, "south": 3, "east": 5, "west": 7}[green_arm]
        self._total_decisions += 1
        return SignalDecision(
            green_arm=green_arm,
            phase_duration=20,
            action_id=action_id,
            confidence=0.0,
            all_q_values=[0.0] * 8,
            fallback_used=True,
            reasoning=f"Fallback heuristic: {green_arm} has most vehicles ({counts[green_arm]})",
        )

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        return {
            "model_loaded":     self._model_loaded,
            "total_decisions":  self._total_decisions,
            "model_path":       self.MODEL_PATH,
        }


# ── Module-level singleton ────────────────────────────────────────────────────
rl_controller = RLSignalController()

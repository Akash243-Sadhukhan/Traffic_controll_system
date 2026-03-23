# ai-services/src/rl/traffic_env.py
"""
TrafficSignalEnv — Gymnasium environment for 4-arm intersection signal control.

State space  : Box(8,)  [n_count, s_count, e_count, w_count,
                          n_wait,  s_wait,  e_wait,  w_wait]  normalised 0–1
Action space : Discrete(8)  → (arm, duration)
"""

import numpy as np
import gymnasium as gym
from gymnasium import spaces


ARM_NAMES = ["north", "south", "east", "west"]

ACTION_MAP = {
    0: ("north", 15), 1: ("north", 30),
    2: ("south", 15), 3: ("south", 30),
    4: ("east",  15), 5: ("east",  30),
    6: ("west",  15), 7: ("west",  30),
}

MAX_COUNT = 20.0   # normalisation ceiling for queue counts
MAX_WAIT  = 60.0   # normalisation ceiling for wait times (seconds)


class TrafficSignalEnv(gym.Env):
    """
    Simulates a 4-arm signalised intersection for RL training.

    The agent chooses which arm receives green and for how long.
    The reward penalises queues and rewards throughput.
    """

    metadata = {"render_modes": []}

    def __init__(self):
        super().__init__()

        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(8,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(8)

        # Internal state
        self._counts: dict[str, int]  = {a: 0 for a in ARM_NAMES}
        self._waits:  dict[str, float] = {a: 0.0 for a in ARM_NAMES}
        self._current_green: str = "north"
        self._step_count: int   = 0
        self._max_steps: int    = 500
        self._prev_action: int  = -1

    # ── Gym API ───────────────────────────────────────────────────────────────

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        for arm in ARM_NAMES:
            self._counts[arm] = int(self.np_random.integers(0, 15))
            self._waits[arm]  = float(self.np_random.integers(0, 40))
        self._step_count  = 0
        self._prev_action = -1
        return self._get_obs(), {}

    def step(self, action: int):
        arm, duration = ACTION_MAP[action]

        # Vehicles cleared on the green arm (proportional to duration)
        cleared = min(self._counts[arm], max(1, duration // 5))
        emergency_cleared = (self._counts[arm] > 10 and arm == self._current_green)

        # Apply action
        prev_counts_total = sum(self._counts.values())
        self._counts[arm] = max(0, self._counts[arm] - cleared)

        # Simulate new arrivals on all arms
        for a in ARM_NAMES:
            if a != arm:
                self._counts[a] = min(int(MAX_COUNT), self._counts[a] + int(self.np_random.integers(0, 3)))
                self._waits[a]  = min(MAX_WAIT, self._waits[a] + float(duration))
            else:
                self._waits[a] = max(0.0, self._waits[a] - float(duration))

        self._current_green = arm
        reward = self._compute_reward(cleared, action, emergency_cleared, prev_counts_total)
        self._prev_action  = action
        self._step_count  += 1

        terminated = self._step_count >= self._max_steps
        return self._get_obs(), reward, terminated, False, {}

    def render(self):
        pass  # no-op

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_obs(self) -> np.ndarray:
        obs = []
        for arm in ARM_NAMES:
            obs.append(min(self._counts[arm] / MAX_COUNT, 1.0))
        for arm in ARM_NAMES:
            obs.append(min(self._waits[arm]  / MAX_WAIT,  1.0))
        return np.array(obs, dtype=np.float32)

    def _compute_reward(
        self,
        vehicles_cleared: int,
        action: int,
        emergency_cleared: bool,
        prev_total: int,
    ) -> float:
        total_waiting = sum(self._counts.values())
        phase_change_penalty = 0.1 if (self._prev_action != -1 and action != self._prev_action) else 0.0
        emergency_bonus = 10.0 if emergency_cleared else 0.0

        reward = (
            -1.0 * total_waiting
            + 5.0 * vehicles_cleared
            - phase_change_penalty
            + emergency_bonus
        )
        return float(reward)


# ── Smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    env = TrafficSignalEnv()
    obs, _ = env.reset()
    print(f"Initial obs: {obs}")
    total_reward = 0.0
    for _ in range(20):
        action = env.action_space.sample()
        obs, reward, terminated, truncated, _ = env.step(action)
        total_reward += reward
        if terminated:
            break
    print(f"Smoke test passed. Total reward over 20 steps: {total_reward:.2f}")

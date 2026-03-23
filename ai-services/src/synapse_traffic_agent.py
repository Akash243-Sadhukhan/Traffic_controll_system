"""
synapse_traffic_agent.py
========================
AI-powered adaptive traffic signal control using:
  - SUMO-RL  : OpenAI Gym-compatible wrapper for SUMO simulations
  - Stable Baselines3 : PPO agent
  - Custom reward      : waiting-time penalty + emergency-vehicle priority + efficiency bonus

Project: Traffic Control System (Minor Project)
Author:  AI Engineer – Urban Mobility
Device:  MacBook (cpu training)
"""

import os
import sys
import traci
import numpy as np
from typing import Optional

# ── Stable Baselines3 ────────────────────────────────────────────────────────
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.callbacks import CheckpointCallback

# ── SUMO-RL ──────────────────────────────────────────────────────────────────
from sumo_rl import SumoEnvironment
from sumo_rl.environment.observations import DefaultObservationFunction

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
MODEL_SAVE_PATH   = "synapse_traffic_brain"          # SB3 appends .zip automatically
CHECKPOINT_PREFIX = "synapse_checkpoint"
LOG_DIR           = "./logs/synapse_ppo/"

# ── SUMO simulation files ─────────────────────────────────────────────────────
# Points to the real Sumo_simulation directory at the project root.
_SIM_DIR        = os.path.join(os.path.dirname(__file__), "..", "..", "Sumo_simulation")
SUMO_NET_FILE   = os.path.join(_SIM_DIR, "maps", "test.net.xml")
SUMO_ROUTE_FILE = os.path.join(_SIM_DIR, "maps", "trips.trips.xml")

# ── Priority vehicle detection ────────────────────────────────────────────────
EMERGENCY_KEYWORD       = "emergency"   # vehicle type/id substring for ambulances
PRIORITY_DETECTION_DIST = 100.0         # metres – radius around junction centre
EMERGENCY_SPEED_THRESH  = 0.1           # m/s – below this → vehicle is "stopped"
EMERGENCY_PENALTY       = 10.0          # multiplier applied to stopped-emergency penalty


# ─────────────────────────────────────────────────────────────────────────────
# HELPER – retrieve junction position (cached after first call)
# ─────────────────────────────────────────────────────────────────────────────
_junction_pos_cache: dict[str, tuple[float, float]] = {}

def _get_junction_pos(ts_id: str) -> tuple[float, float]:
    """Return (x, y) world coordinates of a traffic-signal junction."""
    if ts_id not in _junction_pos_cache:
        _junction_pos_cache[ts_id] = traci.junction.getPosition(ts_id)
    return _junction_pos_cache[ts_id]


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM REWARD FUNCTION
# sumo-rl passes the TrafficSignal object to reward_fn; we compute globally.
# ─────────────────────────────────────────────────────────────────────────────
_prev_arrived: set[str] = set()   # module-level state used by the reward fn

def custom_reward_fn(traffic_signal) -> float:  # noqa: ANN001
    """
    Custom reward callable compatible with sumo-rl's reward_fn interface.

    Args:
        traffic_signal: The sumo_rl TrafficSignal object for this junction.

    Returns:
        float – scalar reward for this step.
    """
    global _prev_arrived

    total_wait  = 0.0
    emg_penalty = 0.0

    for vid in traci.vehicle.getIDList():
        wait  = float(traci.vehicle.getWaitingTime(vid))
        total_wait += wait

        vtype = traci.vehicle.getTypeID(vid).lower()
        if EMERGENCY_KEYWORD in vtype or EMERGENCY_KEYWORD in vid.lower():
            speed = float(traci.vehicle.getSpeed(vid))
            if speed < EMERGENCY_SPEED_THRESH:
                emg_penalty += EMERGENCY_PENALTY * wait

    # Efficiency bonus – vehicles that exited during this step
    arrived_now  = set(traci.simulation.getArrivedIDList())
    new_arrivals = arrived_now - _prev_arrived
    efficiency   = 0.5 * len(new_arrivals)
    _prev_arrived = arrived_now

    return -total_wait - emg_penalty + efficiency


# ─────────────────────────────────────────────────────────────────────────────
# PRIORITY SUMO ENVIRONMENT
# ─────────────────────────────────────────────────────────────────────────────
class PrioritySumoEnv(SumoEnvironment):
    """
    Extends SumoEnvironment with:

    1. Custom reward function
       - Base     : –(total waiting time across all vehicles)
       - Penalty  : –EMERGENCY_PENALTY * waiting_time for each stopped emergency vehicle
       - Bonus    : +0.5 for each vehicle that exited the simulation this step

    2. Extended observation (state) space
       - All original SumoEnvironment features
       - Vehicle density per incoming lane
       - Current traffic-light phase index (normalised)
       - Boolean flag : any priority vehicle within PRIORITY_DETECTION_DIST metres
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._prev_departed: set[str] = set()   # track already-seen vehicles
        self._arrived_count: int      = 0        # cumulative exits

    # ── Observation ───────────────────────────────────────────────────────────
    def _get_obs(self) -> dict:
        """
        Build an extended observation dictionary for each traffic-signal agent.

        Returns the parent observation augmented with:
          - 'lane_density'         : np.ndarray – normalised vehicle count per lane
          - 'phase_index'          : float       – current phase / total phases
          - 'priority_vehicle_near': float       – 1.0 if emergency nearby, else 0.0
        """
        base_obs = super()._get_obs()

        for ts_id, ts in self.traffic_signals.items():
            # ── Lane density ─────────────────────────────────────────────────
            lanes      = traci.trafficlight.getControlledLanes(ts_id)
            densities  = []
            for lane in set(lanes):            # unique lanes
                n_veh  = traci.lane.getLastStepVehicleNumber(lane)
                length = max(traci.lane.getLength(lane), 1.0)
                densities.append(n_veh / length)
            lane_density = np.array(densities, dtype=np.float32)

            # ── Phase index ──────────────────────────────────────────────────
            total_phases = len(ts.all_phases)
            phase_norm   = ts.green_phase / max(total_phases, 1)

            # ── Priority vehicle proximity flag ──────────────────────────────
            jx, jy         = _get_junction_pos(ts_id)
            priority_nearby = 0.0
            for vid in traci.vehicle.getIDList():
                vtype = traci.vehicle.getTypeID(vid).lower()
                if EMERGENCY_KEYWORD in vtype or EMERGENCY_KEYWORD in vid.lower():
                    vx, vy = traci.vehicle.getPosition(vid)
                    dist   = ((vx - jx) ** 2 + (vy - jy) ** 2) ** 0.5
                    if dist <= PRIORITY_DETECTION_DIST:
                        priority_nearby = 1.0
                        break

            # Augment the observation for this traffic-signal agent
            if isinstance(base_obs, dict):
                base_obs[ts_id] = {
                    "base"                 : base_obs.get(ts_id, np.array([])),
                    "lane_density"         : lane_density,
                    "phase_index"          : np.float32(phase_norm),
                    "priority_vehicle_near": np.float32(priority_nearby),
                }

        return base_obs


# ─────────────────────────────────────────────────────────────────────────────
# FACTORY – build the Gym environment
# ─────────────────────────────────────────────────────────────────────────────
def make_priority_env(use_gui: bool = False) -> PrioritySumoEnv:
    """
    Instantiate and return a PrioritySumoEnv.

    Args:
        use_gui: If True, launches SUMO with a graphical window (for demo).
    """
    env = PrioritySumoEnv(
        net_file          = SUMO_NET_FILE,
        route_file        = SUMO_ROUTE_FILE,
        use_gui           = use_gui,
        num_seconds       = 3600,                     # simulated seconds per episode
        delta_time        = 5,                        # seconds per RL step
        yellow_time       = 2,
        min_green         = 5,
        max_green         = 60,
        reward_fn         = custom_reward_fn,         # our callable – correct sumo-rl API
        observation_class = DefaultObservationFunction,  # class object, not a string
        sumo_seed         = "random",
        single_agent      = True,
    )
    return env


# ─────────────────────────────────────────────────────────────────────────────
# TRAINING
# ─────────────────────────────────────────────────────────────────────────────
def train_agent(total_timesteps: int = 200_000):
    """
    Train a PPO agent on the PrioritySumoEnv.

    Hyper-parameters are tuned for a MacBook (CPU training):
      - n_steps    : 1024  – rollout buffer size
      - batch_size : 64    – mini-batch for gradient updates
      - device     : 'cpu' – no GPU required
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    print("=" * 60)
    print("  SYNAPSE TRAFFIC BRAIN – PPO Training")
    print("=" * 60)
    print(f"  Net file   : {SUMO_NET_FILE}")
    print(f"  Route file : {SUMO_ROUTE_FILE}")
    print(f"  Timesteps  : {total_timesteps:,}")
    print(f"  Log dir    : {LOG_DIR}")
    print("=" * 60)

    # Single vectorised environment (CPU-friendly)
    env = make_vec_env(lambda: make_priority_env(use_gui=False), n_envs=1)

    # Periodic checkpoint every 50 000 steps
    checkpoint_cb = CheckpointCallback(
        save_freq   = 50_000,
        save_path   = LOG_DIR,
        name_prefix = CHECKPOINT_PREFIX,
        verbose     = 1,
    )

    # PPO – MacBook-optimised hyper-parameters
    model = PPO(
        policy          = "MlpPolicy",
        env             = env,
        n_steps         = 1024,          # steps collected before update
        batch_size      = 64,            # mini-batch size
        n_epochs        = 10,            # optimisation epochs per update
        gamma           = 0.99,
        gae_lambda      = 0.95,
        clip_range      = 0.2,
        ent_coef        = 0.01,          # encourage exploration
        learning_rate   = 3e-4,
        verbose         = 1,
        tensorboard_log = LOG_DIR,
        device          = "cpu",         # MacBook – no CUDA
    )

    print("\n[INFO] Starting training …\n")
    model.learn(
        total_timesteps = total_timesteps,
        callback        = checkpoint_cb,
        progress_bar    = True,
    )

    save_model(model)
    env.close()
    return model


# ─────────────────────────────────────────────────────────────────────────────
# SAVE
# ─────────────────────────────────────────────────────────────────────────────
def save_model(model: PPO, path: str = MODEL_SAVE_PATH) -> str:
    """
    Save the trained PPO model to <path>.zip.

    Returns the full path to the saved file.
    """
    model.save(path)
    full_path = os.path.abspath(f"{path}.zip")
    print(f"\n✅  Model saved → {full_path}\n")
    return full_path


# ─────────────────────────────────────────────────────────────────────────────
# DEMO – run trained model in sumo-gui
# ─────────────────────────────────────────────────────────────────────────────
def run_demo(
    model_path : str = f"{MODEL_SAVE_PATH}.zip",
    n_episodes : int = 3,
    max_steps  : int = 720,                     # steps per episode (≈ 1 hour)
):
    """
    Load a saved PPO model and run it in SUMO-GUI for visual demonstration.

    Args:
        model_path : Path to the .zip model file.
        n_episodes : Number of demo episodes to run.
        max_steps  : Maximum RL steps per episode.
    """
    print("\n" + "=" * 60)
    print("  SYNAPSE TRAFFIC BRAIN – DEMO (sumo-gui)")
    print("=" * 60)
    print(f"  Model      : {model_path}")
    print(f"  Episodes   : {n_episodes}")
    print(f"  Max steps  : {max_steps}")
    print("=" * 60 + "\n")

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"Model file not found: {model_path}\n"
            "Run train_agent() first to create it."
        )

    model = PPO.load(model_path, device="cpu")

    for episode in range(1, n_episodes + 1):
        env         = make_priority_env(use_gui=True)
        obs, _info  = env.reset()
        done        = False
        total_reward = 0.0
        step         = 0

        print(f"── Episode {episode}/{n_episodes} started ──────────────────────")

        while not done and step < max_steps:
            action, _states = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            done          = terminated or truncated
            total_reward += reward
            step         += 1

        env.close()
        print(
            f"── Episode {episode} finished │ "
            f"steps={step} │ total_reward={total_reward:.2f} ──"
        )

    print("\n✅  Demo complete.\n")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Synapse Traffic Brain – PPO-based adaptive signal controller"
    )
    parser.add_argument(
        "--mode",
        choices=["train", "demo", "train-demo"],
        default="train",
        help=(
            "train       → train the PPO agent and save model\n"
            "demo        → load saved model and run in sumo-gui\n"
            "train-demo  → train then immediately run demo"
        ),
    )
    parser.add_argument(
        "--timesteps",
        type=int,
        default=200_000,
        help="Total training timesteps (default: 200 000)",
    )
    parser.add_argument(
        "--episodes",
        type=int,
        default=3,
        help="Number of demo episodes (default: 3)",
    )
    args = parser.parse_args()

    if args.mode in ("train", "train-demo"):
        trained_model = train_agent(total_timesteps=args.timesteps)

    if args.mode in ("demo", "train-demo"):
        run_demo(n_episodes=args.episodes)

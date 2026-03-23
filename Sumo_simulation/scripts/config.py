# Sumo_simulation/scripts/config.py
"""
config.py — Shared configuration and mutable simulation state.
Import CFG and STATE from any script in this package.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))          # .../Sumo_simulation/scripts/
GEN_DIR  = os.path.join(BASE_DIR, "generated")                 # all generated XML files land here

NET_FILE = os.path.join(GEN_DIR, "intersection.net.xml")
ROU_FILE = os.path.join(GEN_DIR, "routes.rou.xml")
CFG_FILE = os.path.join(GEN_DIR, "sim.sumocfg")
LOG_FILE = os.path.join(BASE_DIR, "detections.log")


# ─────────────────────────────────────────────────────────────────────────────
# SIMULATION CONFIGURATION  (read-only after startup)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class SimConfig:
    # Network
    street_length: float = 300.0
    num_lanes: int        = 2
    speed_limit: float    = 13.89         # m/s  ≈ 50 km/h

    # Traffic-light timing
    fixed_green: int       = 30           # seconds
    fixed_yellow: int      = 5
    min_green: int         = 10
    max_green: int         = 60
    adaptive_ext_step: int = 2            # seconds added per vehicle in queue
    adaptive_check_every: int = 10        # check interval (steps)
    adaptive_start_time: int  = 30        # sim-time after which adaptive kicks in

    # Spawning
    default_spawn_rate: int = 20          # vehicles / minute
    min_spawn_rate: int     = 5
    max_spawn_rate: int     = 60
    vtype_dist: Dict[str, float] = field(
        default_factory=lambda: {
            "passenger":  0.75,
            "bus":        0.10,
            "motorcycle": 0.15,
        }
    )

    # TraCI / SUMO
    traci_port: int    = 8813
    step_length: float = 1.0             # seconds per simulation step

    # ANPR
    detection_speed_threshold: float = 0.5   # m/s — below this ≈ stopped
    flagged_plate: str = "WB06XX9999"

    # Dashboard
    refresh_rate: int = 4                # Rich live refresh per second

    # --- Pipeline integration (NEW) ---
    ai_service_url: str   = "http://localhost:8001"
    backend_url: str      = "http://localhost:8080"
    publish_interval: int = 10            # simulation steps between publishes
    command_poll_interval: int = 5        # steps between backend command polls


# ─────────────────────────────────────────────────────────────────────────────
# SIMULATION STATE  (mutable, shared across modules)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class SimState:
    # Runtime control
    spawn_rate: int  = 20
    mode: str        = "FIXED"           # "FIXED" | "ADAPTIVE"
    running: bool    = True
    sim_time: int    = 0

    # Vehicle tracking
    active_vehicles: int = 0
    total_plates: int    = 0
    plate_map: Dict[str, str] = field(default_factory=dict)      # veh_id → plate
    recent_detections: List[Dict] = field(default_factory=list)  # last 5 ANPR hits

    # Per-arm queue lengths
    queues: Dict[str, int] = field(
        default_factory=lambda: {"north": 0, "south": 0, "east": 0, "west": 0}
    )

    # Hotkey triggers
    trigger_emergency: bool = False
    trigger_flagged:   bool = False
    trigger_reset:     bool = False

    # Dashboard alert
    alert_msg:     str = ""
    alert_expires: int = 0

    # Metrics for final report
    total_wait_fixed:    float = 0.0
    total_wait_adaptive: float = 0.0
    steps_fixed:    int = 0
    steps_adaptive: int = 0

    # --- Pipeline integration (NEW) ---
    last_backend_response: dict = field(default_factory=dict)
    last_publish_time: int = 0

    # --- RL mode (NEW) ---
    last_rl_decision: dict = field(default_factory=dict)
    rl_mode_start_time: int = 60     # simulation time when RL mode activates
    arm_to_phase: dict = field(default_factory=lambda: {
        "north": 0, "south": 2, "east": 4, "west": 6
    })


# ─────────────────────────────────────────────────────────────────────────────
# SINGLETONS — import these everywhere
# ─────────────────────────────────────────────────────────────────────────────
CFG   = SimConfig()
STATE = SimState(spawn_rate=SimConfig().default_spawn_rate)

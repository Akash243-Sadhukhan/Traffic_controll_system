"""
config.py — Centralized configuration for the AI Traffic Management System.

All settings are overridable via environment variables.
"""

import os
import sys
from dataclasses import dataclass, field
from typing import Dict, Optional


def _detect_device() -> str:
    """Auto-detect best available compute device."""
    override = os.getenv("AI_DEVICE", "").lower()
    try:
        import torch
    except ImportError:
        return "cpu"

    if override:
        if override == "cuda" and torch.cuda.is_available():
            return "cuda"
        if override == "mps" and getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        if override == "cpu":
            return "cpu"

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "traffic.db")
MODELS_DIR = os.path.join(BASE_DIR, "models")


@dataclass(frozen=True)
class AppConfig:
    """Immutable application configuration."""

    # ── Server ────────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = int(os.getenv("PORT", "8001"))
    debug: bool = os.getenv("DEBUG", "0") == "1"

    # ── AI / Detection ────────────────────────────────────────────────────────
    device: str = field(default_factory=_detect_device)
    vehicle_model: str = os.getenv("VEHICLE_MODEL", os.path.join(MODELS_DIR, "best.pt"))
    plate_model: str = os.getenv("PLATE_MODEL", os.path.join(MODELS_DIR, "best.pt"))
    detection_confidence: float = float(os.getenv("DETECTION_CONF", "0.5"))
    plate_confidence: float = float(os.getenv("PLATE_CONF", "0.3"))

    # ── RL / Signal Generator ─────────────────────────────────────────────────
    rl_policy_model: str = os.path.join(MODELS_DIR, "policy.pth")
    rl_variables_path: str = os.path.join(MODELS_DIR, "pytorch_variables.pth")
    rl_input_dim: int = 19
    rl_output_dim: int = 2

    # ── RL / Signal Generator ─────────────────────────────────────────────────
    rl_policy_model: str = os.path.join(MODELS_DIR, "policy.pth")
    rl_variables_path: str = os.path.join(MODELS_DIR, "pytorch_variables.pth")

    # ── Signal Control ────────────────────────────────────────────────────────
    default_green_time: int = int(os.getenv("DEFAULT_GREEN", "30"))
    min_green_time: int = int(os.getenv("MIN_GREEN", "10"))
    max_green_time: int = int(os.getenv("MAX_GREEN", "60"))
    yellow_time: int = int(os.getenv("YELLOW_TIME", "5"))
    adaptive_ext_step: int = int(os.getenv("ADAPTIVE_EXT_STEP", "2"))

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
    history_retention_hours: int = int(os.getenv("HISTORY_RETENTION_HOURS", "72"))

    # ── Display ───────────────────────────────────────────────────────────────
    show_opencv_window: bool = os.getenv("SHOW_WINDOW", "0" if sys.platform == "darwin" else "1") not in ("0", "false", "no")
    window_name: str = os.getenv("WINDOW_NAME", "🚦 Traffic AI — Live Feed")

    # ── External Services ─────────────────────────────────────────────────────
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    mqtt_broker: str = os.getenv("MQTT_BROKER", "")  # empty = use in-process pub/sub
    mqtt_port: int = int(os.getenv("MQTT_PORT", "1883"))

    # ── Intersection Lanes (default 4-way) ────────────────────────────────────
    lane_names: tuple = ("north", "south", "east", "west")


# Singleton
settings = AppConfig()

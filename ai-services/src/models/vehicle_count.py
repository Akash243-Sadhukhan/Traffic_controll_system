# ai-services/src/models/vehicle_count.py
"""
vehicle_count.py — Pydantic v2 models for the SUMO → ai-services pipeline.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel


# ─────────────────────────────────────────────────────────────────────────────
# Inbound — posted by Sumo_simulation/scripts/publisher.py
# ─────────────────────────────────────────────────────────────────────────────
class VehicleCountPayload(BaseModel):
    """Raw vehicle-count data arriving from the SUMO simulation."""

    timestamp:       int
    intersection_id: str
    arm_counts:      Dict[str, int]   # e.g. {"north": 3, "south": 1, ...}
    total_vehicles:  int
    mode:            str              # "FIXED" | "ADAPTIVE"
    source:          str              # always "sumo_simulation"


# ─────────────────────────────────────────────────────────────────────────────
# Internal — per-arm analysis produced by vehicle_count_routes.py
# ─────────────────────────────────────────────────────────────────────────────
class ArmCongestion(BaseModel):
    """Analysis result for a single intersection arm."""

    arm:                        str
    count:                      int
    congestion_level:           Literal["LOW", "MEDIUM", "HIGH"]
    recommended_green_extension: int   # seconds, clamped 0–15


# ─────────────────────────────────────────────────────────────────────────────
# Outbound — returned to the publisher and rendered on the dashboard
# ─────────────────────────────────────────────────────────────────────────────
class ProcessedCountResponse(BaseModel):
    """Full analysis response sent back to the SUMO simulation publisher."""

    intersection_id:      str
    timestamp:            int
    arm_analysis:         List[ArmCongestion]
    most_congested_arm:   str
    total_vehicles:       int
    backend_notified:     bool
    backend_status_code:  Optional[int] = None

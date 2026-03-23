# ai-services/src/vehicle_count_routes.py
"""
vehicle_count_routes.py — FastAPI router for the SUMO vehicle-count pipeline.

Registration (add these two lines to ai-services/src/main.py):
    from vehicle_count_routes import router as vc_router
    app.include_router(vc_router)
"""

from __future__ import annotations

import logging
from typing import List

import httpx
from fastapi import APIRouter

from models.vehicle_count import (
    ArmCongestion,
    ProcessedCountResponse,
    VehicleCountPayload,
)
import state_store  # shared live state


logger = logging.getLogger("traffic.vehicle_count_routes")

router = APIRouter(prefix="/ai", tags=["vehicle-counts"])

import os
_BACKEND_BASE_URL  = os.getenv("BACKEND_URL", "http://localhost:8080").rstrip("/")
_BACKEND_URL       = f"{_BACKEND_BASE_URL}/api/detections/vehicle-count"
_BACKEND_TIMEOUT   = 5.0   # seconds


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _congestion_level(count: int) -> str:
    if count <= 3:
        return "LOW"
    if count <= 7:
        return "MEDIUM"
    return "HIGH"


def _green_extension(count: int) -> int:
    return min(count * 2, 15)


def _analyse_arms(arm_counts: dict) -> List[ArmCongestion]:
    return [
        ArmCongestion(
            arm=arm,
            count=count,
            congestion_level=_congestion_level(count),
            recommended_green_extension=_green_extension(count),
        )
        for arm, count in arm_counts.items()
    ]


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/vehicle-counts", response_model=ProcessedCountResponse)
async def process_vehicle_counts(payload: VehicleCountPayload) -> ProcessedCountResponse:
    """
    Receive raw vehicle counts from the SUMO simulation, compute per-arm
    congestion levels, forward the event to Spring Boot, and return the
    full analysis to the publisher dashboard.
    """
    # 1. Analyse each arm
    arm_analysis = _analyse_arms(payload.arm_counts)

    # 2. Most congested arm
    most_congested_arm = (
        max(payload.arm_counts, key=payload.arm_counts.get)
        if payload.arm_counts
        else "unknown"
    )
    most_congested_analysis = next(
        (a for a in arm_analysis if a.arm == most_congested_arm), None
    )

    # 2b. Mirror into shared live state so the dashboard updates instantly
    state_store.state.update_arm_counts(
        arm_counts=payload.arm_counts,
        total=payload.total_vehicles,
    )

    # 3. Forward to Spring Boot backend (best-effort, never crash on failure)
    backend_notified     = False
    backend_status_code: int | None = None

    detection_event = {
        "intersectionId":     payload.intersection_id,
        "timestamp":          payload.timestamp,
        "armCounts":          payload.arm_counts,
        "totalVehicles":      payload.total_vehicles,
        "mostCongestedArm":   most_congested_arm,
        "mode":               payload.mode,
        "source":             payload.source,
    }

    try:
        async with httpx.AsyncClient(timeout=_BACKEND_TIMEOUT) as client:
            print("\n" + "="*50)
            print(f"🚀 AI-SERVICES: Sending Vehicle Count to Backend")
            print(f"   Intersection : {payload.intersection_id}")
            print(f"   Timestamp    : {payload.timestamp}")
            print(f"   Total Count  : {payload.total_vehicles}")
            print(f"   Payload      : {detection_event}")
            print("="*50 + "\n")
            
            resp = await client.post(_BACKEND_URL, json=detection_event)
            backend_status_code = resp.status_code
            if resp.is_success:
                backend_notified = True
                print(f"✅ Backend notified OK (HTTP {resp.status_code}) for t={payload.timestamp}")
                logger.debug("Backend notified OK (%d) for t=%d", resp.status_code, payload.timestamp)
            else:
                print(f"⚠️ Backend returned HTTP {resp.status_code} for t={payload.timestamp}")
                logger.warning("Backend returned HTTP %d for t=%d", resp.status_code, payload.timestamp)
    except Exception as exc:
        logger.warning("Could not reach backend: %s", exc)

    return ProcessedCountResponse(
        intersection_id=payload.intersection_id,
        timestamp=payload.timestamp,
        arm_analysis=arm_analysis,
        most_congested_arm=most_congested_arm,
        total_vehicles=payload.total_vehicles,
        backend_notified=backend_notified,
        backend_status_code=backend_status_code,
    )


@router.get("/vehicle-counts/health")
async def health() -> dict:
    """Liveness probe for the vehicle-count sub-service."""
    return {"status": "ok", "service": "vehicle-count-processor"}

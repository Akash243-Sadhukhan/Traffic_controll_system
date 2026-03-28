"""
routes.py — FastAPI REST API endpoints for the traffic management system.
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.websocket_manager import ws_manager

logger = logging.getLogger("traffic.routes")

router = APIRouter()


# ── Request/Response Models ───────────────────────────────────────────────────

class StartDetectionRequest(BaseModel):
    source: str = "0"  # "0" for webcam, path for video, URL for RTSP
    target_fps: float = 30.0


class VehicleCountPayload(BaseModel):
    timestamp: int = 0
    intersection_id: str = "MAIN_JUNCTION"
    arm_counts: Dict[str, int] = {}
    total_vehicles: int = 0
    mode: str = "ADAPTIVE"
    source: str = "simulation"


class SignalOverrideRequest(BaseModel):
    lane: str
    reason: str = "manual_override"
    vehicle_type: str = "manual"


class HistoryQueryParams(BaseModel):
    event_type: Optional[str] = None
    lane: Optional[str] = None
    limit: int = 50


class RLObservation(BaseModel):
    intersection_id: str
    timestamp: float
    north_count: int
    south_count: int
    east_count: int
    west_count: int
    north_wait: float
    south_wait: float
    east_wait: float
    west_wait: float
    mode: str = "RL"
    source: str = "simulation"


# ── Health & Status ───────────────────────────────────────────────────────────

@router.get("/", tags=["health"])
async def root():
    return {
        "service": "🚦 AI Traffic Management System",
        "status": "online",
        "version": "1.0.0",
        "timestamp": time.time(),
    }


@router.get("/health", tags=["health"])
async def health_check():
    return {"status": "healthy", "uptime": time.time()}


# ── Traffic Stats ─────────────────────────────────────────────────────────────

@router.get("/stats", tags=["stats"])
async def get_stats():
    """Get current traffic snapshot."""
    # Will be populated by the traffic engine
    from main import traffic_engine
    return traffic_engine.get_snapshot()


@router.get("/stats/stream", tags=["stats"])
async def stats_stream(request: Request):
    """Server-Sent Events stream of live traffic stats."""
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            from main import traffic_engine
            data = json.dumps(traffic_engine.get_snapshot())
            yield f"data: {data}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Detection Control ────────────────────────────────────────────────────────

@router.post("/detection/start", tags=["detection"])
async def start_detection(req: StartDetectionRequest):
    """Start the detection loop."""
    from main import traffic_engine
    traffic_engine.start_detection(source=req.source, target_fps=req.target_fps)
    return {
        "status": "detection_started",
        "source": req.source,
        "target_fps": req.target_fps,
    }


@router.post("/detection/stop", tags=["detection"])
async def stop_detection():
    """Stop the detection loop."""
    from main import traffic_engine
    traffic_engine.stop_detection()
    return {"status": "detection_stopped"}


@router.get("/detection/status", tags=["detection"])
async def detection_status():
    """Get detection loop status."""
    from main import traffic_engine
    return traffic_engine.get_detection_status()


@router.get("/video_feed", tags=["detection"])
async def video_feed(request: Request):
    """Serve live MJPEG stream of an annotated video feed."""
    from main import traffic_engine

    async def gen():
        while True:
            if await request.is_disconnected():
                break
            
            frame_bytes = traffic_engine.display.get_latest_frame()
            if frame_bytes:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )
            else:
                # If no frame yet, yield a blank or sleep
                await asyncio.sleep(0.05)
                continue
            
            # Throttle stream to ~20FPS logic
            await asyncio.sleep(0.05)

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


# ── Signal Control ────────────────────────────────────────────────────────────

@router.get("/signal/status", tags=["signals"])
async def signal_status():
    """Get current signal state for all lanes."""
    from main import traffic_engine
    return traffic_engine.get_signal_state()


@router.post("/signal/override", tags=["signals"])
async def signal_override(req: SignalOverrideRequest):
    """Manually override a signal (force green on a lane)."""
    from main import traffic_engine
    result = traffic_engine.trigger_override(
        lane=req.lane,
        reason=req.reason,
        vehicle_type=req.vehicle_type,
    )
    return result


@router.post("/vehicle-counts", tags=["counts"])
async def receive_vehicle_counts(payload: VehicleCountPayload):
    """Receive vehicle counts from SUMO simulation or external sensors."""
    from main import traffic_engine
    result = traffic_engine.process_external_counts(
        arm_counts=payload.arm_counts,
        total=payload.total_vehicles,
        mode=payload.mode,
        source=payload.source,
    )

    # Broadcast via WebSocket
    await ws_manager.broadcast_stats(result)

    return result


@router.post("/ai/rl/predict", tags=["rl"])
async def predict_rl_action(observation: RLObservation):
    """Predict next signal action using the PyTorch DQN model."""
    from main import traffic_engine
    
    # 1. Map observation to list (Standardize 19 features)
    # The simulation currently sends 8 features, we map them to 19 
    # using the engine's mapper if needed, OR we trust the payload if it's 19.
    
    obs_8 = [
        float(observation.north_count), float(observation.south_count),
        float(observation.east_count), float(observation.west_count),
        float(observation.north_wait), float(observation.south_wait),
        float(observation.east_wait), float(observation.west_wait)
    ]
    
    # 2. Get action from model (0: Stay, 1: Switch)
    action = traffic_engine.predict_rl_action(obs_8)
    
    # 3. Apply the decision to the engine
    result = traffic_engine.apply_rl_decision(action)
    
    return {
        "status": "success",
        "action": action,
        "action_name": "SWITCH" if action == 1 else "STAY",
        "timestamp": observation.timestamp,
        "engine_result": result
    }


# ── History & Audit ───────────────────────────────────────────────────────────

@router.get("/history", tags=["history"])
async def get_history(
    event_type: Optional[str] = None,
    lane: Optional[str] = None,
    limit: int = 50,
):
    """Query the audit trail."""
    from main import traffic_engine
    return traffic_engine.get_history(
        event_type=event_type,
        lane=lane,
        limit=limit,
    )


@router.get("/history/phases", tags=["history"])
async def get_phase_history(limit: int = 100):
    """Get signal phase change history."""
    from main import traffic_engine
    return traffic_engine.get_phase_history(limit=limit)


@router.get("/history/alerts", tags=["history"])
async def get_alert_history(limit: int = 50):
    """Get alert history."""
    from main import traffic_engine
    return traffic_engine.get_alert_history(limit=limit)


# ── Density Analysis ──────────────────────────────────────────────────────────

@router.get("/density", tags=["density"])
async def get_density():
    """Get current density analysis for all lanes."""
    from main import traffic_engine
    return traffic_engine.get_density_analysis()


# ── WebSocket ─────────────────────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    client_id = await ws_manager.connect(websocket)
    try:
        await ws_manager.receive_and_process(client_id)
    except WebSocketDisconnect:
        await ws_manager.disconnect(client_id)

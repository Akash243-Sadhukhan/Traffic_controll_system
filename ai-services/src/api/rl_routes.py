# ai-services/src/api/rl_routes.py
"""
FastAPI router for RL signal controller — prefix /ai/rl
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter

from models.rl_models import TrafficStateRequest, SignalDecisionResponse
from rl.rl_inference import rl_controller, TrafficState

logger = logging.getLogger("traffic.rl_routes")

router = APIRouter(prefix="/ai/rl", tags=["rl-signal"])

_BACKEND_URL = "http://localhost:8080/api/signal-decisions"
_HTTP_TIMEOUT = 3.0


async def _post_decision_to_backend(payload: dict[str, Any]) -> None:
    """Fire-and-forget: forward the RL decision to Spring Boot for persistence."""
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(_BACKEND_URL, json=payload)
            if not resp.is_success:
                logger.warning("Backend returned HTTP %d for signal decision", resp.status_code)
    except Exception as exc:
        logger.warning("Could not forward signal decision to backend: %s", exc)


@router.post("/predict", response_model=SignalDecisionResponse)
async def predict_signal(request: TrafficStateRequest) -> SignalDecisionResponse:
    """
    Main RL inference endpoint.
    Converts the request to a TrafficState, calls the RL model,
    forwards the decision to Spring Boot (async), returns immediately.
    """
    state = TrafficState(
        north_count=request.north_count,
        south_count=request.south_count,
        east_count=request.east_count,
        west_count=request.west_count,
        north_wait=request.north_wait,
        south_wait=request.south_wait,
        east_wait=request.east_wait,
        west_wait=request.west_wait,
    )

    decision = rl_controller.predict(state)

    response = SignalDecisionResponse(
        intersection_id=request.intersection_id,
        timestamp=request.timestamp,
        green_arm=decision.green_arm,
        phase_duration=decision.phase_duration,
        action_id=decision.action_id,
        confidence=decision.confidence,
        all_q_values=decision.all_q_values,
        fallback_used=decision.fallback_used,
        reasoning=decision.reasoning,
    )

    # Forward to backend in background — never wait for it
    asyncio.create_task(
        _post_decision_to_backend(response.model_dump())
    )

    return response


@router.get("/status")
async def rl_status() -> dict:
    """Returns model stats + current server timestamp."""
    stats = rl_controller.get_stats()
    stats["server_time"] = datetime.now().isoformat()
    return stats


@router.post("/reload-model")
async def reload_model() -> dict:
    """Hot-reload the PPO model from disk without restarting the service."""
    success = rl_controller.reload_model()
    return {
        "success": success,
        "message": "Model reloaded successfully." if success else "Reload failed — check logs.",
        "model_loaded": rl_controller._model_loaded,
    }


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "model_loaded": rl_controller._model_loaded}

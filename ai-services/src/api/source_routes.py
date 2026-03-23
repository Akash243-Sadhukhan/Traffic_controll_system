# ai-services/src/api/source_routes.py
"""
FastAPI router for AI input source management — prefix /ai/source

Note: stream_state and current_input_config are imported from main at
request time (not at import time) to avoid a circular-import cycle.
"""

from __future__ import annotations

import os
import logging
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("traffic.source_routes")
router = APIRouter(prefix="/ai/source", tags=["input-source"])

# Resolve Data directory relative to ai-services root
_HERE     = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR  = os.path.dirname(_HERE)
_BASE_DIR = os.path.dirname(_SRC_DIR)
_DATA_DIR = os.path.join(_BASE_DIR, "Data")

_VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov")

# ── Injected singleton (set by main.py at startup) ───────────────────────────
_input_selector = None


def set_input_selector(selector) -> None:
    """Called by main.py to inject the live singleton after creation."""
    global _input_selector
    _input_selector = selector


class SwitchSourceRequest(BaseModel):
    source:       Literal["simulation", "camera", "video"]
    camera_index: Optional[int] = 0
    video_path:   Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
async def get_status() -> dict:
    """
    Returns the current input source configuration plus live stream state.
    Reads stream_state from main at request time to avoid circular imports.
    """
    try:
        import main as _main
        cfg          = _main.current_input_config
        ss           = _main.stream_state
        source_val   = cfg.source.value
        cam_idx      = cfg.camera_index if source_val == "camera" else None
        vid_path     = cfg.video_path   if source_val == "video"  else None
        running      = ss["running"]
        frame_count  = ss["frame_count"]
    except Exception:
        # Fallback if main hasn't fully initialised yet
        source_val  = _input_selector.get_source_info().get("source", "unknown") if _input_selector else "unknown"
        cam_idx     = None
        vid_path    = None
        running     = False
        frame_count = 0

    return {
        "source":       source_val,
        "camera_index": cam_idx,
        "video_path":   vid_path,
        "active":       running,
        "frame_count":  frame_count,
    }


@router.post("/switch")
async def switch_source(request: SwitchSourceRequest) -> dict:
    """
    Switch the active input source.
    Also updates current_input_config in main so /status reflects it immediately.
    Note: does NOT restart a running detection thread — use /start-stream for that.
    """
    if _input_selector is None:
        raise HTTPException(status_code=503, detail="Input selector not initialised")

    import main as _main
    from input_selector import InputConfig, InputSource

    if request.source == "camera":
        idx = request.camera_index or 0
        if idx not in range(0, 4):
            raise HTTPException(
                status_code=422,
                detail=f"camera_index must be 0–3, got {idx}",
            )
        new_cfg = InputConfig(source=InputSource.CAMERA, camera_index=idx)
        message = f"Config updated to camera {idx} — use /start-stream to begin capture"

    elif request.source == "video":
        path = (request.video_path or "").strip()
        if not path:
            raise HTTPException(status_code=422, detail="video_path is required for video mode")
        if not path.lower().endswith(_VIDEO_EXTENSIONS):
            raise HTTPException(
                status_code=422,
                detail=f"video_path must end in {_VIDEO_EXTENSIONS}",
            )
        new_cfg = InputConfig(source=InputSource.VIDEO, video_path=path)
        message = f"Config updated to video: {path} — use /start-stream to begin"

    else:  # simulation
        new_cfg = InputConfig(source=InputSource.SIMULATION)
        message = "Config updated to SIMULATION mode — receiving SUMO webhook data"

    # Update both the selector singleton and main's config reference
    _input_selector.update_config(new_cfg)
    _main.current_input_config = new_cfg
    logger.info("Source config switched: %s", message)

    return {"switched": True, "source": request.source, "message": message}


@router.get("/available-videos")
async def available_videos() -> dict:
    """Scans ai-services/Data/ for playable video files."""
    videos: List[str] = []
    if os.path.isdir(_DATA_DIR):
        for fname in sorted(os.listdir(_DATA_DIR)):
            if fname.lower().endswith(_VIDEO_EXTENSIONS):
                videos.append(os.path.join("Data", fname))
    return {"videos": videos}

# ai-services/src/main.py
import os
import sys
import json
import asyncio
import logging
import threading
from pathlib import Path

# MPS memory fix — must be before any torch import
os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")

import uvicorn
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from processor import TrafficPipeline
import state_store

from vehicle_count_routes import router as vc_router
from api.rl_routes import router as rl_router
from api.source_routes import router as source_router
from api.source_routes import set_input_selector
from input_selector import InputSelector, InputConfig, InputSource

logger = logging.getLogger("traffic.main")

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_weights_override = os.getenv("WEIGHTS_DIR")
if _weights_override:
    WEIGHTS_DIR = _weights_override
else:
    candidate_a = os.path.join(BASE_DIR, "models", "weights")
    candidate_b = os.path.join(BASE_DIR, "Data", "weights")
    WEIGHTS_DIR = candidate_a if os.path.isdir(candidate_a) else candidate_b

VEHICLE_WEIGHTS  = os.path.join(WEIGHTS_DIR, "yolov8n.pt")
PLATE_WEIGHTS    = os.path.join(WEIGHTS_DIR, "best.pt")
BACKEND_BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8080")
SHOW_WINDOW      = os.getenv("SHOW_WINDOW", "1") not in ("0", "false", "False", "no", "NO")

# ── Module-level mutable state shared with source_routes ──────────────────────
current_input_config: InputConfig = InputConfig(source=InputSource.SIMULATION)
input_selector:       InputSelector = InputSelector(current_input_config)

stream_state: dict = {
    "running":     False,
    "thread":      None,
    "frame_count": 0,
    "last_result": None,
    "last_error":  None,
}

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(title="Traffic AI Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

set_input_selector(input_selector)

app.include_router(vc_router)
app.include_router(rl_router)
app.include_router(source_router)

# ── Pipeline (lazy model loading) ─────────────────────────────────────────────
pipeline = TrafficPipeline(
    vehicle_model_path=VEHICLE_WEIGHTS,
    plate_model_path=PLATE_WEIGHTS,
    backend_url=BACKEND_BASE_URL,
    show_window=SHOW_WINDOW,
)

# ── Request models ────────────────────────────────────────────────────────────

class StreamRequest(BaseModel):
    video_path:   str  = ""
    camera_index: int  = -1   # -1 means "not specified"


# ══════════════════════════════════════════════════════════════════════════════
# DETECTION THREAD
# ══════════════════════════════════════════════════════════════════════════════

def _publish_sync(client, result: dict) -> None:
    """Synchronously POST a detection result to the Spring Boot backend."""
    try:
        import httpx as _httpx
        base     = BACKEND_BASE_URL.rstrip("/")
        endpoint = base + "/api/detections"
        client.post(endpoint, json=result, timeout=3.0)
    except Exception as exc:
        name = type(exc).__name__
        if "Connect" in name:
            logger.warning("Backend unreachable: %s", exc)
        elif "Timeout" in name:
            logger.warning("Backend timed out: %s", exc)
        else:
            logger.warning("Publish error (%s): %s", name, exc)


def _process_frame_sync(frame) -> dict | None:
    """
    Run one frame through the detection pipeline synchronously.

    Uses the existing pipeline internals (vehicle model, plate model, OCR)
    but returns a payload dict instead of firing an async task.
    Returns None if no stable plate was found.
    """
    import cv2
    from datetime import datetime

    # 1. Vehicle detection
    try:
        v_results = pipeline.vehicle_model(
            frame, conf=0.5, verbose=False, device=pipeline.device
        )
    except Exception as exc:
        logger.warning("Vehicle model error: %s", exc)
        return None

    vehicle_count = sum(len(r.boxes) for r in v_results)
    state_store.state.update_vehicle_count(vehicle_count)

    result_payload = None

    for res in v_results:
        for box in res.boxes:
            vx1, vy1, vx2, vy2 = map(int, box.xyxy[0])
            v_type = res.names[int(box.cls[0])]

            car_crop = frame[vy1:vy2, vx1:vx2]
            if car_crop.size == 0:
                continue

            # 2. Plate detection inside vehicle ROI
            try:
                p_results = pipeline.plate_model(
                    car_crop, conf=0.3, verbose=False, device=pipeline.device
                )
            except Exception as exc:
                logger.warning("Plate model error: %s", exc)
                continue

            for p_res in p_results:
                for p_box in p_res.boxes:
                    px1, py1, px2, py2 = map(int, p_box.xyxy[0])
                    h_c, w_c = car_crop.shape[:2]
                    px1, py1 = max(0, px1), max(0, py1)
                    px2, py2 = min(w_c - 1, px2), min(h_c - 1, py2)

                    if px2 <= px1 or py2 <= py1:
                        continue
                    if (px2 - px1) * (py2 - py1) < 400:
                        continue

                    plate_crop = car_crop[py1:py2, px1:px2]

                    # 3. OCR + stabilisation
                    raw_text   = pipeline.recognize_and_clean(plate_crop)
                    abs_px1    = vx1 + px1
                    abs_py1    = vy1 + py1
                    track_key  = (abs_px1 // 50, abs_py1 // 50)
                    stable     = pipeline._update_plate_history(track_key, raw_text)

                    if not stable:
                        continue

                    last_sent = pipeline.tracker.get(track_key)
                    if last_sent == stable:
                        continue
                    pipeline.tracker[track_key] = stable

                    if pipeline.log_plates:
                        logger.info("Plate detected: %s", stable)

                    state_store.state.add_plate(
                        plate=stable,
                        vehicle_type=v_type,
                        location_id="INTERSECTION_A1",
                        is_valid=len(stable) >= 6,
                    )

                    result_payload = {
                        "plateNumber": stable,
                        "vehicleType": v_type,
                        "locationId":  "INTERSECTION_A1",
                        "timestamp":   datetime.now().isoformat(),
                    }

    return result_payload


def _run_detection_loop() -> None:
    """Background thread: pulls frames from InputSelector, runs detection, publishes results."""
    import httpx

    global stream_state
    stream_state["running"]     = True
    stream_state["frame_count"] = 0
    stream_state["last_error"]  = None

    logger.info("Detection loop started — source: %s", current_input_config.source.value)

    client = httpx.Client(timeout=3.0)

    try:
        gen = input_selector.get_frame_generator()
    except FileNotFoundError as exc:
        logger.error("Cannot open source: %s", exc)
        stream_state["running"]    = False
        stream_state["last_error"] = str(exc)
        client.close()
        return

    try:
        for frame, meta in gen:
            if not stream_state["running"]:
                break

            # SIMULATION mode yields None frames — count them but skip detection
            if frame is None:
                stream_state["frame_count"] += 1
                continue

            stream_state["frame_count"] += 1

            if stream_state["frame_count"] % 50 == 0:
                logger.info(
                    "Detection loop — frames processed: %d", stream_state["frame_count"]
                )

            try:
                result = _process_frame_sync(frame)
            except Exception as exc:
                logger.warning("Frame processing error (skipping): %s", exc)
                result = None

            if result is not None:
                stream_state["last_result"] = result
                _publish_sync(client, result)

    except Exception as exc:
        logger.error("Detection loop crashed: %s", exc)
        stream_state["last_error"] = str(exc)
    finally:
        stream_state["running"] = False
        client.close()
        logger.info(
            "Detection loop ended — total frames: %d", stream_state["frame_count"]
        )


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {"message": "Traffic AI Engine — Online"}


@app.get("/health")
async def health_check():
    return {"status": "Healthy"}


@app.post("/start-stream")
async def start_stream(request: StreamRequest):
    global current_input_config, input_selector

    # Stop any existing loop first
    if stream_state["running"] and stream_state["thread"] is not None:
        stream_state["running"] = False
        stream_state["thread"].join(timeout=3.0)

    # (a) Update the global config based on what was requested
    vp = request.video_path.strip()
    ci = request.camera_index

    if vp:
        # Could be a webcam shorthand
        if vp in ("0", "webcam"):
            current_input_config = InputConfig(source=InputSource.CAMERA, camera_index=0)
        else:
            # Normalise relative paths to ai-services root
            if not os.path.isabs(vp):
                full = os.path.join(BASE_DIR, vp)
            else:
                full = vp
            current_input_config = InputConfig(source=InputSource.VIDEO, video_path=full)
    elif ci >= 0:
        current_input_config = InputConfig(source=InputSource.CAMERA, camera_index=ci)
    else:
        current_input_config = InputConfig(source=InputSource.SIMULATION)

    # (b) Recreate the InputSelector with the updated config
    input_selector = InputSelector(current_input_config)
    set_input_selector(input_selector)

    # (c) Launch the detection thread
    t = threading.Thread(
        target=_run_detection_loop,
        name="detection-loop",
        daemon=True,
    )
    stream_state["thread"] = t
    t.start()

    return {
        "status":  "Processing started",
        "source":  current_input_config.source.value,
        "details": current_input_config.video_path or current_input_config.camera_index,
    }


@app.post("/stop-stream")
async def stop_stream():
    stream_state["running"] = False
    return {
        "status":       "stopped",
        "total_frames": stream_state["frame_count"],
    }


@app.get("/stream-status")
async def get_stream_status():
    return {
        "running":     stream_state["running"],
        "frame_count": stream_state["frame_count"],
        "source":      current_input_config.source.value,
        "last_error":  stream_state["last_error"],
    }


# ── Legacy /start-stream that accepts a bare video_path string (backward compat)
@app.post("/start-stream-legacy")
async def start_stream_legacy(request: StreamRequest, background_tasks: BackgroundTasks):
    """Backward-compat shim: runs the async process_stream directly (no InputSelector)."""
    p = request.video_path.strip()
    if p in ("0", "webcam"):
        source = 0
    else:
        if not any(p.startswith(s) for s in ("rtsp://", "http://", "https://")):
            candidate = str(Path(BASE_DIR) / p)
            source = candidate if os.path.exists(candidate) else p
        else:
            source = p
    background_tasks.add_task(pipeline.process_stream, source)
    return {"status": "Processing Started", "source": request.video_path}


# ── Live stats (SSE) ──────────────────────────────────────────────────────────

@app.get("/stats")
async def get_stats():
    return state_store.state.snapshot()


@app.get("/stats/stream")
async def stats_stream(request: Request):
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            data = json.dumps(state_store.state.snapshot())
            yield f"data: {data}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/dashboard")
async def dashboard():
    return HTMLResponse(content="<h1>AI Service running. Main dashboard at :8080</h1>")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)

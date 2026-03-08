<<<<<<< HEAD
import asyncio
from fastapi import FastAPI, BackgroundTasks
from src.processor import TrafficPipeline

app = FastAPI(title="Traffic AI Engine")

# Initialize the pipeline with your paths and backend URL
pipeline = TrafficPipeline(
    vehicle_model_path="models/yolov8n.pt",
    plate_model_path="models/license_plate_best.pt",
    backend_url="http://localhost:8080/api/detections"
=======
import uvicorn
import os
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from processor import TrafficPipeline


class StreamRequest(BaseModel):
    video_path: str

# Resolve project root dynamically (works both locally and in Docker)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_weights_override = os.getenv("WEIGHTS_DIR")
if _weights_override:
    WEIGHTS_DIR = _weights_override
else:
    # Prefer ./models/weights, fallback to ./Data/weights for older layouts.
    candidate_a = os.path.join(BASE_DIR, "models", "weights")
    candidate_b = os.path.join(BASE_DIR, "Data", "weights")
    WEIGHTS_DIR = candidate_a if os.path.isdir(candidate_a) else candidate_b

VEHICLE_WEIGHTS = os.path.join(WEIGHTS_DIR, "yolov8n.pt")
PLATE_WEIGHTS = os.path.join(WEIGHTS_DIR, "best.pt")

BACKEND_BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8080")
SHOW_WINDOW = os.getenv("SHOW_WINDOW", "1") not in ("0", "false", "False", "no", "NO")

app = FastAPI(title="Traffic AI Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the pipeline with your paths and backend URL
pipeline = TrafficPipeline(
    vehicle_model_path=VEHICLE_WEIGHTS,
    plate_model_path=PLATE_WEIGHTS,
    backend_url=BACKEND_BASE_URL,
    show_window=SHOW_WINDOW,
>>>>>>> 48bccc1 (incomplete test files)
)

@app.get("/")
async def root():
    return {"message": "Traffic AI Service is Online"}

@app.post("/start-stream")
<<<<<<< HEAD
async def start_stream(video_path: str, background_tasks: BackgroundTasks):
=======
async def start_stream(request: StreamRequest, background_tasks: BackgroundTasks):
>>>>>>> 48bccc1 (incomplete test files)
    """
    Starts the two-model pipeline in the background.
    video_path can be a file path, an RTSP link, or '0' for webcam.
    """
    # Use BackgroundTasks so the API doesn't hang while processing video
<<<<<<< HEAD
    background_tasks.add_task(pipeline.process_stream, video_path)
    return {"status": "Processing Started", "source": video_path}
=======
    p = request.video_path.strip()
    if p in ("0", "webcam"):
        source = 0
    else:
        # If a relative path is provided, resolve it relative to the ai-services root.
        # This allows calling with "Data/video.mp4" (works in Docker with the volume mount).
        if not (p.startswith("rtsp://") or p.startswith("http://") or p.startswith("https://")):
            candidate = str(Path(BASE_DIR) / p)
            source = candidate if os.path.exists(candidate) else p
        else:
            source = p
    background_tasks.add_task(pipeline.process_stream, source)
    return {"status": "Processing Started", "source": request.video_path}
>>>>>>> 48bccc1 (incomplete test files)

@app.get("/health")
async def health_check():
    # In a professional setup, you'd check GPU/CPU usage here
<<<<<<< HEAD
    return {"status": "Healthy"}
=======
    return {"status": "Healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
>>>>>>> 48bccc1 (incomplete test files)

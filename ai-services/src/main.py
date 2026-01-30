import asyncio
from fastapi import FastAPI, BackgroundTasks
from src.processor import TrafficPipeline

app = FastAPI(title="Traffic AI Engine")

# Initialize the pipeline with your paths and backend URL
pipeline = TrafficPipeline(
    vehicle_model_path="models/yolov8n.pt",
    plate_model_path="models/license_plate_best.pt",
    backend_url="http://localhost:8080/api/detections"
)

@app.get("/")
async def root():
    return {"message": "Traffic AI Service is Online"}

@app.post("/start-stream")
async def start_stream(video_path: str, background_tasks: BackgroundTasks):
    """
    Starts the two-model pipeline in the background.
    video_path can be a file path, an RTSP link, or '0' for webcam.
    """
    # Use BackgroundTasks so the API doesn't hang while processing video
    background_tasks.add_task(pipeline.process_stream, video_path)
    return {"status": "Processing Started", "source": video_path}

@app.get("/health")
async def health_check():
    # In a professional setup, you'd check GPU/CPU usage here
    return {"status": "Healthy"}
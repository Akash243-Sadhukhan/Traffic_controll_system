import cv2
import os
import asyncio
from processor import TrafficPipeline

# 1. SETUP PATHS
BASE_DIR = "/Volumes/Akash/Traffic_controll_system/ai-services"
VIDEO_PATH = os.path.join(BASE_DIR, "Data", "t.mp4")
VEHICLE_WEIGHTS = os.path.join(BASE_DIR, "models", "weights", "yolov8n.pt")
PLATE_WEIGHTS = os.path.join(BASE_DIR, "models", "weights", "best.pt")
BACKEND_URL = "http://localhost:8080/api/detections"

def run_test():
    # Check files
    if not os.path.exists(VEHICLE_WEIGHTS):
        print(f"❌ ERROR: Vehicle model not found at {VEHICLE_WEIGHTS}")
        return
    if not os.path.exists(PLATE_WEIGHTS):
        print(f"❌ ERROR: Plate model not found at {PLATE_WEIGHTS}")
        return
    if not os.path.exists(VIDEO_PATH):
        print(f"❌ ERROR: Video file not found at {VIDEO_PATH}")
        return

    print("--- Starting Traffic Pipeline Test ---")
    
    # Initialize Pipeline
    pipeline = TrafficPipeline(VEHICLE_WEIGHTS, PLATE_WEIGHTS, BACKEND_URL)
    
    # Run the async process
    # Since process_stream is async, we need to run it in an event loop
    try:
        asyncio.run(pipeline.process_stream(VIDEO_PATH))
    except KeyboardInterrupt:
        print("Test stopped by user.")

if __name__ == "__main__":
    run_test()
import cv2
import os
import asyncio
from processor import TrafficPipeline

# 1. SETUP PATHS
BASE_DIR = "/Volumes/Akash/Traffic_controll_system/ai-services"
<<<<<<< HEAD
VIDEO_PATH = os.path.join(BASE_DIR, "Data", "t.mp4")
=======
VIDEO_PATH = os.path.join(BASE_DIR, "Data", "video.mp4")
>>>>>>> 48bccc1 (incomplete test files)
VEHICLE_WEIGHTS = os.path.join(BASE_DIR, "models", "weights", "yolov8n.pt")
PLATE_WEIGHTS = os.path.join(BASE_DIR, "models", "weights", "best.pt")
BACKEND_URL = "http://localhost:8080/api/detections"

def run_test():
<<<<<<< HEAD
    # Check files
=======
    # Validate required files exist before continuing
>>>>>>> 48bccc1 (incomplete test files)
    if not os.path.exists(VEHICLE_WEIGHTS):
        print(f"❌ ERROR: Vehicle model not found at {VEHICLE_WEIGHTS}")
        return
    if not os.path.exists(PLATE_WEIGHTS):
        print(f"❌ ERROR: Plate model not found at {PLATE_WEIGHTS}")
        return
    if not os.path.exists(VIDEO_PATH):
        print(f"❌ ERROR: Video file not found at {VIDEO_PATH}")
        return

<<<<<<< HEAD
    print("--- Starting Traffic Pipeline Test ---")
    
    # Initialize Pipeline
    pipeline = TrafficPipeline(VEHICLE_WEIGHTS, PLATE_WEIGHTS, BACKEND_URL)
    
    # Run the async process
    # Since process_stream is async, we need to run it in an event loop
    try:
        asyncio.run(pipeline.process_stream(VIDEO_PATH))
    except KeyboardInterrupt:
        print("Test stopped by user.")
=======
    print("--- Starting Traffic Pipeline Stream ---")
    print("Press 'q' in the window to exit.")
    
    # Initialize pipeline and run the stream processing
    pipeline = TrafficPipeline(VEHICLE_WEIGHTS, PLATE_WEIGHTS, BACKEND_URL)
    print(f"DEBUG: Processing frame on device {pipeline.device}")
    asyncio.run(pipeline.process_stream(VIDEO_PATH))

>>>>>>> 48bccc1 (incomplete test files)

if __name__ == "__main__":
    run_test()
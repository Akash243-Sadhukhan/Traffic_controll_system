import cv2
import os
from orc_textdetection import LicensePlateDetector

# 1. SETUP PATHS (Absolute paths are safer)
# BASE_DIR is now the project root: /Volumes/Akash/Traffic_controll_system/ai-services
BASE_DIR = "/Volumes/Akash/Traffic_controll_system/ai-services"
VIDEO_PATH = os.path.join(BASE_DIR, "Data", "video.mp4")  # Changed back to video path


def test_detection():
    if not os.path.exists(VIDEO_PATH):
        print(f"❌ ERROR: Video file not found at {VIDEO_PATH}")
        return

    print("Starting Video Detection...")
    
    # Instantiate the detector
    # Note: The model path is handled inside the class, or you can pass it if needed
    detector = LicensePlateDetector()
    
    # Use the method from the class to run inference
    detector.run_video_inference(VIDEO_PATH)

    print("Test finished.")

if __name__ == "__main__":
    test_detection()

"""
License Plate Detection and Recognition Module
==============================================

Description:
------------
This module implements a robust license plate detection and recognition system using a combination of
YOLO (You Only Look Once) for object detection and EasyOCR for optical character recognition.
It is designed to process video frames, detect license plates, extract text, and stabilize the
readings over multiple frames to ensure accuracy.

Architecture & Workflow:
------------------------
1. Initialization (LicensePlateDetector class):
   - Loads the YOLO model (custom trained for license plates).
   - Initializes the EasyOCR reader for text extraction.
   - Sets up regex patterns for Indian license plate formats.
   - Configures history buffers (deque) for stabilizing OCR results over time.

2. Preprocessing (preprocess_for_ocr):
   - Converts the cropped license plate image to grayscale.
   - Applies CLAHE (Contrast Limited Adaptive Histogram Equalization) to enhance contrast.
   - Uses Bilateral Filtering to reduce noise while preserving edges.
   - Upscales the image to improve OCR accuracy on small text.

3. Recognition (recognize_plate):
   - Passes the preprocessed image to EasyOCR.
   - Extracts text and sorts results by confidence.
   - Applies 'correct_plate_format' to fix common OCR errors (e.g., '0' vs 'O', '8' vs 'B') based on
     expected character positions (Alpha vs Numeric).

4. Stabilization (get_stable_plate):
   - Uses a spatial ID ('get_box_id') to track plates across frames.
   - Maintains a history of recognized text for each tracked plate.
   - Returns the most frequent text (mode) from the history buffer to filter out flickering or erroneous reads.

5. Frame Processing (process_frame):
   - Runs YOLO detection on the full video frame.
   - Crops detected regions.
   - Runs the recognition and stabilization pipeline.
   - Returns a list of detections with bounding boxes and stabilized text.

6. Inference Loop (run_video_inference):
   - Captures video from a file.
   - Iterates through frames, calling 'process_frame'.
   - Visualizes results (bounding boxes and text) on the video.
   - Sends detected data to a Spring Boot backend API via HTTP POST.

Dependencies:
-------------
- opencv-python (cv2): Image processing and video capture.
- ultralytics (YOLO): Object detection model.
- easyocr: Text recognition.
- numpy: Array manipulations.
- requests: HTTP client for backend communication.
"""

import cv2
import numpy as np
from ultralytics import YOLO
import easyocr
import re
import requests
import os
from collections import defaultdict, deque


class LicensePlateDetector:
    def __init__(self, model_path=None):
        """
        Initialize the detector with model paths and configurations.
        """
        # Resolve absolute path to model
        if model_path is None:
            # Assuming the script is running from project root
            # The structure is:
            # /Volumes/Akash/Traffic_controll_system/
            #   models/weights /license_plate_best.pt
            #   src/orc_textdetection.py
            
            # Use absolute path to avoid relative path issues
            base_path = "/Volumes/Akash/Traffic_controll_system/ai-services"
            model_path = os.path.join(base_path, "models", "weights ", "best.pt")

        print(f"Loading model from: {model_path}")
        
        try:
            self.model = YOLO(model_path)
        except Exception as e:
            print(f"Error loading model: {e}. Check your file path!")
            raise e

        self.reader = easyocr.Reader(['en'], gpu=True)

        # 2. RELAXED: Indian plates can be 9 or 10 characters (e.g., DL3C 1234 or DL03CA 1234)
        self.plate_pattern = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{4}$")

        self.plate_history = defaultdict(lambda: deque(maxlen=15))
        self.plate_final = {}

        self.mapping_num_to_alpha = {"0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B"}
        self.mapping_alpha_to_num = {"O": "0", "I": "1", "Z": "2", "S": "5", "G": "6", "B": "8"}

    def preprocess_for_ocr(self, plate_crop):
        """Enhances image quality specifically for text recognition."""
        if plate_crop.size == 0: return None

        # Convert to Gray and enhance contrast using CLAHE
        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        contrast = clahe.apply(gray)

        # Denoise while keeping edges sharp
        blurred = cv2.bilateralFilter(contrast, 9, 75, 75)

        # Upscale for OCR accuracy
        upscaled = cv2.resize(blurred, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        return upscaled

    def correct_plate_format(self, text):
        """Smart correction for common OCR character confusion."""
        text = text.upper().replace(" ", "").strip()
        # Filter non-alphanumeric noise
        text = "".join(c for c in text if c.isalnum())

        # Simple format correction (first 2 should be Alpha, last 4 Num)
        res = list(text)
        for i in range(len(res)):
            if i < 2 and res[i].isdigit():  # First two chars
                res[i] = self.mapping_num_to_alpha.get(res[i], res[i])
            elif i >= len(res) - 4 and res[i].isalpha():  # Last four chars
                res[i] = self.mapping_alpha_to_num.get(res[i], res[i])
        return "".join(res)

    def recognize_plate(self, plate_crop):
        processed = self.preprocess_for_ocr(plate_crop)
        if processed is None: return ""

        try:
            # paragraph=False prevents splitting text into different lines
            results = self.reader.readtext(processed, detail=1, paragraph=False)
            if not results: return ""

            # Sort results by confidence and pick the best one
            results.sort(key=lambda x: x[2], reverse=True)
            raw_text = results[0][1]

            clean_text = self.correct_plate_format(raw_text)
            return clean_text
        except:
            return ""

    def get_box_id(self, x1, y1, x2, y2):
        # 3. FIXED: Increased tolerance to 50px so ID doesn't break during motion
        return f"{int(x1 / 50)}_{int(y1 / 50)}"

    def get_stable_plate(self, box_id, new_text):
        if len(new_text) > 5:  # Only save if we got a decent read
            self.plate_history[box_id].append(new_text)
            # Find the most frequent text in the last 15 frames
            most_common = max(self.plate_history[box_id], key=self.plate_history[box_id].count)
            self.plate_final[box_id] = most_common
        return self.plate_final.get(box_id, "Scanning...")

    def process_frame(self, frame):
        # Lower confidence to 0.2 to catch blurred plates
        results = self.model(frame, verbose=True, conf=0.20)
        detections = []

        for result in results:
            for box in result.boxes:
                coords = box.xyxy[0].tolist()
                x1, y1, x2, y2 = map(int, coords)

                # Expand crop slightly to catch plate edges
                pad = 5
                h, w, _ = frame.shape
                plate_crop = frame[max(0, y1 - pad):min(h, y2 + pad), max(0, x1 - pad):min(w, x2 + pad)]

                raw_text = self.recognize_plate(plate_crop)
                box_id = self.get_box_id(x1, y1, x2, y2)
                stable_text = self.get_stable_plate(box_id, raw_text)

                detections.append({
                    'bbox': (x1, y1, x2, y2),
                    'text': stable_text,
                    'stable_text': stable_text, # Added for compatibility with main.py
                    'is_valid': bool(self.plate_pattern.match(stable_text))
                })
        return detections

    def run_video_inference(self,video_path):
        cap = cv2.VideoCapture(video_path)
        # Instantiate the class
        # Pass self.model.model to reuse the loaded model if needed, but here we are inside the class instance
        # The issue in the traceback was creating a NEW instance inside run_video_inference without passing the path
        # We should use 'self' methods instead of creating a new detector instance.
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            # Call the logic from src/detector.py
            results = self.process_frame(frame)

            # Draw results on the frame (Visualization)
            for det in results:
                x1, y1, x2, y2 = det['bbox']
                text = det['stable_text'] if det['stable_text'] else det['text']

                # Draw bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)


                # Draw text background
                if text:
                    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
                    cv2.rectangle(frame, (x1, y1 - 30), (x1 + w, y1), (0, 255, 0), -1)
                    cv2.putText(frame, text, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)

                # prepare data for spring boot
                data = {
                    "vehicleType": text,
                    "Timestamp": "2026-01-20T22:30:00Z",
                    "locationId": "Intersection_01"
                }
                
                # post to spring boot api
                try:
                    requests.post("http://localhost:8080/api/detections",json=data, timeout=0.1)
                except:
                    pass

            cv2.imshow('Traffic System', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()
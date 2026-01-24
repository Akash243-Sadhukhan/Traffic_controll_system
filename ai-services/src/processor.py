
"""
Traffic Control System - AI Processor Pipeline
==============================================

Description:
------------
This script implements a real-time computer vision pipeline designed to monitor traffic flow
and detect vehicle violations. It integrates two distinct YOLO (You Only Look Once) models
to perform a hierarchical detection process:

1. Vehicle Detection: Identifies vehicles (cars, trucks, buses, motorcycles) in the video stream.
2. License Plate Detection: Analyzes the detected vehicle regions (ROI) to locate license plates.

Key Functions:
--------------
- TrafficPipeline Class: Encapsulates the entire processing logic.
    - __init__: Initializes the YOLO models for vehicle and plate detection and sets up the backend API endpoint.
    - send_data: Asynchronously transmits detection data (vehicle type, location, timestamp, etc.) to the Spring Boot backend service via HTTP POST requests.
    - process_stream: The core loop that reads video frames, runs the detection cascade, and triggers data transmission upon successful detection.

Workflow:
---------
1. Video Ingestion: Captures frames from a video source (file or camera stream).
2. Primary Detection (Vehicles): The 'vehicle_model' scans the full frame to locate vehicles.
3. Region of Interest (ROI) Extraction: For each detected vehicle, the corresponding image area is cropped.
4. Secondary Detection (Plates): The 'plate_model' scans the cropped vehicle image to find license plates.
5. Data Aggregation & Transmission: If a plate is detected, relevant metadata (vehicle type, location ID, timestamp) is packaged into a JSON payload and sent to the backend server for logging and further processing (e.g., violation ticketing).

Usage:
------
This script is intended to run as a background service or within a containerized environment (e.g., Docker), continuously processing video feeds from traffic cameras.
"""

import cv2
import httpx
import asyncio
from ultralytics import YOLO
from datetime import datetime


class TrafficPipeline:
    def __init__(self, vehicle_model_path, plate_model_path, backend_url):
        """
        Initialize the TrafficPipeline with model paths and backend configuration.
        
        Args:
            vehicle_model_path (str): Path to the YOLO model weights for vehicle detection.
            plate_model_path (str): Path to the YOLO model weights for license plate detection.
            backend_url (str): The HTTP endpoint of the Spring Boot application to receive data.
        """
        # Load specialized models
        self.vehicle_model = YOLO(vehicle_model_path)
        self.plate_model = YOLO(plate_model_path)
        self.backend_url = backend_url

    async def send_data(self, payload):
        """
        Async call to Spring Boot backend to send detection events.
        
        Args:
            payload (dict): JSON-serializable dictionary containing event details.
        """
        try:
            async with httpx.AsyncClient() as client:
                await client.post(self.backend_url, json=payload, timeout=1.0)
        except Exception as e:
            print(f"Connection Error: {e}")

    async def process_stream(self, video_source):
        """
        Main processing loop for video frames.
        
        Args:
            video_source (str or int): Path to video file or camera index (0 for webcam).
        """
        cap = cv2.VideoCapture(video_source)

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            # 1. Detect Vehicles (Cars, Trucks, etc.)
            vehicle_results = self.vehicle_model(frame, conf=0.5, verbose=False)

            for res in vehicle_results:
                for box in res.boxes:
                    # Get coordinates for the car
                    vx1, vy1, vx2, vy2 = map(int, box.xyxy[0])
                    vehicle_type = res.names[int(box.cls[0])]

                    # 2. Crop the Vehicle (ROI)
                    # Ensure coordinates are within frame bounds
                    h, w, _ = frame.shape
                    vx1, vy1 = max(0, vx1), max(0, vy1)
                    vx2, vy2 = min(w, vx2), min(h, vy2)
                    
                    if vx1 >= vx2 or vy1 >= vy2:
                        continue
                        
                    car_crop = frame[vy1:vy2, vx1:vx2]

                    # 3. Detect License Plate within the crop
                    plate_results = self.plate_model(car_crop, conf=0.3, verbose=False)

                    for p_res in plate_results:
                        for p_box in p_res.boxes:
                            # If a plate is found, prepare data for Spring Boot
                            payload = {
                                "vehicleType": vehicle_type,
                                "locationId": "INTERSECTION_A1",
                                "timestamp": datetime.now().isoformat()  # Use dynamic timestamp
                            }
                            await self.send_data(payload)

            # Optional: Display for local debugging
            # cv2.imshow('Pipeline', frame)
            # if cv2.waitKey(1) & 0xFF == ord('q'): break

        cap.release()

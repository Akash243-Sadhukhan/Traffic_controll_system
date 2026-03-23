
"""
License Plate Detection and Recognition Module
==============================================

Description:
------------
This module implements a robust license plate detection and recognition system using a combination of
YOLO (You Only Look Once) for object detection and an ensemble of EasyOCR and TrOCR for optical
character recognition. It is designed to process video frames, detect license plates, extract text,
and stabilize the readings over multiple frames to ensure accuracy.

Architecture & Workflow:
------------------------
1. Initialization (LicensePlateDetector class):
   - Loads the YOLO model.
   - Initializes the OcrEnsemble, which loads and caches EasyOCR and TrOCR models.
   - Sets up regex patterns and history buffers for stabilization.

2. Recognition (recognize_plate):
   - Asynchronously calls the OcrEnsemble to run both OCR models in parallel.
   - The ensemble returns a result based on weighted confidence and character-level voting.

3. Stabilization (get_stable_plate):
   - Uses a centroid tracker to maintain object identity across frames.
   - Stores a history of recognized text for each plate.
   - Returns the most frequent (mode) text from the history to filter out errors.

4. Frame Processing (process_frame):
   - Runs YOLO detection on the video frame.
   - Creates asynchronous OCR tasks for each detected plate.
   - Executes all tasks concurrently using asyncio.gather.
   - Applies format correction and stabilization to the results.

5. Inference Loop (run_video_inference):
   - Captures video, processes frames, and visualizes results.
   - Sends detected data to a backend API.

Dependencies:
-------------
- opencv-python, ultralytics, easyocr, numpy, requests, torch, transformers
"""

import cv2
import numpy as np
import torch
from ultralytics import YOLO
import re
import requests
import os
from collections import deque, OrderedDict
from scipy.spatial import distance as dist
import asyncio
from ocr_ensemble import OcrEnsemble # Import the new ensemble class


class LicensePlateDetector:
    def __init__(self, model_path=None):
        """
        Initialize the detector with model paths and configurations.
        """
        if model_path is None:
            base_path = "/Volumes/Akash/Traffic_controll_system/ai-services"
            model_path = os.path.join(base_path, "models", "weights ", "best.pt")

        print(f"Loading YOLO model from: {model_path}")
        try:
            self.model = YOLO(model_path)
        except Exception as e:
            print(f"Error loading YOLO model: {e}. Check your file path!")
            raise e

        self.device = 'mps' if torch.backends.mps.is_available() else 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"Using device: {self.device}")
        self.model.to(self.device)

        # Initialize the OCR Ensemble
        self.ocr_ensemble = OcrEnsemble()

        self.plate_pattern = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{4}$")

        # Centroid Tracker State
        self.next_object_id = 0
        self.objects = OrderedDict()
        self.disappeared = OrderedDict()
        self.max_disappeared = 10
        self.plate_history = {}
        self.plate_final = {}

        self.mapping_num_to_alpha = {"0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B"}
        self.mapping_alpha_to_num = {"O": "0", "I": "1", "Z": "2", "S": "5", "G": "6", "B": "8"}

    def correct_plate_format(self, text):
        """Smart correction for common OCR character confusion."""
        if not text: return ""
        text = text.upper().replace(" ", "").strip()
        text = "".join(c for c in text if c.isalnum())

        res = list(text)
        for i in range(len(res)):
            if i < 2 and res[i].isdigit():
                res[i] = self.mapping_num_to_alpha.get(res[i], res[i])
            elif i >= len(res) - 4 and res[i].isalpha():
                res[i] = self.mapping_alpha_to_num.get(res[i], res[i])
        return "".join(res)

    def get_centroid(self, x1, y1, x2, y2):
        return (int((x1 + x2) / 2.0), int((y1 + y2) / 2.0))

    def register(self, centroid):
        self.objects[self.next_object_id] = centroid
        self.disappeared[self.next_object_id] = 0
        self.plate_history[self.next_object_id] = deque(maxlen=15)
        self.next_object_id += 1

    def deregister(self, object_id):
        del self.objects[object_id]
        del self.disappeared[object_id]
        if object_id in self.plate_history:
            del self.plate_history[object_id]

    def update_tracker(self, rects):
        if len(rects) == 0:
            for object_id in list(self.disappeared.keys()):
                self.disappeared[object_id] += 1
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)
            return self.objects

        input_centroids = np.zeros((len(rects), 2), dtype="int")
        for (i, (x1, y1, x2, y2)) in enumerate(rects):
            input_centroids[i] = self.get_centroid(x1, y1, x2, y2)

        if len(self.objects) == 0:
            for i in range(len(input_centroids)):
                self.register(input_centroids[i])
        else:
            object_ids = list(self.objects.keys())
            object_centroids = list(self.objects.values())
            D = dist.cdist(np.array(object_centroids), input_centroids)
            rows = D.min(axis=1).argsort()
            cols = D.argmin(axis=1)[rows]

            used_rows, used_cols = set(), set()
            for (row, col) in zip(rows, cols):
                if row in used_rows or col in used_cols: continue
                object_id = object_ids[row]
                self.objects[object_id] = input_centroids[col]
                self.disappeared[object_id] = 0
                used_rows.add(row)
                used_cols.add(col)

            unused_rows = set(range(D.shape[0])).difference(used_rows)
            unused_cols = set(range(D.shape[1])).difference(used_cols)

            if D.shape[0] >= D.shape[1]:
                for row in unused_rows:
                    object_id = object_ids[row]
                    self.disappeared[object_id] += 1
                    if self.disappeared[object_id] > self.max_disappeared:
                        self.deregister(object_id)
            else:
                for col in unused_cols:
                    self.register(input_centroids[col])
        return self.objects

    async def recognize_plate(self, plate_crop):
        """
        Asynchronously recognizes text from a plate crop using the OCR ensemble.
        """
        if plate_crop.shape[0] < 15 or plate_crop.shape[1] < 15:
            return ""
        return await self.ocr_ensemble.recognize(plate_crop)

    def get_stable_plate(self, object_id, new_text):
        if len(new_text) > 5:
            if object_id in self.plate_history:
                self.plate_history[object_id].append(new_text)
            if object_id in self.plate_history and self.plate_history[object_id]:
                most_common = max(self.plate_history[object_id], key=self.plate_history[object_id].count)
                self.plate_final[object_id] = most_common
        return self.plate_final.get(object_id, "Scanning...")

    async def process_frame_async(self, frame):
        """
        Asynchronously processes a single frame for license plate detection and recognition.
        """
        results = self.model(frame, verbose=False, device=self.device, conf=0.25)
        
        rects, box_map = [], []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                rects.append((x1, y1, x2, y2))
                c = self.get_centroid(x1, y1, x2, y2)
                box_map.append((c, (x1, y1, x2, y2)))

        tracked_objects = self.update_tracker(rects)
        
        tasks, task_to_id_map = [], {}
        for object_id, centroid in tracked_objects.items():
            matched_box = None
            for bc, bbox in box_map:
                if bc == tuple(centroid):
                    matched_box = bbox
                    break
            
            if matched_box:
                x1, y1, x2, y2 = matched_box
                pad = 5
                h, w, _ = frame.shape
                plate_crop = frame[max(0, y1 - pad):min(h, y2 + pad), max(0, x1 - pad):min(w, x2 + pad)]
                
                task = self.recognize_plate(plate_crop)
                tasks.append(task)
                task_to_id_map[id(task)] = (object_id, matched_box)

        # Run all OCR tasks concurrently
        ocr_results = await asyncio.gather(*tasks)

        detections = []
        for i, raw_text in enumerate(ocr_results):
            task_id = id(tasks[i])
            object_id, (x1, y1, x2, y2) = task_to_id_map[task_id]
            
            clean_text = self.correct_plate_format(raw_text)
            stable_text = self.get_stable_plate(object_id, clean_text)

            detections.append({
                'bbox': (x1, y1, x2, y2),
                'text': clean_text,
                'stable_text': stable_text,
                'is_valid': bool(self.plate_pattern.match(stable_text))
            })
        return detections

    def run_video_inference(self, video_path):
        cap = cv2.VideoCapture(video_path)
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            # Run the async frame processing
            results = asyncio.run(self.process_frame_async(frame))

            for det in results:
                x1, y1, x2, y2 = det['bbox']
                text = det['stable_text'] if det['stable_text'] else det['text']

                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                if text:
                    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
                    cv2.rectangle(frame, (x1, y1 - 30), (x1 + w, y1), (0, 255, 0), -1)
                    cv2.putText(frame, text, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)

                data = {
                    "vehicleType": text,
                    "Timestamp": "2026-01-20T22:30:00Z",
                    "locationId": "Intersection_01"
                }
                
                try:
                    requests.post("http://localhost:8080/api/detections", json=data, timeout=0.1)
                except requests.exceptions.RequestException:
                    pass

            cv2.imshow('Traffic System', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()

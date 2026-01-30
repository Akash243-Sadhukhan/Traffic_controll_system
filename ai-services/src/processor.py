"""Traffic processing pipeline.

This module provides the TrafficPipeline class which encapsulates:
- Loading vehicle and plate detection models (YOLO via ultralytics)
- Running real-time video frame processing
- OCR of detected license plates (EasyOCR) with preprocessing
- Simple plate-history tracking
- Asynchronous reporting to a backend service

The module is intentionally defensive (checks for required packages at import time)
and includes helpers to stabilize OCR results and to safely crop image regions.
"""

import asyncio
import re
import logging
from collections import OrderedDict, defaultdict, deque
from datetime import datetime

# Dependency checks with helpful error messages
try:
    import torch
except Exception as e:
    raise ImportError("Missing dependency 'torch'. Install PyTorch (https://pytorch.org/) and try again.") from e

try:
    from ultralytics import YOLO
except Exception as e:
    raise ImportError("Missing dependency 'ultralytics'. Install with 'pip install ultralytics'.") from e

try:
    import easyocr
except Exception as e:
    raise ImportError("Missing dependency 'easyocr'. Install with 'pip install easyocr'.") from e

try:
    import cv2
except Exception as e:
    raise ImportError("Missing dependency 'opencv-python'. Install with 'pip install opencv-python' or 'opencv-python-headless'.") from e

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TrafficPipeline:
    """High-level pipeline for vehicle and plate detection with OCR and backend reporting.

    The pipeline coordinates model loading, frame processing, OCR preprocessing, and
    asynchronous delivery of detection JSON payloads to a configured backend endpoint.

    Typical usage:
        pipeline = TrafficPipeline('vehicle.pt', 'plate.pt', 'http://localhost:8080')
        asyncio.run(pipeline.process_stream(0))  # use 0 for default webcam
    """

    def __init__(self, vehicle_model_path, plate_model_path, backend_url):
        """Initialize models and engines used by the pipeline.

        Args:
            vehicle_model_path (str): Path or model identifier for vehicle YOLO model.
            plate_model_path (str): Path or model identifier for license-plate YOLO model.
            backend_url (str): Base URL for backend service (e.g., 'http://host:8080').
        """
        # Prefer MPS on macOS when available, fallback to CPU
        self.device = 'mps' if torch.backends.mps.is_available() else 'cpu'
        logger.info(f"🚀 AI Engine Active on: {self.device}")

        # 1. Models
        # Load models; ultralytics' YOLO supports device movement via .to()
        self.vehicle_model = YOLO(vehicle_model_path)
        try:
            self.vehicle_model.to(self.device)
        except Exception:
            logger.debug("Could not move vehicle_model to device, continuing with default device.")

        self.plate_model = YOLO(plate_model_path)
        try:
            self.plate_model.to(self.device)
        except Exception:
            logger.debug("Could not move plate_model to device, continuing with default device.")
        
        # 2. OCR Engine (Mac Optimized)
        # easyocr's Reader will choose GPU when gpu=True and a compatible GPU/back-end exists
        self.reader = easyocr.Reader(['en'], gpu=(self.device == 'mps'))
        self.backend_url = backend_url

        # 3. Tracking & History (from orc.py)
        self.tracker = OrderedDict()
        self.plate_history = defaultdict(lambda: deque(maxlen=15))
        self.next_id = 0

    # --- OCR helpers ---
    def preprocess_for_ocr(self, plate_img):
        """Prepare a license-plate crop for OCR.

        Steps performed:
          - Convert to grayscale (if BGR input)
          - Resize to a reasonable maximum dimension while keeping aspect ratio
          - Apply Otsu thresholding to increase contrast between text and background

        Args:
            plate_img (numpy.ndarray): BGR or grayscale image of the plate region.
        Returns:
            numpy.ndarray: Single-channel thresholded image ready for OCR.
        """
        try:
            gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
        except Exception:
            # If plate_img is already single channel or conversion fails, use as-is
            gray = plate_img
        h, w = gray.shape[:2]
        scale = 400 / max(1, max(w, h))
        if scale != 1:
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LINEAR)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return thresh

    def correct_plate_format(self, text: str) -> str:
        """Normalize OCR output to a canonical plate format.

        This function performs light normalization only (keeps digits and ASCII letters,
        upper-cases the string and removes non-alphanumeric characters). It deliberately
        avoids country-specific formatting rules; you can extend it for locale-aware
        validation or regex-based formatting.

        Args:
            text (str): Raw OCR text
        Returns:
            str: Cleaned uppercase alphanumeric string (may be empty)
        """
        cleaned = re.sub(r'[^A-Z0-9]', '', text.upper())
        return cleaned

    async def process_stream(self, video_source):
        """Read frames from a video source and process detections in a loop.

        The method blocks (asynchronous-friendly) while the video is open. It detects
        vehicles, crops vehicle ROIs, runs a second YOLO pass for plates, runs OCR,
        and sends detection payloads to the backend asynchronously.

        Args:
            video_source (int | str): OpenCV video source (0 for webcam, or filepath/URL).
        """
        cap = cv2.VideoCapture(video_source)
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            # STEP 1: Detect Vehicles
            v_results = self.vehicle_model(frame, conf=0.5, verbose=False, device=self.device)
            
            for res in v_results:
                for box in res.boxes:
                    vx1, vy1, vx2, vy2 = map(int, box.xyxy[0])
                    v_type = res.names[int(box.cls[0])]

                    # STEP 2: ROI - Crop the Vehicle
                    car_crop = frame[vy1:vy2, vx1:vx2]
                    if car_crop.size == 0: continue

                    # STEP 3: Detect Plate inside Car ROI
                    p_results = self.plate_model(car_crop, conf=0.3, verbose=False, device=self.device)

                    for p_res in p_results:
                        for p_box in p_res.boxes:
                            px1, py1, px2, py2 = map(int, p_box.xyxy[0])
                            h_c, w_c = car_crop.shape[:2]
                            px1, py1 = max(0, px1), max(0, py1)
                            px2, py2 = min(w_c - 1, px2), min(h_c - 1, py2)
                            if px2 <= px1 or py2 <= py1:
                                continue
                            plate_crop = car_crop[py1:py2, px1:px2]

                            # STEP 4: OCR & Stabilization (The "orc.py" logic)
                            raw_text = self.recognize_and_clean(plate_crop)
                            if not raw_text:
                                continue
                            
                            # Prepare Payload
                            payload = {
                                "plateNumber": raw_text,
                                "vehicleType": v_type,
                                "locationId": "INTERSECTION_A1",
                                "timestamp": datetime.now().isoformat()
                            }
                            asyncio.create_task(self.send_data(payload))

            # STEP 5: Visual Feedback
            cv2.imshow('Traffic System v1.0', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break

        cap.release()
        cv2.destroyAllWindows()

    def recognize_and_clean(self, plate_img):
        """Perform OCR on a plate image and clean the result for backend ingestion.

        The method will call `preprocess_for_ocr` and then `easyocr.Reader.readtext`.
        If OCR fails or returns no text, an empty string is returned. The output is passed
        through `correct_plate_format` before being returned.

        Args:
            plate_img (numpy.ndarray): Cropped image of license plate region.
        Returns:
            str: Cleaned plate text (uppercase, alphanumeric) or empty string if not found.
        """
        if plate_img is None:
            return ""
        if hasattr(plate_img, "size") and getattr(plate_img, "size") == 0:
            return ""

        proc = self.preprocess_for_ocr(plate_img)
        try:
            results = self.reader.readtext(proc, detail=0, paragraph=False)
        except Exception as e:
            logger.exception("easyocr.readtext failed: %s", e)
            results = []

        if not results:
            return ""

        raw = "".join(results)
        return self.correct_plate_format(raw)

    async def send_data(self, payload: dict):
        """Send detection payload to backend asynchronously using httpx.

        If `httpx` is not available the method will log a warning and return without
        raising. Responses with status codes >= 400 are logged as warnings.

        Args:
            payload (dict): JSON-serializable detection data (plateNumber, vehicleType, etc.).
        """
        try:
            import httpx
        except Exception as e:
            logger.warning("httpx is not installed; cannot send data to backend: %s", e)
            return

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                endpoint = self.backend_url.rstrip('/') + '/api/detections'
                resp = await client.post(endpoint, json=payload)
                if resp.status_code >= 400:
                    logger.warning("Backend returned %s for payload %s", resp.status_code, payload)
        except Exception as e:
            logger.exception("Failed sending payload to backend: %s", e)
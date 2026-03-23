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
import os
import sys
from collections import OrderedDict, defaultdict, deque, Counter
from datetime import datetime
from signal_controller import SignalController
import state_store  # shared live state

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

    def __init__(self, vehicle_model_path, plate_model_path, backend_url, *, show_window: bool = True, log_plates: bool = True):
        """Initialize models and engines used by the pipeline.

        Args:
            vehicle_model_path (str): Path or model identifier for vehicle YOLO model.
            plate_model_path (str): Path or model identifier for license-plate YOLO model.
            backend_url (str): Base URL for backend service (e.g., 'http://host:8080').
        """
        # Prefer explicit override via env, then CUDA, then MPS (Apple), otherwise CPU
        override = os.getenv("AI_DEVICE", "").lower()
        self.device = None
        if override:
            if override == "cuda" and torch.cuda.is_available():
                self.device = "cuda"
            elif override == "mps" and getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                self.device = "mps"
            elif override == "cpu":
                self.device = "cpu"
            else:
                logger.warning("Requested AI_DEVICE=%s is not available; falling back to auto device.", override)

        if self.device is None:
            if torch.cuda.is_available():
                self.device = "cuda"
            elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cpu"
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

        # 2. OCR Engine
        # easyocr's Reader benefits mainly from CUDA; other backends fall back to CPU.
        ocr_use_gpu = torch.cuda.is_available()
        self.reader = easyocr.Reader(['en'], gpu=ocr_use_gpu, verbose=False)
        # Restrict OCR to license-plate-like characters for speed and stability
        self.ocr_allowlist = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        self.backend_url = backend_url
        self.show_window = show_window
        self.log_plates = log_plates
        self.window_name = os.getenv("WINDOW_NAME", "Traffic System v1.0")

        # 3. Tracking & History (from orc.py)
        self.tracker = OrderedDict()
        self.plate_history = defaultdict(lambda: deque(maxlen=15))
        self.next_id = 0
        self._httpx_client = None

        # 4. Smart Traffic Signal Controller
        # Default intersection layout (can be configured via environment or API later)
        default_lanes = {
            "North Lane": {"polygon": [[300, 100], [500, 100], [450, 300], [250, 300]], "light": "RED"},
            "East Lane": {"polygon": [[600, 200], [800, 200], [800, 400], [600, 400]], "light": "RED"},
            "South Lane": {"polygon": [[300, 600], [500, 600], [450, 400], [250, 400]], "light": "RED"},
            "West Lane": {"polygon": [[100, 200], [300, 200], [300, 400], [100, 400]], "light": "RED"}
        }
        self.signal_controller = SignalController(
            lanes=default_lanes,
            default_green_time=8,
            min_green_time=4,
            yellow_time=2
        )

    def _can_use_highgui(self) -> bool:
        """Return True if it's safe to call OpenCV HighGUI (imshow/namedWindow).

        In many Docker/Linux environments, calling HighGUI functions aborts the process
        (Qt plugin / X11 not available). We avoid calling HighGUI unless we believe a
        display is available.
        """
        if not self.show_window:
            return False
        if sys.platform.startswith("linux"):
            # In Linux, HighGUI typically requires a display server.
            return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        # macOS/Windows don't use DISPLAY in the same way.
        return True

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

    def _update_plate_history(self, key, plate_text: str) -> str:
        """Update and smooth plate text history for a spatial track.

        Args:
            key: Hashable track key (e.g., quantized plate position).
            plate_text (str): Newly read plate text.
        Returns:
            str: Stabilized plate text once it has been consistently observed;
                 empty string otherwise.
        """
        if not plate_text:
            return ""

        history = self.plate_history[key]
        history.append(plate_text)

        # Require a short warm‑up before trusting the value
        if len(history) < 4:
            return ""

        counts = Counter(history)
        candidate, count = counts.most_common(1)[0]

        # Require both a minimum count and majority agreement
        if count >= max(3, len(history) // 2 + 1):
            return candidate
        return ""

    async def process_stream(self, video_source):
        """Read frames from a video source and process detections in a loop.

        The method blocks (asynchronous-friendly) while the video is open. It detects
        vehicles, crops vehicle ROIs, runs a second YOLO pass for plates, runs OCR,
        and sends detection payloads to the backend asynchronously.

        Args:
            video_source (int | str): OpenCV video source (0 for webcam, or filepath/URL).
        """
        cap = cv2.VideoCapture(video_source)

        window_ok = False
        if self._can_use_highgui():
            # Important: in some environments a HighGUI call can abort the process.
            # We only attempt it when a display looks available.
            cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
            window_ok = True
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            # STEP 1: Detect Vehicles
            v_results = self.vehicle_model(frame, conf=0.5, verbose=False, device=self.device)
            
            vehicle_centers = []
            
            for res in v_results:
                for box in res.boxes:
                    vx1, vy1, vx2, vy2 = map(int, box.xyxy[0])
                    v_type = res.names[int(box.cls[0])]
                    
                    center_x = (vx1 + vx2) // 2
                    center_y = (vy1 + vy2) // 2
                    vehicle_centers.append((center_x, center_y))

                    # Draw vehicle bounding box and label
                    cv2.rectangle(frame, (vx1, vy1), (vx2, vy2), (0, 255, 0), 2)
                    cv2.putText(frame, v_type, (vx1, vy1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

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
                            abs_px1, abs_py1 = vx1 + px1, vy1 + py1
                            abs_px2, abs_py2 = vx1 + px2, vy1 + py2

                            if px2 <= px1 or py2 <= py1:
                                continue

                            # Skip extremely small plate crops (typically just noise)
                            if (px2 - px1) * (py2 - py1) < 400:
                                continue

                            plate_crop = car_crop[py1:py2, px1:px2]

                            # STEP 4: OCR & Stabilization
                            raw_text = self.recognize_and_clean(plate_crop)
                            track_key = (abs_px1 // 50, abs_py1 // 50)
                            stable_text = self._update_plate_history(track_key, raw_text)

                            # Draw plate bounding box and the most stable text we have
                            display_text = stable_text or raw_text
                            cv2.rectangle(frame, (abs_px1, abs_py1), (abs_px2, abs_py2), (255, 0, 255), 2)
                            if display_text:
                                cv2.putText(
                                    frame,
                                    display_text,
                                    (abs_px1, abs_py1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    0.5,
                                    (255, 0, 255),
                                    2,
                                )

                            # Only send when OCR is stable to avoid flicker and duplicates
                            if not stable_text:
                                continue

                            # Avoid resending the same stable plate for this track
                            last_sent = self.tracker.get(track_key)
                            if last_sent == stable_text:
                                continue
                            self.tracker[track_key] = stable_text
                            if self.log_plates:
                                logger.info("Plate detected: %s", stable_text)

                            # Push to shared live state
                            state_store.state.add_plate(
                                plate=stable_text,
                                vehicle_type=v_type,
                                location_id="INTERSECTION_A1",
                                is_valid=len(stable_text) >= 6,
                            )

                            # Prepare Payload
                            payload = {
                                "plateNumber": stable_text,
                                "vehicleType": v_type,
                                "locationId": "INTERSECTION_A1",
                                "timestamp": datetime.now().isoformat()
                            }
                            asyncio.create_task(self.send_data(payload))

            # STEP 4.5: Update vehicle count in shared live state
            vehicle_count_in_frame = sum(
                len(res.boxes) for res in v_results
            )
            state_store.state.update_vehicle_count(vehicle_count_in_frame)

            # STEP 5: Update Signal Controller
            self.signal_controller.update_counts(vehicle_centers)
            self.signal_controller.tick()
            frame = self.signal_controller.draw(frame)

            # STEP 5: Visual Feedback
            if window_ok:
                cv2.imshow(self.window_name, frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

        cap.release()
        if window_ok:
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
            results = self.reader.readtext(
                proc,
                detail=0,
                paragraph=False,
                allowlist=self.ocr_allowlist,
            )
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
            if self._httpx_client is None:
                self._httpx_client = httpx.AsyncClient(timeout=10.0)

            base = self.backend_url.rstrip('/')
            endpoint = base if base.endswith('/api/detections') else (base + '/api/detections')
            resp = await self._httpx_client.post(endpoint, json=payload)
            if resp.status_code >= 400:
                logger.warning("Backend returned %s for payload %s", resp.status_code, payload)
        except Exception as e:
            logger.exception("Failed sending payload to backend: %s", e)
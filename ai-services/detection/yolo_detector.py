"""
yolo_detector.py — YOLOv8 detection wrapper.

Provides a clean interface over ultralytics YOLO with structured output.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

logger = logging.getLogger("traffic.yolo_detector")


@dataclass
class Detection:
    """A single detected object."""
    bbox: tuple[int, int, int, int]  # (x1, y1, x2, y2)
    class_name: str
    class_id: int
    confidence: float
    center: tuple[int, int] = field(init=False)

    def __post_init__(self):
        x1, y1, x2, y2 = self.bbox
        self.center = ((x1 + x2) // 2, (y1 + y2) // 2)

    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]

    @property
    def area(self) -> int:
        return self.width * self.height


# Vehicle classes from COCO dataset that we care about
VEHICLE_CLASSES = {
    "car", "truck", "bus", "motorcycle", "bicycle",
    "item", # Custom model generic class
    # Extra classes that might appear
    "train", "boat",
}

EMERGENCY_CLASSES = {"fire truck", "ambulance"}


class YOLODetector:
    """Wraps ultralytics YOLO model with structured output.

    Features:
    - Auto device selection (CUDA → MPS → CPU)
    - Returns list of Detection dataclass instances
    - Filters by confidence and class
    - Lazy model loading
    """

    def __init__(
        self,
        model_path: str,
        device: str = "cpu",
        confidence: float = 0.5,
        vehicle_only: bool = True,
    ):
        self.model_path = model_path
        self.device = device
        self.confidence = confidence
        self.vehicle_only = vehicle_only
        self._model = None
        self._class_names: dict = {}

    def _ensure_loaded(self) -> None:
        """Lazy-load the YOLO model on first use."""
        if self._model is not None:
            return

        try:
            from ultralytics import YOLO
        except ImportError:
            raise ImportError("ultralytics is required. Install: pip install ultralytics")

        logger.info("Loading YOLO model: %s (device=%s)", self.model_path, self.device)

        if not os.path.exists(self.model_path):
            logger.warning(
                "Model file not found at %s — ultralytics will attempt download",
                self.model_path,
            )

        self._model = YOLO(self.model_path)
        try:
            self._model.to(self.device)
        except Exception:
            logger.debug("Could not move model to %s, using default device", self.device)

        # Cache class names
        if hasattr(self._model, "names"):
            self._class_names = self._model.names
        logger.info("YOLO model loaded — %d classes available", len(self._class_names))

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Run detection on a single frame.

        Args:
            frame: BGR numpy array (from OpenCV)

        Returns:
            List of Detection objects, filtered by confidence and optionally vehicle-only.
        """
        self._ensure_loaded()

        results = self._model(frame, conf=self.confidence, verbose=False, device=self.device)
        detections: List[Detection] = []

        for res in results:
            for box in res.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                class_id = int(box.cls[0])
                class_name = res.names.get(class_id, f"class_{class_id}")
                conf = float(box.conf[0])

                # Filter to vehicle classes if enabled
                if self.vehicle_only and class_name.lower() not in VEHICLE_CLASSES:
                    continue

                detections.append(Detection(
                    bbox=(x1, y1, x2, y2),
                    class_name=class_name,
                    class_id=class_id,
                    confidence=conf,
                ))

        return detections

    def detect_in_roi(
        self,
        frame: np.ndarray,
        roi: tuple[int, int, int, int],
        confidence: Optional[float] = None,
    ) -> List[Detection]:
        """Run detection within a region of interest.

        Coordinates in returned Detections are mapped back to full frame space.
        """
        x1, y1, x2, y2 = roi
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return []

        # Temporarily override settings
        old_vehicle_only = self.vehicle_only
        old_conf = self.confidence
        self.vehicle_only = False  # In ROI mode, detect everything
        if confidence is not None:
            self.confidence = confidence

        detections = self.detect(crop)

        # Restore
        self.vehicle_only = old_vehicle_only
        self.confidence = old_conf

        # Offset coordinates back to full frame
        offset_detections = []
        for d in detections:
            bx1, by1, bx2, by2 = d.bbox
            offset_detections.append(Detection(
                bbox=(bx1 + x1, by1 + y1, bx2 + x1, by2 + y1),
                class_name=d.class_name,
                class_id=d.class_id,
                confidence=d.confidence,
            ))

        return offset_detections

    def is_emergency_vehicle(self, detection: Detection) -> bool:
        """Check if a detection is an emergency vehicle."""
        return detection.class_name.lower() in EMERGENCY_CLASSES

    @property
    def class_names(self) -> dict:
        self._ensure_loaded()
        return self._class_names

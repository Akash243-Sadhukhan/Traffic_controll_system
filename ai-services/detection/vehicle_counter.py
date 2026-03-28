"""
vehicle_counter.py — Zone-based vehicle counting with per-class breakdown.

Assigns detected vehicles to intersection lanes/zones using polygon containment,
tracks counts over time windows, and provides aggregated statistics.
"""

import time
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from detection.yolo_detector import Detection

logger = logging.getLogger("traffic.vehicle_counter")


@dataclass
class ZoneConfig:
    """Configuration for a counting zone / lane."""
    name: str
    polygon: List[Tuple[int, int]]  # [(x, y), ...]
    direction: str = "unknown"  # "north", "south", "east", "west"

    @property
    def np_polygon(self) -> np.ndarray:
        return np.array(self.polygon, np.int32)


@dataclass
class ZoneCount:
    """Snapshot of counts within a single zone."""
    zone_name: str
    total: int = 0
    by_class: Dict[str, int] = field(default_factory=dict)
    weighted_total: float = 0.0  # bus/truck count more

    @property
    def is_empty(self) -> bool:
        return self.total == 0


# Vehicle class weights for density calculation
CLASS_WEIGHTS = {
    "car": 1.0,
    "truck": 2.0,
    "bus": 2.5,
    "motorcycle": 0.5,
    "bicycle": 0.3,
}


class VehicleCounter:
    """Polygon-based zone counting for intersection lanes.

    Assigns each detected vehicle to exactly one zone based on its center point,
    tracks counts per class, and maintains a rolling time-window history.
    """

    def __init__(
        self,
        zones: Optional[List[ZoneConfig]] = None,
        history_window: int = 30,  # seconds of history to keep
    ):
        self.zones = zones or self._default_zones()
        self.history_window = history_window

        # Rolling history: deque of (timestamp, zone_counts_dict)
        self._history: deque = deque(maxlen=history_window * 10)  # ~10 FPS
        self._current_counts: Dict[str, ZoneCount] = {}
        self._total_vehicles = 0
        self._last_update = time.time()

    @staticmethod
    def _default_zones() -> List[ZoneConfig]:
        """Default 4-way intersection zones (640x480 frame assumed)."""
        return [
            ZoneConfig(
                name="north",
                polygon=[(220, 0), (420, 0), (370, 200), (270, 200)],
                direction="north",
            ),
            ZoneConfig(
                name="south",
                polygon=[(270, 280), (370, 280), (420, 480), (220, 480)],
                direction="south",
            ),
            ZoneConfig(
                name="east",
                polygon=[(420, 140), (640, 140), (640, 340), (420, 340)],
                direction="east",
            ),
            ZoneConfig(
                name="west",
                polygon=[(0, 140), (220, 140), (220, 340), (0, 340)],
                direction="west",
            ),
        ]

    def update(self, detections: List[Detection]) -> Dict[str, ZoneCount]:
        """Count vehicles per zone from a list of detections.

        Each vehicle is assigned to exactly one zone (first match).
        Returns per-zone counts including class breakdown.
        """
        counts: Dict[str, ZoneCount] = {
            zone.name: ZoneCount(zone_name=zone.name) for zone in self.zones
        }

        for det in detections:
            cx, cy = det.center
            for zone in self.zones:
                polygon = zone.np_polygon
                if cv2.pointPolygonTest(polygon, (float(cx), float(cy)), False) >= 0:
                    zc = counts[zone.name]
                    zc.total += 1
                    zc.by_class[det.class_name] = zc.by_class.get(det.class_name, 0) + 1
                    weight = CLASS_WEIGHTS.get(det.class_name.lower(), 1.0)
                    zc.weighted_total += weight
                    break  # assign to first matching zone

        self._current_counts = counts
        self._total_vehicles = sum(zc.total for zc in counts.values())
        self._last_update = time.time()

        # Record in history
        self._history.append((
            self._last_update,
            {name: zc.total for name, zc in counts.items()},
        ))

        return counts

    @property
    def current_counts(self) -> Dict[str, ZoneCount]:
        return self._current_counts

    @property
    def total_vehicles(self) -> int:
        return self._total_vehicles

    def get_arm_counts(self) -> Dict[str, int]:
        """Get simple {zone_name: count} dict for API consumption."""
        return {name: zc.total for name, zc in self._current_counts.items()}

    def get_weighted_counts(self) -> Dict[str, float]:
        """Get {zone_name: weighted_count} for density analysis."""
        return {name: zc.weighted_total for name, zc in self._current_counts.items()}

    def get_trend(self, zone_name: str, window_seconds: float = 10.0) -> str:
        """Determine if vehicle count in a zone is increasing, stable, or decreasing."""
        now = time.time()
        cutoff = now - window_seconds
        recent = [(t, c.get(zone_name, 0)) for t, c in self._history if t >= cutoff]

        if len(recent) < 4:
            return "stable"

        half = len(recent) // 2
        first_half_avg = sum(c for _, c in recent[:half]) / half
        second_half_avg = sum(c for _, c in recent[half:]) / (len(recent) - half)
        diff = second_half_avg - first_half_avg

        if diff > 1.5:
            return "increasing"
        elif diff < -1.5:
            return "decreasing"
        return "stable"

    def draw_zones(self, frame: np.ndarray, alpha: float = 0.25) -> np.ndarray:
        """Draw counting zones as semi-transparent overlays on the frame."""
        overlay = frame.copy()
        colors = {
            "north": (255, 100, 100),  # blue-ish
            "south": (100, 255, 100),  # green-ish
            "east": (100, 100, 255),   # red-ish
            "west": (255, 255, 100),   # cyan-ish
        }

        for zone in self.zones:
            color = colors.get(zone.name, (200, 200, 200))
            pts = zone.np_polygon.reshape((-1, 1, 2))
            cv2.fillPoly(overlay, [pts], color)

            # Zone label with count
            zc = self._current_counts.get(zone.name)
            count = zc.total if zc else 0
            label_pos = zone.polygon[0]
            cv2.putText(
                frame, f"{zone.name.upper()}: {count}",
                (label_pos[0], max(25, label_pos[1] - 10)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2,
            )

        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
        return frame

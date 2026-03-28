"""
opencv_window.py — Annotated frame rendering for local display.

Draws bounding boxes, zone overlays, signal indicators, and counters
on the video frame for debugging and demonstration.
"""

import sys
import os
import logging
from typing import Dict, List, Optional

import cv2
import numpy as np

from detection.yolo_detector import Detection

logger = logging.getLogger("traffic.opencv_window")

# Color palette (BGR)
COLORS = {
    "car": (0, 255, 100),
    "truck": (255, 150, 0),
    "bus": (0, 150, 255),
    "motorcycle": (255, 255, 0),
    "bicycle": (255, 0, 255),
    "emergency": (0, 0, 255),
    "item": (0, 255, 0), # Custom model highlight
    "default": (0, 255, 0),
}

SIGNAL_COLORS = {
    "RED": (0, 0, 220),
    "YELLOW": (0, 220, 220),
    "GREEN": (0, 220, 0),
}


class OpenCVDisplay:
    """Manages the OpenCV display window for annotated video feed.

    Features:
    - Vehicle bounding boxes with class labels
    - Zone overlays with vehicle counts
    - Signal state indicators
    - FPS counter
    - Emergency alert banner
    """

    def __init__(self, window_name: str = "🚦 Traffic AI — Live Feed", enabled: bool = True):
        self.window_name = window_name
        self.enabled = enabled and self._can_display()
        self._window_created = False

    @staticmethod
    def _can_display() -> bool:
        """Check if we can create GUI windows."""
        if sys.platform.startswith("linux"):
            return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        return True  # macOS / Windows

    def _ensure_window(self) -> None:
        if not self._window_created and self.enabled:
            try:
                cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(self.window_name, 960, 720)
                self._window_created = True
            except Exception as e:
                logger.warning("Cannot create window: %s", e)
                self.enabled = False

    def render(
        self,
        frame: np.ndarray,
        detections: List[Detection],
        signal_states: Optional[Dict[str, str]] = None,
        zone_counts: Optional[Dict[str, int]] = None,
        fps: float = 0.0,
        alert_text: str = "",
    ) -> bool:
        """Render annotated frame and cache JPEG for web stream. Returns False if window was closed."""
        self._ensure_window()
        annotated = frame.copy()

        # 1. Draw bounding boxes
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            color = COLORS.get(det.class_name.lower(), COLORS["default"])
            
            # Use thickness 4 for prominent border
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 4)

            label = f"{det.class_name} {det.confidence:.0%}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            # Label background box for emphasis
            cv2.rectangle(annotated, (x1-2, y1 - th - 12), (x1 + tw + 6, y1), color, -1)
            cv2.putText(annotated, label, (x1 + 2, y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # 2. Draw signal state indicators (top-right corner)
        if signal_states:
            self._draw_signals(annotated, signal_states)

        # 3. Draw zone counts (bottom panel)
        if zone_counts:
            self._draw_zone_counts(annotated, zone_counts)

        # 4. FPS counter (top-left)
        if fps > 0:
            cv2.putText(annotated, f"FPS: {fps:.1f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        # 5. Alert banner (top, full width)
        if alert_text:
            self._draw_alert(annotated, alert_text)

        # 6. Encode for Web Stream (MJPEG)
        import threading
        if not hasattr(self, "_lock"):
            self._lock = threading.Lock()
            self._latest_jpeg = b""

        _, buffer = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
        with self._lock:
            self._latest_jpeg = buffer.tobytes()

        # 7. Local display (If supported/enabled)
        if self.enabled:
            cv2.imshow(self.window_name, annotated)
            key = cv2.waitKey(1) & 0xFF
            return key != ord('q')
        
        return True

    def get_latest_frame(self) -> bytes:
        """Return the latest annotated frame as JPEG bytes."""
        if hasattr(self, "_lock"):
            with self._lock:
                return self._latest_jpeg
        return b""

    def _draw_signals(self, frame: np.ndarray, states: Dict[str, str]) -> None:
        """Draw traffic light indicators in the top-right corner."""
        h, w = frame.shape[:2]
        x_start = w - 180
        y = 20

        cv2.putText(frame, "SIGNALS", (x_start, y),
                     cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        y += 25

        for lane, state in states.items():
            color = SIGNAL_COLORS.get(state, (128, 128, 128))
            cv2.circle(frame, (x_start + 10, y), 8, color, -1)
            cv2.circle(frame, (x_start + 10, y), 8, (255, 255, 255), 1)
            cv2.putText(frame, f"{lane}: {state}", (x_start + 25, y + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
            y += 25

    def _draw_zone_counts(self, frame: np.ndarray, counts: Dict[str, int]) -> None:
        """Draw zone count panel at the bottom."""
        h, w = frame.shape[:2]
        panel_h = 40
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, h - panel_h), (w, h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

        x = 20
        for zone, count in counts.items():
            bar_w = min(count * 8, 80)
            color = (0, 255, 0) if count < 5 else (0, 200, 255) if count < 10 else (0, 0, 255)
            cv2.putText(frame, f"{zone.upper()}: {count}", (x, h - 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
            cv2.rectangle(frame, (x + 80, h - 25), (x + 80 + bar_w, h - 12), color, -1)
            x += 180

    def _draw_alert(self, frame: np.ndarray, text: str) -> None:
        """Draw a red alert banner at the top."""
        h, w = frame.shape[:2]
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 45), (0, 0, 180), -1)
        cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)
        cv2.putText(frame, f"⚠ {text}", (15, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    def close(self) -> None:
        """Clean up the display window."""
        if self._window_created:
            cv2.destroyAllWindows()
            self._window_created = False

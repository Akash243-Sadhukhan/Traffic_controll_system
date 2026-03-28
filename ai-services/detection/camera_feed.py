"""
camera_feed.py — Camera feed manager supporting webcam, video file, and RTSP.

Provides a unified frame generator interface regardless of source type.
"""

import cv2
import logging
import time
from enum import Enum
from dataclasses import dataclass
from typing import Generator, Tuple, Optional, Any

import numpy as np

logger = logging.getLogger("traffic.camera_feed")


class SourceType(str, Enum):
    WEBCAM = "webcam"
    VIDEO = "video"
    RTSP = "rtsp"
    SIMULATION = "simulation"


@dataclass
class FrameMeta:
    """Metadata attached to each frame."""
    frame_number: int
    timestamp: float
    source_type: SourceType
    fps: float = 0.0
    width: int = 0
    height: int = 0


class CameraFeed:
    """Unified camera feed manager.

    Supports webcam (by index), video file (by path), RTSP stream (by URL),
    and a simulation mode that yields None frames for SUMO integration.
    """

    def __init__(
        self,
        source: str | int = 0,
        target_fps: float = 30.0,
        reconnect_delay: float = 3.0,
        max_reconnects: int = 5,
    ):
        self.source = source
        self.target_fps = target_fps
        self.reconnect_delay = reconnect_delay
        self.max_reconnects = max_reconnects
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame_count = 0
        self._source_type = self._detect_source_type()

    def _detect_source_type(self) -> SourceType:
        if isinstance(self.source, int):
            return SourceType.WEBCAM
        s = str(self.source).lower()
        if s in ("sim", "simulation", "sumo"):
            return SourceType.SIMULATION
        if s.startswith("rtsp://") or s.startswith("http://") or s.startswith("https://"):
            return SourceType.RTSP
        return SourceType.VIDEO

    @property
    def source_type(self) -> SourceType:
        return self._source_type

    def open(self) -> bool:
        """Open the video source. Returns True on success."""
        if self._source_type == SourceType.SIMULATION:
            logger.info("Camera feed: SIMULATION mode (no actual video source)")
            return True

        self._cap = cv2.VideoCapture(self.source)
        if not self._cap.isOpened():
            logger.error("Failed to open video source: %s", self.source)
            return False

        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = self._cap.get(cv2.CAP_PROP_FPS) or self.target_fps
        logger.info("Camera feed opened: %s (%dx%d @ %.1f FPS)", self._source_type.value, w, h, fps)
        return True

    def close(self) -> None:
        """Release the video source."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        logger.info("Camera feed closed (total frames: %d)", self._frame_count)

    def frames(self) -> Generator[Tuple[Optional[np.ndarray], FrameMeta], None, None]:
        """Yield (frame, metadata) tuples.

        For SIMULATION mode, yields (None, meta).
        For real sources, yields (BGR numpy array, meta).
        Respects target_fps throttling.
        """
        if self._source_type == SourceType.SIMULATION:
            yield from self._simulation_frames()
            return

        if self._cap is None or not self._cap.isOpened():
            if not self.open():
                return

        min_interval = 1.0 / self.target_fps if self.target_fps > 0 else 0
        reconnect_count = 0

        while True:
            t_start = time.monotonic()
            ret, frame = self._cap.read()

            if not ret:
                if self._source_type == SourceType.RTSP and reconnect_count < self.max_reconnects:
                    reconnect_count += 1
                    logger.warning(
                        "RTSP stream lost — reconnecting (%d/%d) in %.1fs...",
                        reconnect_count, self.max_reconnects, self.reconnect_delay,
                    )
                    time.sleep(self.reconnect_delay)
                    self._cap.release()
                    self._cap = cv2.VideoCapture(self.source)
                    continue
                break

            reconnect_count = 0
            self._frame_count += 1
            h, w = frame.shape[:2]

            meta = FrameMeta(
                frame_number=self._frame_count,
                timestamp=time.time(),
                source_type=self._source_type,
                fps=1.0 / max(time.monotonic() - t_start, 0.001),
                width=w,
                height=h,
            )
            yield frame, meta

            # FPS throttling
            elapsed = time.monotonic() - t_start
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)

        self.close()

    def _simulation_frames(self) -> Generator[Tuple[None, FrameMeta], None, None]:
        """Yield synthetic (None) frames for simulation mode at target FPS."""
        interval = 1.0 / self.target_fps if self.target_fps > 0 else 1.0
        while True:
            self._frame_count += 1
            meta = FrameMeta(
                frame_number=self._frame_count,
                timestamp=time.time(),
                source_type=SourceType.SIMULATION,
                fps=self.target_fps,
            )
            yield None, meta
            time.sleep(interval)

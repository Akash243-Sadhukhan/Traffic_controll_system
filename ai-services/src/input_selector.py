# ai-services/src/input_selector.py
"""
input_selector.py — AI input source abstraction.

Supports three modes:
  SIMULATION : frame-less mode; data arrives via /ai/vehicle-counts webhook.
  CAMERA     : live webcam via cv2.VideoCapture(camera_index).
  VIDEO      : pre-recorded file via cv2.VideoCapture(video_path), loops for demo.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Generator

logger = logging.getLogger("traffic.input_selector")

# ai-services root — two levels up from this file
AI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class InputSource(str, Enum):
    SIMULATION = "simulation"
    CAMERA     = "camera"
    VIDEO      = "video"


@dataclass
class InputConfig:
    source:       InputSource = InputSource.SIMULATION
    camera_index: int         = 0
    video_path:   str         = ""


class InputSelector:
    """Manages the active video / data source for the AI pipeline."""

    def __init__(self, config: InputConfig) -> None:
        self._config      = config
        self._frame_count: int  = 0
        self._active:      bool = False   # True only while generator is running

    # ── Public API ────────────────────────────────────────────────────────────

    def get_frame_generator(self) -> Generator:
        """
        Returns a generator yielding (frame, metadata) tuples.

        SIMULATION mode: immediately stops (empty generator) — data arrives via webhook.
        CAMERA mode:     yields BGR frames from webcam, retries on failure.
        VIDEO mode:      yields BGR frames from file, loops at end.
        """
        if self._config.source == InputSource.SIMULATION:
            return self._simulation_gen()
        elif self._config.source == InputSource.CAMERA:
            return self._camera_gen()
        elif self._config.source == InputSource.VIDEO:
            return self._video_gen()
        raise ValueError(f"Unknown InputSource: {self._config.source}")

    def get_source_info(self) -> dict:
        """Returns metadata for the /ai/source/status endpoint."""
        return {
            "source":       self._config.source.value,
            "camera_index": self._config.camera_index
                            if self._config.source == InputSource.CAMERA else None,
            "video_path":   self._config.video_path
                            if self._config.source == InputSource.VIDEO else None,
            "active":       self._active,
            "frame_count":  self._frame_count,
        }

    def update_config(self, config: InputConfig) -> None:
        self._config      = config
        self._frame_count = 0
        self._active      = False

    # ── Generators ────────────────────────────────────────────────────────────

    def _simulation_gen(self) -> Generator:
        """SIMULATION: empty generator — webhook data drives state_store directly."""
        logger.info("InputSelector: SIMULATION mode — frames not needed (webhook-driven).")
        self._active = False
        return
        yield  # makes this a generator function that immediately returns

    def _camera_gen(self) -> Generator:
        import cv2
        self._active = True
        cap = None
        try:
            while self._active:
                if cap is None or not cap.isOpened():
                    logger.info("Opening camera index %d", self._config.camera_index)
                    cap = cv2.VideoCapture(self._config.camera_index)
                    if not cap.isOpened():
                        logger.error(
                            "Camera %d unavailable — retrying in 2s",
                            self._config.camera_index,
                        )
                        time.sleep(2.0)
                        continue

                ret, frame = cap.read()
                if not ret:
                    logger.warning("Camera read failed — reopening")
                    cap.release()
                    cap = None
                    time.sleep(1.0)
                    continue

                self._frame_count += 1
                yield frame, {"source": "camera", "frame": self._frame_count}
        finally:
            self._active = False
            if cap and cap.isOpened():
                cap.release()

    def _video_gen(self) -> Generator:
        import cv2

        path = self._config.video_path

        # Resolve relative paths against ai-services root
        if not os.path.isabs(path):
            full_path = os.path.join(AI_ROOT, path)
        else:
            full_path = path

        if not os.path.exists(full_path):
            data_dir = os.path.join(AI_ROOT, "Data")
            files_in_data = os.listdir(data_dir) if os.path.isdir(data_dir) else []
            raise FileNotFoundError(
                f"Video not found: {path}\n"
                f"Resolved to: {full_path}\n"
                f"Files in Data/: {files_in_data}"
            )

        logger.info("Opening video: %s", full_path)
        cap = cv2.VideoCapture(full_path)
        if not cap.isOpened():
            raise FileNotFoundError(f"OpenCV could not open: {full_path}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        logger.info("Video loaded — total frames: %d", total_frames)

        self._active = True
        try:
            while self._active:
                ret, frame = cap.read()
                if not ret:
                    # Loop the video for demo purposes
                    logger.info("Video ended — looping from beginning")
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

                self._frame_count += 1
                yield frame, {
                    "source": "video",
                    "path":   full_path,
                    "frame":  self._frame_count,
                    "total":  total_frames,
                }
        finally:
            self._active = False
            cap.release()
            logger.info("Video capture released.")

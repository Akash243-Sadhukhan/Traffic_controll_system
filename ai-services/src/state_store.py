"""
state_store.py
Shared in-memory state for the Traffic AI Service.

A single AppState instance is imported by processor.py, vehicle_count_routes.py,
and main.py so they all read/write the same live data without a database.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any, Deque, Dict, Optional


@dataclass
class AppState:
    """Central state bag: vehicle count, ANPR plates, arm queues."""

    # Total vehicles visible in the current frame (updated per-frame by processor)
    vehicle_count: int = 0

    # Last N plate detections — each item is a dict:
    # { plate, vehicle_type, location_id, timestamp, is_valid }
    plates: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=50))

    # Per-arm queue lengths from SUMO simulation (or sensor later)
    arm_counts: Dict[str, int] = field(default_factory=lambda: {
        "north": 0, "south": 0, "east": 0, "west": 0
    })

    # ISO timestamp of last update
    last_updated: str = ""

    # Thread-safety for concurrent writes from the video thread + API handlers
    _lock: Lock = field(default_factory=Lock, repr=False, compare=False)

    def update_vehicle_count(self, count: int) -> None:
        with self._lock:
            self.vehicle_count = count
            self.last_updated = datetime.now().isoformat()

    def add_plate(self, plate: str, vehicle_type: str,
                  location_id: str = "INTERSECTION_A1",
                  is_valid: bool = False) -> None:
        with self._lock:
            self.plates.appendleft({
                "plate": plate,
                "vehicle_type": vehicle_type,
                "location_id": location_id,
                "timestamp": datetime.now().isoformat(),
                "is_valid": is_valid,
            })
            self.last_updated = datetime.now().isoformat()

    def update_arm_counts(self, arm_counts: Dict[str, int],
                          total: Optional[int] = None) -> None:
        with self._lock:
            self.arm_counts.update(arm_counts)
            if total is not None:
                self.vehicle_count = total
            self.last_updated = datetime.now().isoformat()

    def snapshot(self) -> Dict[str, Any]:
        """Return a JSON-safe snapshot of current state."""
        with self._lock:
            return {
                "vehicle_count": self.vehicle_count,
                "plates": list(self.plates),
                "arm_counts": dict(self.arm_counts),
                "last_updated": self.last_updated,
            }


# Singleton — import this everywhere
state = AppState()

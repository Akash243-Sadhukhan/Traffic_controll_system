"""
priority_override.py — Emergency vehicle preemption logic.

Detects emergency vehicles (from YOLO class or manual trigger) and
forces green on the approach lane with cooldown management.
"""

import time
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

logger = logging.getLogger("traffic.priority_override")


@dataclass
class OverrideEvent:
    """Record of a priority override."""
    timestamp: float
    lane: str
    vehicle_type: str  # "ambulance", "fire_truck", "manual"
    duration: float = 0.0
    resolved: bool = False
    resolved_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "lane": self.lane,
            "vehicle_type": self.vehicle_type,
            "duration": round(self.duration, 1),
            "resolved": self.resolved,
            "resolved_at": self.resolved_at,
        }


class PriorityOverride:
    """Manages emergency vehicle preemption for traffic signals.

    Features:
    - Tracks active override state
    - Cooldown timer after override ends
    - Queue of pending overrides (multiple emergencies)
    - Integration with PhaseScheduler.force_green()
    """

    def __init__(
        self,
        cooldown_seconds: float = 10.0,
        max_override_duration: float = 60.0,
    ):
        self.cooldown_seconds = cooldown_seconds
        self.max_override_duration = max_override_duration

        self._active_override: Optional[OverrideEvent] = None
        self._pending: Deque[OverrideEvent] = deque(maxlen=10)
        self._history: List[OverrideEvent] = []
        self._cooldown_until: float = 0.0
        self._is_in_cooldown: bool = False

    @property
    def is_active(self) -> bool:
        """Is there an active emergency override?"""
        return self._active_override is not None and not self._active_override.resolved

    @property
    def is_in_cooldown(self) -> bool:
        """Is the system in post-override cooldown?"""
        if self._cooldown_until > 0 and time.time() < self._cooldown_until:
            return True
        self._is_in_cooldown = False
        return False

    @property
    def active_override(self) -> Optional[OverrideEvent]:
        return self._active_override

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def trigger(self, lane: str, vehicle_type: str = "emergency") -> OverrideEvent:
        """Trigger a priority override for the given lane.

        If another override is already active, this one is queued.
        """
        event = OverrideEvent(
            timestamp=time.time(),
            lane=lane,
            vehicle_type=vehicle_type,
        )

        if self.is_active:
            # Queue it
            self._pending.append(event)
            logger.info(
                "Override queued for %s (%s) — %d pending",
                lane, vehicle_type, len(self._pending),
            )
        else:
            self._activate(event)

        return event

    def _activate(self, event: OverrideEvent) -> None:
        """Activate an override event."""
        self._active_override = event
        self._is_in_cooldown = False
        logger.warning(
            "🚨 PRIORITY OVERRIDE ACTIVATED — lane: %s, type: %s",
            event.lane, event.vehicle_type,
        )

    def resolve(self) -> Optional[OverrideEvent]:
        """Resolve the current active override and start cooldown.

        Automatically activates the next pending override if any.
        Returns the resolved event.
        """
        if not self.is_active:
            return None

        event = self._active_override
        now = time.time()
        event.resolved = True
        event.resolved_at = now
        event.duration = now - event.timestamp
        self._history.append(event)
        self._active_override = None

        logger.info(
            "Override resolved — lane: %s, duration: %.1fs",
            event.lane, event.duration,
        )

        # Check for pending overrides
        if self._pending:
            next_event = self._pending.popleft()
            self._activate(next_event)
        else:
            # Start cooldown
            self._cooldown_until = now + self.cooldown_seconds
            self._is_in_cooldown = True
            logger.info("Cooldown started — %.1fs", self.cooldown_seconds)

        return event

    def tick(self) -> Optional[str]:
        """Check override timeouts. Returns action string or None.

        Should be called each tick to enforce max override duration.
        """
        if not self.is_active:
            return None

        elapsed = time.time() - self._active_override.timestamp
        if elapsed >= self.max_override_duration:
            logger.warning(
                "Override timed out after %.1fs — auto-resolving", elapsed
            )
            self.resolve()
            return "timeout_resolved"

        return None

    def check_emergency_detections(
        self,
        detections: list,
        lane_assignment: Dict[str, str],
    ) -> Optional[OverrideEvent]:
        """Check detections for emergency vehicles and trigger override if found.

        Args:
            detections: List of Detection objects
            lane_assignment: {detection_id: lane_name} mapping

        Returns:
            OverrideEvent if triggered, None otherwise.
        """
        for det in detections:
            class_name = getattr(det, "class_name", "").lower()
            if class_name in ("ambulance", "fire truck", "emergency"):
                # Find which lane this emergency vehicle is in
                det_id = id(det)
                lane = lane_assignment.get(det_id, "")
                if lane:
                    return self.trigger(lane, vehicle_type=class_name)
        return None

    def get_status(self) -> dict:
        """Get current override status for API/WebSocket."""
        return {
            "is_active": self.is_active,
            "is_in_cooldown": self.is_in_cooldown,
            "active_override": self._active_override.to_dict() if self._active_override else None,
            "pending_count": self.pending_count,
            "history_count": len(self._history),
        }

    @property
    def history(self) -> List[OverrideEvent]:
        return self._history

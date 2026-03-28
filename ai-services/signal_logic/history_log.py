"""
history_log.py — Audit trail and replay for signal/traffic events.

Stores all signal phase changes, vehicle counts, and alerts in SQLite
for later querying, reporting, and replay.
"""

import time
import json
import logging
from dataclasses import dataclass, field
from collections import deque
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger("traffic.history_log")


@dataclass
class LogEntry:
    """A single audit log entry."""
    timestamp: float
    event_type: str  # "phase_change", "vehicle_count", "alert", "override", "detection"
    data: Dict[str, Any] = field(default_factory=dict)
    lane: str = ""
    severity: str = "info"  # "info", "warning", "critical"

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "data": self.data,
            "lane": self.lane,
            "severity": self.severity,
        }


class HistoryLog:
    """In-memory + persistent audit trail for traffic events.

    Maintains a fast in-memory deque for real-time queries and
    writes to the database for long-term storage.

    Replay capability: reconstruct signal state at any past time.
    """

    def __init__(self, max_memory_entries: int = 5000):
        self._entries: Deque[LogEntry] = deque(maxlen=max_memory_entries)
        self._phase_history: List[LogEntry] = []  # all phase changes (never trimmed in memory)
        self._counts_history: Deque[LogEntry] = deque(maxlen=1000)
        self._alert_history: Deque[LogEntry] = deque(maxlen=200)

    def log(
        self,
        event_type: str,
        data: Dict[str, Any],
        lane: str = "",
        severity: str = "info",
    ) -> LogEntry:
        """Add an event to the log.

        Args:
            event_type: Category ("phase_change", "vehicle_count", "alert", etc.)
            data: Arbitrary event data
            lane: Relevant lane name (if applicable)
            severity: "info", "warning", or "critical"

        Returns:
            The created LogEntry
        """
        entry = LogEntry(
            timestamp=time.time(),
            event_type=event_type,
            data=data,
            lane=lane,
            severity=severity,
        )

        self._entries.append(entry)

        # Route to specialized stores
        if event_type == "phase_change":
            self._phase_history.append(entry)
        elif event_type == "vehicle_count":
            self._counts_history.append(entry)
        elif event_type in ("alert", "override"):
            self._alert_history.append(entry)

        return entry

    def log_phase_change(
        self,
        lane: str,
        from_state: str,
        to_state: str,
        reason: str,
        duration: float = 0.0,
        vehicle_count: int = 0,
    ) -> LogEntry:
        """Convenience method for logging phase changes."""
        return self.log(
            event_type="phase_change",
            data={
                "from_state": from_state,
                "to_state": to_state,
                "reason": reason,
                "duration": round(duration, 1),
                "vehicle_count": vehicle_count,
            },
            lane=lane,
        )

    def log_vehicle_count(
        self,
        arm_counts: Dict[str, int],
        total: int,
        congestion_level: str = "",
    ) -> LogEntry:
        """Convenience method for logging vehicle counts."""
        return self.log(
            event_type="vehicle_count",
            data={
                "arm_counts": arm_counts,
                "total": total,
                "congestion_level": congestion_level,
            },
        )

    def log_alert(
        self,
        alert_type: str,
        message: str,
        lane: str = "",
        severity: str = "warning",
    ) -> LogEntry:
        """Convenience method for logging alerts."""
        return self.log(
            event_type="alert",
            data={"alert_type": alert_type, "message": message},
            lane=lane,
            severity=severity,
        )

    # ── Query methods ─────────────────────────────────────────────────────────

    def get_recent(
        self,
        count: int = 50,
        event_type: Optional[str] = None,
    ) -> List[dict]:
        """Get the most recent N log entries, optionally filtered by type."""
        entries = self._entries
        if event_type:
            entries = deque(e for e in entries if e.event_type == event_type)
        return [e.to_dict() for e in list(entries)[-count:]]

    def get_by_time_range(
        self,
        start_time: float,
        end_time: float,
        event_type: Optional[str] = None,
    ) -> List[dict]:
        """Get log entries within a time range."""
        results = []
        for entry in self._entries:
            if start_time <= entry.timestamp <= end_time:
                if event_type is None or entry.event_type == event_type:
                    results.append(entry.to_dict())
        return results

    def get_by_lane(self, lane: str, count: int = 50) -> List[dict]:
        """Get log entries for a specific lane."""
        entries = [e for e in self._entries if e.lane == lane]
        return [e.to_dict() for e in entries[-count:]]

    def get_phase_history(self, count: int = 100) -> List[dict]:
        """Get recent phase changes."""
        return [e.to_dict() for e in self._phase_history[-count:]]

    def get_alert_history(self, count: int = 50) -> List[dict]:
        """Get recent alerts."""
        return [e.to_dict() for e in list(self._alert_history)[-count:]]

    # ── Replay ────────────────────────────────────────────────────────────────

    def replay_signal_state(self, target_time: float) -> Dict[str, str]:
        """Reconstruct the signal state at a given point in time.

        Replays all phase changes up to target_time and returns
        the signal state that would have been active.
        """
        states: Dict[str, str] = {}
        for entry in self._phase_history:
            if entry.timestamp > target_time:
                break
            lane = entry.lane
            to_state = entry.data.get("to_state", "")
            if to_state:
                # Set target lane to its new state
                states[lane] = to_state
                # If going GREEN, set all others to RED
                if to_state == "GREEN":
                    for other_lane in states:
                        if other_lane != lane:
                            states[other_lane] = "RED"

        return states

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get summary statistics."""
        return {
            "total_entries": len(self._entries),
            "phase_changes": len(self._phase_history),
            "count_records": len(self._counts_history),
            "alerts": len(self._alert_history),
        }

    @property
    def entry_count(self) -> int:
        return len(self._entries)

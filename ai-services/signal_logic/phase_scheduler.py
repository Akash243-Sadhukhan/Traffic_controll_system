"""
phase_scheduler.py — Adaptive traffic signal phase scheduling.

Manages the GREEN/YELLOW/RED cycle across intersection lanes,
with density-weighted priority scheduling and configurable timing.
"""

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger("traffic.phase_scheduler")


class LightState(str, Enum):
    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"


class SchedulingMode(str, Enum):
    FIXED = "FIXED"
    ADAPTIVE = "ADAPTIVE"


@dataclass
class PhaseConfig:
    """Configuration for signal phase timing."""
    default_green: int = 30    # seconds
    min_green: int = 10
    max_green: int = 60
    yellow_time: int = 5
    all_red_time: int = 2      # safety clearance
    adaptive_ext_step: int = 2  # seconds per queued vehicle


@dataclass
class LaneState:
    """Current state of a single lane's signal."""
    name: str
    light: LightState = LightState.RED
    green_time_remaining: float = 0.0
    vehicles_served: int = 0
    total_wait_time: float = 0.0


@dataclass
class PhaseChange:
    """Record of a phase change event."""
    timestamp: float
    lane: str
    from_state: str
    to_state: str
    reason: str
    duration: float = 0.0  # how long the previous state lasted
    vehicle_count: int = 0


class PhaseScheduler:
    """Manages traffic signal phases with adaptive scheduling.

    Supports:
    - Fixed round-robin scheduling
    - Adaptive scheduling based on density
    - Yellow transition handling
    - Phase change event logging
    """

    def __init__(
        self,
        lane_names: List[str],
        config: Optional[PhaseConfig] = None,
        mode: SchedulingMode = SchedulingMode.ADAPTIVE,
    ):
        self.lane_names = lane_names
        self.config = config or PhaseConfig()
        self.mode = mode

        # Initialize all lanes to RED, first lane to GREEN
        self.lanes: Dict[str, LaneState] = {}
        for name in lane_names:
            self.lanes[name] = LaneState(name=name, light=LightState.RED)

        self._active_lane: str = lane_names[0] if lane_names else ""
        if self._active_lane:
            self.lanes[self._active_lane].light = LightState.GREEN
            self.lanes[self._active_lane].green_time_remaining = float(self.config.default_green)

        self._pending_lane: Optional[str] = None  # next lane after YELLOW
        self._phase_start_time: float = time.time()
        self._phase_history: List[PhaseChange] = []
        self._queue: List[str] = list(lane_names[1:]) if len(lane_names) > 1 else []

    @property
    def active_lane(self) -> str:
        return self._active_lane

    @property
    def current_states(self) -> Dict[str, str]:
        """Get {lane: "RED"|"YELLOW"|"GREEN"} for all lanes."""
        return {name: ls.light.value for name, ls in self.lanes.items()}

    @property
    def phase_history(self) -> List[PhaseChange]:
        return self._phase_history

    def tick(self, arm_counts: Optional[Dict[str, int]] = None) -> List[PhaseChange]:
        """Advance the signal state by one tick.

        Args:
            arm_counts: Optional per-lane vehicle counts for adaptive mode.

        Returns:
            List of PhaseChange events that occurred during this tick.
        """
        if not self._active_lane:
            return []

        changes: List[PhaseChange] = []
        now = time.time()
        elapsed = now - self._phase_start_time
        current = self.lanes[self._active_lane]

        if current.light == LightState.YELLOW:
            # Yellow complete → switch to next lane
            if elapsed >= self.config.yellow_time:
                change = self._complete_transition(now, elapsed)
                if change:
                    changes.append(change)

        elif current.light == LightState.GREEN:
            # Calculate effective green time
            green_duration = self.config.default_green

            if self.mode == SchedulingMode.ADAPTIVE and arm_counts:
                green_duration = self._adaptive_green_time(arm_counts)

            # Check if it's time to switch
            if elapsed >= green_duration:
                next_lane = self._select_next_lane(arm_counts)
                if next_lane and next_lane != self._active_lane:
                    change = self._start_transition(next_lane, now, elapsed, arm_counts)
                    if change:
                        changes.append(change)
                else:
                    # Extend current green if no better candidate
                    pass

            elif elapsed >= self.config.min_green and arm_counts:
                # Early switch if current lane is empty and another has traffic
                current_count = arm_counts.get(self._active_lane, 0)
                if current_count == 0:
                    best = self._select_next_lane(arm_counts)
                    best_count = arm_counts.get(best, 0) if best else 0
                    if best and best_count > 0:
                        change = self._start_transition(best, now, elapsed, arm_counts)
                        if change:
                            changes.append(change)

        return changes

    def _adaptive_green_time(self, arm_counts: Dict[str, int]) -> float:
        """Calculate adaptive green time based on current lane's queue."""
        count = arm_counts.get(self._active_lane, 0)
        extension = min(count * self.config.adaptive_ext_step, 30)
        return min(
            self.config.default_green + extension,
            self.config.max_green,
        )

    def _select_next_lane(self, arm_counts: Optional[Dict[str, int]] = None) -> Optional[str]:
        """Select the next lane to receive green.

        In ADAPTIVE mode: pick the lane with the highest queue.
        In FIXED mode: round-robin.
        """
        if self.mode == SchedulingMode.FIXED or not arm_counts:
            # Round-robin
            idx = self.lane_names.index(self._active_lane)
            return self.lane_names[(idx + 1) % len(self.lane_names)]

        # Adaptive: pick highest queue excluding current
        candidates = {k: v for k, v in arm_counts.items() if k != self._active_lane}
        if not candidates:
            return None
        return max(candidates, key=candidates.get)

    def _start_transition(
        self,
        next_lane: str,
        now: float,
        elapsed: float,
        arm_counts: Optional[Dict[str, int]] = None,
    ) -> PhaseChange:
        """Begin YELLOW transition from active lane."""
        change = PhaseChange(
            timestamp=now,
            lane=self._active_lane,
            from_state=LightState.GREEN.value,
            to_state=LightState.YELLOW.value,
            reason=f"switching to {next_lane} (queue-based)" if arm_counts else "round-robin",
            duration=elapsed,
            vehicle_count=arm_counts.get(self._active_lane, 0) if arm_counts else 0,
        )

        self.lanes[self._active_lane].light = LightState.YELLOW
        self._pending_lane = next_lane
        self._phase_start_time = now
        self._phase_history.append(change)

        return change

    def _complete_transition(self, now: float, elapsed: float) -> PhaseChange:
        """Complete the YELLOW→RED→GREEN transition."""
        # Current lane goes RED
        self.lanes[self._active_lane].light = LightState.RED

        # New lane goes GREEN
        old_active = self._active_lane
        self._active_lane = self._pending_lane or self._active_lane
        self._pending_lane = None
        self.lanes[self._active_lane].light = LightState.GREEN
        self.lanes[self._active_lane].green_time_remaining = float(self.config.default_green)
        self._phase_start_time = now

        change = PhaseChange(
            timestamp=now,
            lane=self._active_lane,
            from_state=LightState.RED.value,
            to_state=LightState.GREEN.value,
            reason=f"transition from {old_active} complete",
            duration=elapsed,
        )
        self._phase_history.append(change)
        return change

    def force_green(self, lane: str, reason: str = "manual override") -> Optional[PhaseChange]:
        """Force a specific lane to GREEN immediately (for emergency preemption)."""
        if lane not in self.lanes:
            return None

        now = time.time()
        elapsed = now - self._phase_start_time

        # Set all lanes to RED
        for ls in self.lanes.values():
            ls.light = LightState.RED

        # Set target lane to GREEN
        old_active = self._active_lane
        self._active_lane = lane
        self.lanes[lane].light = LightState.GREEN
        self._phase_start_time = now
        self._pending_lane = None

        change = PhaseChange(
            timestamp=now,
            lane=lane,
            from_state="FORCED",
            to_state=LightState.GREEN.value,
            reason=reason,
            duration=elapsed,
        )
        self._phase_history.append(change)
        logger.warning("FORCED GREEN on %s — reason: %s", lane, reason)
        return change

    def get_signal_snapshot(self) -> dict:
        """Full signal state for API/WebSocket broadcast."""
        return {
            "mode": self.mode.value,
            "active_lane": self._active_lane,
            "states": self.current_states,
            "pending_lane": self._pending_lane,
            "phase_elapsed": round(time.time() - self._phase_start_time, 1),
        }

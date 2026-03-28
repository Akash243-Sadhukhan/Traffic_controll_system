"""
signal_simulator.py — Software traffic signal visualization.

Simulates traffic signals without GPIO hardware, providing current state
via the WebSocket manager for frontend consumption.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List

logger = logging.getLogger("traffic.signal_simulator")


@dataclass
class SignalLight:
    """Represents a single traffic signal light."""
    lane: str
    state: str = "RED"            # RED, YELLOW, GREEN
    time_in_state: float = 0.0
    total_green_time: float = 0.0
    total_red_time: float = 0.0
    cycle_count: int = 0

    def to_dict(self) -> dict:
        return {
            "lane": self.lane,
            "state": self.state,
            "time_in_state": round(self.time_in_state, 1),
            "total_green_time": round(self.total_green_time, 1),
            "total_red_time": round(self.total_red_time, 1),
            "cycle_count": self.cycle_count,
        }


class SignalSimulator:
    """Software-based traffic signal simulator.

    Maintains the visual state of traffic lights for display purposes.
    Integrates with PhaseScheduler for actual decisions but manages
    the display representation and timing statistics.
    """

    def __init__(self, lane_names: List[str]):
        self.lights: Dict[str, SignalLight] = {
            name: SignalLight(lane=name) for name in lane_names
        }
        self._last_tick = time.time()

    def update_states(self, states: Dict[str, str]) -> None:
        """Update signal states from the PhaseScheduler.

        Args:
            states: {lane_name: "RED"|"YELLOW"|"GREEN"}
        """
        now = time.time()
        dt = now - self._last_tick
        self._last_tick = now

        for lane, state in states.items():
            light = self.lights.get(lane)
            if not light:
                continue

            # Track time in current state
            if light.state == state:
                light.time_in_state += dt
            else:
                # State changed
                old_state = light.state
                if old_state == "GREEN":
                    light.total_green_time += light.time_in_state
                elif old_state == "RED":
                    light.total_red_time += light.time_in_state

                light.state = state
                light.time_in_state = 0.0

                if state == "GREEN":
                    light.cycle_count += 1

    def get_display_state(self) -> dict:
        """Get the full display state for frontend rendering."""
        return {
            "lights": {name: light.to_dict() for name, light in self.lights.items()},
            "timestamp": time.time(),
        }

    def get_ascii_display(self) -> str:
        """Generate ASCII art representation of the intersection signals."""
        lines = []
        lines.append("      ┌─────┐")

        # North
        n = self.lights.get("north")
        n_symbol = "🟢" if n and n.state == "GREEN" else "🟡" if n and n.state == "YELLOW" else "🔴"
        lines.append(f"      │  {n_symbol}  │  NORTH")
        lines.append("┌─────┼─────┼─────┐")

        # West and East
        w = self.lights.get("west")
        e = self.lights.get("east")
        w_symbol = "🟢" if w and w.state == "GREEN" else "🟡" if w and w.state == "YELLOW" else "🔴"
        e_symbol = "🟢" if e and e.state == "GREEN" else "🟡" if e and e.state == "YELLOW" else "🔴"
        lines.append(f"│ {w_symbol}  │     │  {e_symbol} │")
        lines.append(f"│WEST │     │ EAST│")
        lines.append("└─────┼─────┼─────┘")

        # South
        s = self.lights.get("south")
        s_symbol = "🟢" if s and s.state == "GREEN" else "🟡" if s and s.state == "YELLOW" else "🔴"
        lines.append(f"      │  {s_symbol}  │  SOUTH")
        lines.append("      └─────┘")

        return "\n".join(lines)

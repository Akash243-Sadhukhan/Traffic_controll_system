"""
terminal_log.py — Rich-powered terminal dashboard for traffic monitoring.

Provides a beautiful terminal UI with live-updating panels showing
traffic stats, signal states, detection events, and alerts.
"""

import logging
from typing import Dict, List, Optional

from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

logger = logging.getLogger("traffic.terminal_log")


class TerminalDashboard:
    """Rich terminal dashboard for traffic monitoring.

    Panels:
    1. System Status — mode, uptime, active vehicles, FPS
    2. Queue Analyser — per-arm vehicle counts with bar chart
    3. Signal State — current light state for each lane
    4. Event Log — recent detection events
    5. Alerts — active alerts and overrides
    """

    def __init__(self):
        self._live: Optional[Live] = None
        self._data = {
            "mode": "ADAPTIVE",
            "total_vehicles": 0,
            "fps": 0.0,
            "frame_count": 0,
            "arm_counts": {"north": 0, "south": 0, "east": 0, "west": 0},
            "signal_states": {"north": "RED", "south": "RED", "east": "RED", "west": "RED"},
            "active_lane": "north",
            "events": [],
            "alerts": [],
            "density": {},
            "override_active": False,
        }

    def update(self, data: dict) -> None:
        """Update dashboard data."""
        self._data.update(data)

    def generate_layout(self) -> Layout:
        """Generate the full dashboard layout."""
        layout = Layout()

        # Title bar
        title = Panel(
            "[bold cyan]🚦 AI Traffic Management System[/bold cyan]  |  "
            f"[white]{self._data['mode']}[/white] mode  |  "
            f"[green]{self._data['total_vehicles']}[/green] vehicles  |  "
            f"[yellow]{self._data['fps']:.1f}[/yellow] FPS",
            style="blue",
        )

        # Main grid
        grid = Table.grid(expand=True)
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)

        # Row 1: Status + Queue
        grid.add_row(
            Panel(self._status_text(), title="System Status", border_style="blue"),
            Panel(self._queue_chart(), title="Queue Analyser", border_style="magenta"),
        )

        # Row 2: Signals + Events
        grid.add_row(
            Panel(self._signal_text(), title="Signal State", border_style="green"),
            Panel(self._events_text(), title="Event Log", border_style="cyan"),
        )

        # Row 3: Density + Alerts
        grid.add_row(
            Panel(self._density_text(), title="Density Analysis", border_style="yellow"),
            Panel(self._alerts_text(), title="Alerts", border_style="red"),
        )

        layout.split_column(
            Layout(title, size=3),
            Layout(grid),
        )

        return layout

    def _status_text(self) -> Text:
        t = Text()
        t.append(f"Control Mode  : ", style="dim")
        t.append(f"{self._data['mode']}\n", style="bold white")
        t.append(f"Active Lane   : ", style="dim")
        t.append(f"{self._data.get('active_lane', 'N/A')}\n", style="bold green")
        t.append(f"Frame Count   : ", style="dim")
        t.append(f"{self._data['frame_count']}\n", style="cyan")
        t.append(f"Total Vehicles: ", style="dim")
        t.append(f"{self._data['total_vehicles']}\n", style="bold yellow")
        if self._data.get("override_active"):
            t.append("🚨 OVERRIDE ACTIVE\n", style="bold red blink")
        return t

    def _queue_chart(self) -> Text:
        t = Text()
        arms = self._data.get("arm_counts", {})
        for arm in ("north", "south", "east", "west"):
            count = arms.get(arm, 0)
            bar = "█" * min(count, 25)
            color = "green" if count <= 3 else "yellow" if count <= 7 else "red"
            t.append(f"{arm.upper():<6}│ {count:<3}│ ", style="dim")
            t.append(f"{bar}\n", style=color)
        return t

    def _signal_text(self) -> Text:
        t = Text()
        states = self._data.get("signal_states", {})
        active = self._data.get("active_lane", "")

        for lane, state in states.items():
            indicator = "🟢" if state == "GREEN" else "🟡" if state == "YELLOW" else "🔴"
            style = "bold green" if state == "GREEN" else "bold yellow" if state == "YELLOW" else "red"
            marker = " ◀" if lane == active else ""
            t.append(f"  {indicator} {lane.upper():<6} {state:<7}{marker}\n", style=style)
        return t

    def _events_text(self) -> Text:
        t = Text()
        events = self._data.get("events", [])
        if not events:
            t.append("Waiting for events …\n", style="dim")
            return t
        for ev in events[-6:]:
            style = "red bold" if ev.get("is_emergency") else "green"
            t.append(
                f"{ev.get('vehicle_class', '?'):<10} "
                f"{ev.get('lane', '?'):<6} "
                f"{ev.get('confidence', 0):.0%}\n",
                style=style,
            )
        return t

    def _density_text(self) -> Text:
        t = Text()
        density = self._data.get("density", {})
        if not density:
            t.append("No density data yet\n", style="dim")
            return t
        for lane, info in density.items():
            if isinstance(info, dict):
                level = info.get("congestion", "LOW")
                color = "green" if level == "LOW" else "yellow" if level == "MEDIUM" else "red"
                t.append(f"{lane.upper():<6} ", style="dim")
                t.append(f"{level:<8} ", style=color)
                t.append(f"+{info.get('recommended_green_extension', 0)}s\n", style="cyan")
        return t

    def _alerts_text(self) -> Text:
        t = Text()
        alerts = self._data.get("alerts", [])
        if not alerts:
            t.append("No active alerts ✓\n", style="green")
            return t
        for alert in alerts[-4:]:
            severity = alert.get("severity", "info")
            style = "red bold" if severity == "critical" else "yellow" if severity == "warning" else "dim"
            t.append(f"[{severity.upper()}] {alert.get('message', '')}\n", style=style)
        return t

    def start(self) -> Live:
        """Start the live dashboard."""
        self._live = Live(self.generate_layout(), refresh_per_second=4)
        return self._live

    def refresh(self) -> None:
        """Refresh the live display."""
        if self._live:
            self._live.update(self.generate_layout())

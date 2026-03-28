"""
density_analyser.py — Per-lane density analysis with congestion classification.

Takes raw vehicle counts per lane and produces congestion levels,
weighted density scores, and trend indicators.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger("traffic.density_analyser")


class CongestionLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TrendDirection(str, Enum):
    INCREASING = "increasing"
    STABLE = "stable"
    DECREASING = "decreasing"


@dataclass
class LaneDensity:
    """Density analysis result for a single lane."""
    lane: str
    vehicle_count: int
    weighted_count: float
    congestion: CongestionLevel
    trend: TrendDirection = TrendDirection.STABLE
    recommended_green_extension: int = 0  # seconds

    def to_dict(self) -> dict:
        return {
            "lane": self.lane,
            "vehicle_count": self.vehicle_count,
            "weighted_count": round(self.weighted_count, 1),
            "congestion": self.congestion.value,
            "trend": self.trend.value,
            "recommended_green_extension": self.recommended_green_extension,
        }


@dataclass
class IntersectionDensity:
    """Full intersection density snapshot."""
    lanes: Dict[str, LaneDensity] = field(default_factory=dict)
    most_congested: str = ""
    total_vehicles: int = 0
    overall_congestion: CongestionLevel = CongestionLevel.LOW
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return {
            "lanes": {k: v.to_dict() for k, v in self.lanes.items()},
            "most_congested": self.most_congested,
            "total_vehicles": self.total_vehicles,
            "overall_congestion": self.overall_congestion.value,
            "timestamp": self.timestamp,
        }


# ── Thresholds ────────────────────────────────────────────────────────────────
_CONGESTION_THRESHOLDS = {
    CongestionLevel.LOW: (0, 3),
    CongestionLevel.MEDIUM: (4, 7),
    CongestionLevel.HIGH: (8, 14),
    CongestionLevel.CRITICAL: (15, float("inf")),
}


class DensityAnalyser:
    """Analyses per-lane vehicle density and produces congestion metrics.

    Accepts raw counts (from VehicleCounter) and weighted counts,
    classifies congestion, and recommends green time extensions.
    """

    def __init__(
        self,
        max_green_extension: int = 15,
        extension_per_vehicle: int = 2,
    ):
        self.max_green_extension = max_green_extension
        self.extension_per_vehicle = extension_per_vehicle
        self._last_result: Optional[IntersectionDensity] = None

    def analyse(
        self,
        arm_counts: Dict[str, int],
        weighted_counts: Optional[Dict[str, float]] = None,
        trends: Optional[Dict[str, str]] = None,
        timestamp: float = 0.0,
    ) -> IntersectionDensity:
        """Analyse the current intersection density.

        Args:
            arm_counts: {lane_name: vehicle_count}
            weighted_counts: {lane_name: weighted_count} (bus=2x, etc.)
            trends: {lane_name: "increasing"|"stable"|"decreasing"}
            timestamp: current timestamp

        Returns:
            IntersectionDensity with per-lane analysis and recommendations.
        """
        if weighted_counts is None:
            weighted_counts = {k: float(v) for k, v in arm_counts.items()}
        if trends is None:
            trends = {k: "stable" for k in arm_counts}

        lanes: Dict[str, LaneDensity] = {}
        for lane, count in arm_counts.items():
            congestion = self._classify(count)
            trend = TrendDirection(trends.get(lane, "stable"))
            extension = min(count * self.extension_per_vehicle, self.max_green_extension)

            # Boost extension if trend is increasing
            if trend == TrendDirection.INCREASING:
                extension = min(extension + 3, self.max_green_extension)

            lanes[lane] = LaneDensity(
                lane=lane,
                vehicle_count=count,
                weighted_count=weighted_counts.get(lane, float(count)),
                congestion=congestion,
                trend=trend,
                recommended_green_extension=extension,
            )

        # Find most congested lane
        most_congested = max(arm_counts, key=arm_counts.get) if arm_counts else ""
        total = sum(arm_counts.values())

        # Overall congestion
        overall = self._classify(total // max(len(arm_counts), 1))

        result = IntersectionDensity(
            lanes=lanes,
            most_congested=most_congested,
            total_vehicles=total,
            overall_congestion=overall,
            timestamp=timestamp,
        )

        self._last_result = result
        return result

    @staticmethod
    def _classify(count: int) -> CongestionLevel:
        """Classify a vehicle count into a congestion level."""
        for level, (low, high) in _CONGESTION_THRESHOLDS.items():
            if low <= count <= high:
                return level
        return CongestionLevel.CRITICAL

    @property
    def last_result(self) -> Optional[IntersectionDensity]:
        return self._last_result

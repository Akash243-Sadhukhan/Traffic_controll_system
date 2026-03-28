"""
repository.py — Database CRUD operations and query helpers.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session as SASession

from db.models import (
    AlertEvent,
    DetectionEvent,
    SignalPhaseLog,
    VehicleCountEvent,
    init_db,
)

logger = logging.getLogger("traffic.repository")


class TrafficRepository:
    """CRUD interface for all traffic-related database operations."""

    def __init__(self, database_url: str = "sqlite:///traffic.db"):
        self._engine, self._SessionFactory = init_db(database_url)
        logger.info("Database initialized: %s", database_url)

    def _session(self) -> SASession:
        return self._SessionFactory()

    # ── Vehicle Counts ────────────────────────────────────────────────────────

    def save_vehicle_count(
        self,
        arm_counts: Dict[str, int],
        total: int,
        congestion_level: str = "LOW",
        mode: str = "ADAPTIVE",
        source: str = "detection",
        intersection_id: str = "MAIN_JUNCTION",
    ) -> int:
        with self._session() as session:
            event = VehicleCountEvent(
                arm_counts=arm_counts,
                total_vehicles=total,
                congestion_level=congestion_level,
                mode=mode,
                source=source,
                intersection_id=intersection_id,
            )
            session.add(event)
            session.commit()
            return event.id

    def get_vehicle_counts(
        self,
        limit: int = 100,
        since: Optional[datetime] = None,
    ) -> List[dict]:
        with self._session() as session:
            query = session.query(VehicleCountEvent).order_by(
                VehicleCountEvent.timestamp.desc()
            )
            if since:
                query = query.filter(VehicleCountEvent.timestamp >= since)
            return [e.to_dict() for e in query.limit(limit).all()]

    # ── Signal Phase Logs ─────────────────────────────────────────────────────

    def save_phase_change(
        self,
        lane: str,
        from_state: str,
        to_state: str,
        reason: str,
        duration: float = 0.0,
        vehicle_count: int = 0,
    ) -> int:
        with self._session() as session:
            log = SignalPhaseLog(
                lane=lane,
                from_state=from_state,
                to_state=to_state,
                reason=reason,
                duration=duration,
                vehicle_count=vehicle_count,
            )
            session.add(log)
            session.commit()
            return log.id

    def get_phase_logs(
        self,
        limit: int = 100,
        lane: Optional[str] = None,
    ) -> List[dict]:
        with self._session() as session:
            query = session.query(SignalPhaseLog).order_by(
                SignalPhaseLog.timestamp.desc()
            )
            if lane:
                query = query.filter(SignalPhaseLog.lane == lane)
            return [e.to_dict() for e in query.limit(limit).all()]

    # ── Detection Events ──────────────────────────────────────────────────────

    def save_detection(
        self,
        vehicle_class: str,
        plate_number: Optional[str] = None,
        lane: Optional[str] = None,
        confidence: float = 0.0,
        is_emergency: bool = False,
    ) -> int:
        with self._session() as session:
            event = DetectionEvent(
                vehicle_class=vehicle_class,
                plate_number=plate_number,
                lane=lane,
                confidence=confidence,
                is_emergency=is_emergency,
            )
            session.add(event)
            session.commit()
            return event.id

    def get_detections(
        self,
        limit: int = 100,
        since: Optional[datetime] = None,
    ) -> List[dict]:
        with self._session() as session:
            query = session.query(DetectionEvent).order_by(
                DetectionEvent.timestamp.desc()
            )
            if since:
                query = query.filter(DetectionEvent.timestamp >= since)
            return [e.to_dict() for e in query.limit(limit).all()]

    # ── Alert Events ──────────────────────────────────────────────────────────

    def save_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        lane: Optional[str] = None,
    ) -> int:
        with self._session() as session:
            event = AlertEvent(
                alert_type=alert_type,
                severity=severity,
                message=message,
                lane=lane,
            )
            session.add(event)
            session.commit()
            return event.id

    def get_alerts(
        self,
        limit: int = 50,
        unresolved_only: bool = False,
    ) -> List[dict]:
        with self._session() as session:
            query = session.query(AlertEvent).order_by(
                AlertEvent.timestamp.desc()
            )
            if unresolved_only:
                query = query.filter(AlertEvent.resolved == False)
            return [e.to_dict() for e in query.limit(limit).all()]

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup_old_records(self, retention_hours: int = 72) -> int:
        """Delete records older than retention_hours. Returns count deleted."""
        cutoff = datetime.utcnow() - timedelta(hours=retention_hours)
        total = 0

        with self._session() as session:
            for model in [VehicleCountEvent, SignalPhaseLog, DetectionEvent, AlertEvent]:
                count = session.query(model).filter(
                    model.timestamp < cutoff
                ).delete()
                total += count
            session.commit()

        if total > 0:
            logger.info("Cleaned up %d old records (older than %dh)", total, retention_hours)
        return total

    # ── Dashboard Stats ───────────────────────────────────────────────────────

    def get_dashboard_stats(self) -> dict:
        """Aggregated stats for dashboard display."""
        with self._session() as session:
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)

            total_detections = session.query(DetectionEvent).count()
            recent_detections = session.query(DetectionEvent).filter(
                DetectionEvent.timestamp >= one_hour_ago
            ).count()
            active_alerts = session.query(AlertEvent).filter(
                AlertEvent.resolved == False
            ).count()
            phase_changes = session.query(SignalPhaseLog).filter(
                SignalPhaseLog.timestamp >= one_hour_ago
            ).count()

            return {
                "total_detections": total_detections,
                "recent_detections_1h": recent_detections,
                "active_alerts": active_alerts,
                "phase_changes_1h": phase_changes,
            }

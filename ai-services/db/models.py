"""
models.py — SQLAlchemy database models for traffic event persistence.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime, JSON, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


class VehicleCountEvent(Base):
    """Stores periodic vehicle count snapshots."""
    __tablename__ = "vehicle_count_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    intersection_id = Column(String(50), default="MAIN_JUNCTION")
    arm_counts = Column(JSON)  # {"north": 5, "south": 3, ...}
    total_vehicles = Column(Integer, default=0)
    congestion_level = Column(String(20), default="LOW")
    mode = Column(String(20), default="ADAPTIVE")
    source = Column(String(50), default="detection")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "intersection_id": self.intersection_id,
            "arm_counts": self.arm_counts,
            "total_vehicles": self.total_vehicles,
            "congestion_level": self.congestion_level,
            "mode": self.mode,
            "source": self.source,
        }


class SignalPhaseLog(Base):
    """Records every signal phase change."""
    __tablename__ = "signal_phase_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    lane = Column(String(20))
    from_state = Column(String(10))
    to_state = Column(String(10))
    reason = Column(String(200))
    duration = Column(Float, default=0.0)
    vehicle_count = Column(Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "lane": self.lane,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "reason": self.reason,
            "duration": self.duration,
            "vehicle_count": self.vehicle_count,
        }


class DetectionEvent(Base):
    """Stores vehicle detection events (plate reads, classifications)."""
    __tablename__ = "detection_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    vehicle_class = Column(String(30))
    plate_number = Column(String(20), nullable=True)
    lane = Column(String(20), nullable=True)
    location_id = Column(String(50), default="MAIN_JUNCTION")
    confidence = Column(Float, default=0.0)
    is_emergency = Column(Boolean, default=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "vehicle_class": self.vehicle_class,
            "plate_number": self.plate_number,
            "lane": self.lane,
            "location_id": self.location_id,
            "confidence": self.confidence,
            "is_emergency": self.is_emergency,
        }


class AlertEvent(Base):
    """Stores alert and override events."""
    __tablename__ = "alert_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    alert_type = Column(String(50))  # "emergency_override", "congestion", "anomaly"
    severity = Column(String(20))    # "info", "warning", "critical"
    message = Column(String(500))
    lane = Column(String(20), nullable=True)
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "message": self.message,
            "lane": self.lane,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


def init_db(database_url: str = "sqlite:///traffic.db"):
    """Create engine, session factory, and all tables."""
    engine = create_engine(database_url, echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session

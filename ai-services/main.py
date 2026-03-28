"""
main.py — FastAPI application entry point for the AI Traffic Management System.

Orchestrates the detection pipeline, signal controller, density analyser,
WebSocket broadcasting, and history logging into a unified engine.
"""

import asyncio
import json
import logging
import os
import sys
import threading
import time
from typing import Dict, List, Optional

# MPS memory fix — must be before any torch import
os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Local imports
from config import settings, BASE_DIR
from detection.camera_feed import CameraFeed, SourceType
from detection.yolo_detector import YOLODetector, Detection
from detection.vehicle_counter import VehicleCounter
from signal_logic.density_analyser import DensityAnalyser
from signal_logic.phase_scheduler import PhaseScheduler, PhaseConfig, SchedulingMode
from signal_logic.priority_override import PriorityOverride
from signal_logic.history_log import HistoryLog
from signal_logic.rl_controller import RLSignalController
from display.opencv_window import OpenCVDisplay
from display.signal_simulator import SignalSimulator
from api.websocket_manager import ws_manager
from api.mqtt_bridge import mqtt_bridge
from db.repository import TrafficRepository

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("traffic.main")


# ══════════════════════════════════════════════════════════════════════════════
# TRAFFIC ENGINE — Central coordinator
# ══════════════════════════════════════════════════════════════════════════════


class TrafficEngine:
    """Central engine coordinating all traffic management subsystems.

    Ties together:
    - Camera feed → YOLO detector → Vehicle counter
    - Density analyser → Phase scheduler → Priority override
    - History logger → Database repository
    - WebSocket & MQTT broadcasting
    - OpenCV window & terminal display
    """

    def __init__(self):
        # Detection layer
        self.camera: Optional[CameraFeed] = None
        self.detector = YOLODetector(
            model_path=settings.vehicle_model,
            device=settings.device,
            confidence=settings.detection_confidence,
        )
        self.counter = VehicleCounter()

        # Signal control layer
        lane_names = list(settings.lane_names)
        self.density_analyser = DensityAnalyser()
        self.phase_scheduler = PhaseScheduler(
            lane_names=lane_names,
            config=PhaseConfig(
                default_green=settings.default_green_time,
                min_green=settings.min_green_time,
                max_green=settings.max_green_time,
                yellow_time=settings.yellow_time,
                adaptive_ext_step=settings.adaptive_ext_step,
            ),
            mode=SchedulingMode.ADAPTIVE,
        )
        self.priority_override = PriorityOverride()
        self.history = HistoryLog()
        
        # RL Model
        self.rl_controller = RLSignalController(
            model_path=settings.rl_policy_model,
            device=settings.device
        )

        # Display layer
        self.display = OpenCVDisplay(
            window_name=settings.window_name,
            enabled=settings.show_opencv_window,
        )
        self.signal_sim = SignalSimulator(lane_names=lane_names)

        # Database
        self.db = TrafficRepository(database_url=settings.database_url)

        # State
        self._detection_running = False
        self._detection_thread: Optional[threading.Thread] = None
        self._frame_count = 0
        self._last_fps = 0.0
        self._last_detections: List[Detection] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        logger.info("🚦 TrafficEngine initialized (device=%s)", settings.device)

    # ── Detection Loop ────────────────────────────────────────────────────────

    def start_detection(self, source: str = "0", target_fps: float = 30.0) -> None:
        """Start the detection loop in a background thread."""
        if self._detection_running:
            self.stop_detection()

        # Parse source
        try:
            src = int(source)
        except ValueError:
            src = source

        self.camera = CameraFeed(source=src, target_fps=target_fps)
        self._detection_running = True

        self._detection_thread = threading.Thread(
            target=self._detection_loop,
            name="detection-loop",
            daemon=True,
        )
        self._detection_thread.start()
        logger.info("Detection started — source=%s, fps=%.1f", source, target_fps)

    def stop_detection(self) -> None:
        """Stop the detection loop."""
        self._detection_running = False
        if self._detection_thread and self._detection_thread.is_alive():
            self._detection_thread.join(timeout=3.0)
        if self.camera:
            self.camera.close()
        self.display.close()
        logger.info("Detection stopped (total frames: %d)", self._frame_count)

    def _detection_loop(self) -> None:
        """Background thread: frame capture → detection → signal update → display."""
        if not self.camera or not self.camera.open():
            self._detection_running = False
            logger.error("Failed to open camera feed")
            return

        for frame, meta in self.camera.frames():
            if not self._detection_running:
                break

            if frame is None:
                continue

            self._frame_count += 1
            self._last_fps = meta.fps

            # 1. Detect vehicles
            detections = self.detector.detect(frame)
            self._last_detections = detections

            # 2. Count per zone
            zone_counts = self.counter.update(detections)
            arm_counts = self.counter.get_arm_counts()

            # 3. Density analysis
            weighted = self.counter.get_weighted_counts()
            trends = {z: self.counter.get_trend(z) for z in arm_counts}
            density = self.density_analyser.analyse(
                arm_counts, weighted, trends, meta.timestamp
            )

            # 4. Signal scheduling
            changes = self.phase_scheduler.tick(arm_counts)
            for change in changes:
                self.history.log_phase_change(
                    lane=change.lane,
                    from_state=change.from_state,
                    to_state=change.to_state,
                    reason=change.reason,
                    duration=change.duration,
                    vehicle_count=change.vehicle_count,
                )
                self.db.save_phase_change(
                    lane=change.lane,
                    from_state=change.from_state,
                    to_state=change.to_state,
                    reason=change.reason,
                    duration=change.duration,
                    vehicle_count=change.vehicle_count,
                )

            # 5. Priority override check
            self.priority_override.tick()

            # 6. Update signal simulator
            self.signal_sim.update_states(self.phase_scheduler.current_states)

            # 7. Periodic DB save & broadcast
            if self._frame_count % 30 == 0:  # every ~1 second at 30fps
                self.db.save_vehicle_count(
                    arm_counts=arm_counts,
                    total=self.counter.total_vehicles,
                    congestion_level=density.overall_congestion.value,
                )
                self.history.log_vehicle_count(
                    arm_counts=arm_counts,
                    total=self.counter.total_vehicles,
                    congestion_level=density.overall_congestion.value,
                )

                # WebSocket broadcast (fire-and-forget)
                if self._loop:
                    asyncio.run_coroutine_threadsafe(
                        self._broadcast_update(arm_counts, density),
                        self._loop,
                    )

            # 8. OpenCV display
            alert = ""
            if self.priority_override.is_active:
                ov = self.priority_override.active_override
                alert = f"EMERGENCY: {ov.vehicle_type} on {ov.lane}"

            keep_going = self.display.render(
                frame=frame,
                detections=detections,
                signal_states=self.phase_scheduler.current_states,
                zone_counts=arm_counts,
                fps=meta.fps,
                alert_text=alert,
            )
            if not keep_going:
                break

        self._detection_running = False
        self.camera.close()
        self.display.close()

    async def _broadcast_update(self, arm_counts: dict, density) -> None:
        """Broadcast current state via WebSocket."""
        await ws_manager.broadcast_stats({
            "arm_counts": arm_counts,
            "total_vehicles": self.counter.total_vehicles,
            "frame_count": self._frame_count,
            "fps": round(self._last_fps, 1),
        })
        await ws_manager.broadcast_signals(self.phase_scheduler.get_signal_snapshot())
        await ws_manager.broadcast_density(density.to_dict())

    # ── External Count Processing ─────────────────────────────────────────────

    def process_external_counts(
        self,
        arm_counts: Dict[str, int],
        total: int,
        mode: str = "ADAPTIVE",
        source: str = "simulation",
    ) -> dict:
        """Process vehicle counts from external source (SUMO, sensors)."""
        # Update density analysis
        density = self.density_analyser.analyse(arm_counts, timestamp=time.time())

        # Update signal scheduling
        changes = self.phase_scheduler.tick(arm_counts)
        for change in changes:
            self.history.log_phase_change(
                lane=change.lane,
                from_state=change.from_state,
                to_state=change.to_state,
                reason=change.reason,
                duration=change.duration,
            )

        # Update signal simulator
        self.signal_sim.update_states(self.phase_scheduler.current_states)

        # Save to DB
        self.db.save_vehicle_count(
            arm_counts=arm_counts,
            total=total,
            congestion_level=density.overall_congestion.value,
            mode=mode,
            source=source,
        )

        self.history.log_vehicle_count(
            arm_counts=arm_counts,
            total=total,
            congestion_level=density.overall_congestion.value,
        )

        return {
            "intersection_id": "MAIN_JUNCTION",
            "arm_counts": arm_counts,
            "total_vehicles": total,
            "density": density.to_dict(),
            "signal_state": self.phase_scheduler.get_signal_snapshot(),
            "most_congested": density.most_congested,
            "override_status": self.priority_override.get_status(),
        }

    # ── RL Decision Logic ─────────────────────────────────────────────────────

    def predict_rl_action(self, observation_8: List[float]) -> int:
        """Map 8-feature stats to 19-dim and run model inference."""
        # Get active phase index (0-3) for one-hot mapping
        try:
            current_lane = self.phase_scheduler.active_lane
            lane_map = ["north", "south", "east", "west"]
            phase_idx = lane_map.index(current_lane) if current_lane in lane_map else 0
        except:
            phase_idx = 0
            
        full_obs = self.rl_controller.map_8_to_19(observation_8, current_phase=phase_idx)
        return self.rl_controller.predict_action(full_obs)

    def apply_rl_decision(self, action: int) -> dict:
        """Apply a binary RL decision (0: Stay, 1: Switch) by cycling phases."""
        if action == 0:
            # RL model decided to STAY
            return {"action": "stay", "mode": "RL"}

        # RL model decided to SWITCH
        # Determine next lane in sequence (round-robin switch)
        current_lane = self.phase_scheduler.active_lane
        all_lanes = ["north", "south", "east", "west"]
        try:
            idx = all_lanes.index(current_lane)
            next_lane = all_lanes[(idx + 1) % len(all_lanes)]
        except:
            next_lane = all_lanes[0]

        change = self.phase_scheduler.force_green(
            next_lane, 
            reason="AI Model RL [SWITCH] Decision"
        )
        
        if change:
            self.history.log_phase_change(
                lane=change.lane,
                from_state=change.from_state,
                to_state=change.to_state,
                reason=change.reason,
                duration=change.duration
            )
            
            # Broadcast update
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    ws_manager.broadcast_signals(self.phase_scheduler.get_signal_snapshot()),
                    self._loop
                )

        return {
            "action": "switch",
            "target": next_lane,
            "signal_state": self.phase_scheduler.get_signal_snapshot()
        }

    # ── Override ──────────────────────────────────────────────────────────────

    def trigger_override(self, lane: str, reason: str = "manual", vehicle_type: str = "manual") -> dict:
        """Trigger priority override on a lane."""
        event = self.priority_override.trigger(lane, vehicle_type)
        change = self.phase_scheduler.force_green(lane, reason=reason)

        self.history.log_alert(
            alert_type="emergency_override",
            message=f"Priority override: {vehicle_type} on {lane} — {reason}",
            lane=lane,
            severity="critical",
        )
        self.db.save_alert(
            alert_type="emergency_override",
            severity="critical",
            message=f"{vehicle_type} override on {lane}",
            lane=lane,
        )

        return {
            "status": "override_activated",
            "lane": lane,
            "override": event.to_dict(),
            "signal_state": self.phase_scheduler.get_signal_snapshot(),
        }

    # ── Snapshots & Queries ───────────────────────────────────────────────────

    def get_snapshot(self) -> dict:
        """Full current state snapshot for API."""
        density_result = self.density_analyser.last_result
        return {
            "detection_running": self._detection_running,
            "frame_count": self._frame_count,
            "fps": round(self._last_fps, 1),
            "total_vehicles": self.counter.total_vehicles,
            "arm_counts": self.counter.get_arm_counts(),
            "signal_state": self.phase_scheduler.get_signal_snapshot(),
            "density": density_result.to_dict() if density_result else {},
            "override_status": self.priority_override.get_status(),
            "signal_display": self.signal_sim.get_display_state(),
            "websocket_clients": ws_manager.client_count,
            "history_stats": self.history.get_stats(),
        }

    def get_detection_status(self) -> dict:
        return {
            "running": self._detection_running,
            "frame_count": self._frame_count,
            "fps": round(self._last_fps, 1),
            "source": self.camera.source_type.value if self.camera else "none",
        }

    def get_signal_state(self) -> dict:
        return {
            **self.phase_scheduler.get_signal_snapshot(),
            "signal_display": self.signal_sim.get_display_state(),
            "override": self.priority_override.get_status(),
        }

    def get_density_analysis(self) -> dict:
        result = self.density_analyser.last_result
        return result.to_dict() if result else {"message": "No density data yet"}

    def get_history(
        self, event_type: Optional[str] = None, lane: Optional[str] = None, limit: int = 50
    ) -> list:
        if lane:
            return self.history.get_by_lane(lane, count=limit)
        return self.history.get_recent(count=limit, event_type=event_type)

    def get_phase_history(self, limit: int = 100) -> list:
        return self.history.get_phase_history(count=limit)

    def get_alert_history(self, limit: int = 50) -> list:
        return self.history.get_alert_history(count=limit)

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop


# ══════════════════════════════════════════════════════════════════════════════
# FASTAPI APP
# ══════════════════════════════════════════════════════════════════════════════

traffic_engine = TrafficEngine()

app = FastAPI(
    title="🚦 AI Traffic Management System",
    description="Adaptive traffic signal control powered by computer vision and AI",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routes
from api.routes import router
app.include_router(router)


@app.on_event("startup")
async def startup():
    """Store the event loop for cross-thread broadcast."""
    traffic_engine.set_event_loop(asyncio.get_event_loop())
    logger.info("🚦 AI Traffic Management System — ONLINE")
    logger.info("   Device: %s", settings.device)
    logger.info("   Port:   %d", settings.port)
    logger.info("   DB:     %s", settings.database_url)


@app.on_event("shutdown")
async def shutdown():
    traffic_engine.stop_detection()
    mqtt_bridge.close()
    logger.info("🚦 System shutdown complete")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )

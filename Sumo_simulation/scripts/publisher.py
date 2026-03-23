# Sumo_simulation/scripts/publisher.py
"""
publisher.py — Non-blocking HTTP publisher that forwards vehicle counts
from the SUMO TraCI loop to ai-services without ever stalling the simulation.

Usage:
    from publisher import VehicleCountPublisher
    pub = VehicleCountPublisher(CFG.ai_service_url)
    pub.publish(STATE.queues, STATE.sim_time, STATE.mode)
"""

import json
import logging
import threading
import time
from typing import Dict

import httpx

from config import STATE  # relative import — same package

logger = logging.getLogger("traffic.publisher")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

_INTERSECTION_ID = "SIM_JUNCTION_001"
_SOURCE          = "sumo_simulation"
_TIMEOUT_SEC     = 3.0
_MAX_RETRIES     = 3
_BACKOFF         = [0.5, 1.0, 2.0]   # seconds between successive retries


class VehicleCountPublisher:
    """
    Fire-and-forget HTTP publisher.

    Each call to :meth:`publish` spawns a **daemon** thread so the TraCI
    event loop is never blocked.  If the ai-services endpoint is unreachable
    the thread logs a warning and exits silently — the simulation continues.
    """

    def __init__(self, ai_service_url: str) -> None:
        self._url = f"{ai_service_url.rstrip('/')}/ai/vehicle-counts"
        logger.info("VehicleCountPublisher initialised → %s", self._url)

    # ── Public API ────────────────────────────────────────────────────────────
    def publish(self, arm_counts: Dict[str, int], sim_time: int, mode: str) -> None:
        """
        Build the payload and dispatch it in a background daemon thread.

        Args:
            arm_counts: Dict mapping arm name → halting vehicle count.
            sim_time:   Current simulation time in steps/seconds.
            mode:       "FIXED" or "ADAPTIVE".
        """
        payload = {
            "timestamp":       sim_time,
            "intersection_id": _INTERSECTION_ID,
            "arm_counts":      dict(arm_counts),
            "total_vehicles":  sum(arm_counts.values()),
            "mode":            mode,
            "source":          _SOURCE,
        }

        t = threading.Thread(
            target=self._do_publish,
            args=(payload,),
            daemon=True,          # never prevents process exit
            name=f"publisher-t{sim_time}",
        )
        t.start()

    # ── Internal (synchronous, runs in background thread) ─────────────────────
    def _do_publish(self, payload: dict) -> None:
        """
        POST payload to ai-services with retry + exponential back-off.

        On HTTP 2xx: parse ProcessedCountResponse JSON and store in
        STATE.last_backend_response.
        On any failure: log warning, never raise.
        """
        for attempt in range(_MAX_RETRIES):
            try:
                response = httpx.post(
                    self._url,
                    json=payload,
                    timeout=_TIMEOUT_SEC,
                )

                if response.is_success:
                    try:
                        data = response.json()
                        STATE.last_backend_response = data
                        STATE.last_publish_time     = payload["timestamp"]
                        logger.debug(
                            "Published t=%d → most_congested=%s backend_notified=%s",
                            payload["timestamp"],
                            data.get("most_congested_arm", "?"),
                            data.get("backend_notified", "?"),
                        )
                    except Exception as parse_err:
                        logger.warning("Could not parse response JSON: %s", parse_err)
                    return  # success — exit retry loop

                # Non-2xx: log and retry
                logger.warning(
                    "ai-services returned HTTP %d (attempt %d/%d)",
                    response.status_code, attempt + 1, _MAX_RETRIES,
                )

            except (httpx.ConnectError, httpx.TimeoutException) as net_err:
                logger.warning(
                    "Network error on attempt %d/%d: %s",
                    attempt + 1, _MAX_RETRIES, net_err,
                )

            except Exception as exc:
                logger.warning("Unexpected error in publisher: %s", exc)
                return  # non-retriable — give up immediately

            # Wait before next retry (skip sleep after last attempt)
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_BACKOFF[attempt])

        logger.warning(
            "Giving up after %d attempts (t=%d).",
            _MAX_RETRIES, payload["timestamp"],
        )

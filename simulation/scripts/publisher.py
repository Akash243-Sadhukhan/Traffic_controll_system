# simulation/scripts/publisher.py
"""
publisher.py — Sends vehicle counts to the ai-services backend.
"""

import logging
import httpx
from typing import Dict

logger = logging.getLogger("traffic_publisher")


class VehicleCountPublisher:
    """Publishes simulation data to the vehicle-counts API endpoint."""

    def __init__(self, backend_url: str):
        self.url = f"{backend_url}/vehicle-counts"
        self._client = httpx.Client(timeout=2.0)

    def publish(self, arm_counts: Dict[str, int], sim_time: int, mode: str):
        """Prepare and send the payload."""
        payload = {
            "arm_counts": arm_counts,
            "total_vehicles": sum(arm_counts.values()),
            "mode": mode,
            "source": "sumo_simulation",
            "timestamp": float(sim_time),
        }

        try:
            resp = self._client.post(self.url, json=payload)
            if not resp.is_success:
                logger.error("Failed to publish counts: HTTP %d", resp.status_code)
        except Exception as exc:
            logger.debug("Publish error (non-fatal): %s", exc)

    def close(self):
        """Clean up the httpx client."""
        self._client.close()

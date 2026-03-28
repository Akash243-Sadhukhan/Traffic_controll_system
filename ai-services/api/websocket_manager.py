"""
websocket_manager.py — WebSocket connection manager for real-time broadcast.

Manages multiple client connections with topic-based messaging,
heartbeat ping/pong, and graceful disconnect handling.
"""

import asyncio
import json
import logging
import time
from enum import Enum
from typing import Dict, List, Set

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("traffic.websocket")


class Topic(str, Enum):
    """Broadcast topics that clients can subscribe to."""
    STATS = "stats"
    SIGNALS = "signals"
    DETECTIONS = "detections"
    ALERTS = "alerts"
    DENSITY = "density"
    HISTORY = "history"
    ALL = "all"


class WebSocketManager:
    """Manages WebSocket connections for real-time data broadcast.

    Features:
    - Multiple concurrent client connections
    - Topic-based subscriptions
    - Auto-cleanup of dead connections
    - JSON message serialization
    - Broadcast to all or specific topics
    """

    def __init__(self, heartbeat_interval: float = 30.0):
        self._connections: Dict[str, WebSocket] = {}  # id → websocket
        self._subscriptions: Dict[str, Set[str]] = {}  # id → set of topics
        self._heartbeat_interval = heartbeat_interval
        self._client_counter = 0

    @property
    def client_count(self) -> int:
        return len(self._connections)

    async def connect(self, websocket: WebSocket, topics: List[str] = None) -> str:
        """Accept a new WebSocket connection.

        Args:
            websocket: The FastAPI WebSocket instance
            topics: List of topics to subscribe to (default: all)

        Returns:
            Client ID string
        """
        await websocket.accept()
        self._client_counter += 1
        client_id = f"client_{self._client_counter}"

        self._connections[client_id] = websocket
        self._subscriptions[client_id] = set(topics or [Topic.ALL])

        logger.info(
            "WebSocket connected: %s (topics: %s) — total: %d",
            client_id, self._subscriptions[client_id], self.client_count,
        )

        # Send welcome message
        await self._send_to(client_id, {
            "type": "connected",
            "client_id": client_id,
            "subscriptions": list(self._subscriptions[client_id]),
            "timestamp": time.time(),
        })

        return client_id

    async def disconnect(self, client_id: str) -> None:
        """Remove a client connection."""
        self._connections.pop(client_id, None)
        self._subscriptions.pop(client_id, None)
        logger.info("WebSocket disconnected: %s — total: %d", client_id, self.client_count)

    async def broadcast(self, topic: str, data: dict) -> None:
        """Broadcast a message to all clients subscribed to the given topic.

        Args:
            topic: The topic channel
            data: The message payload (will be JSON-serialized)
        """
        message = {
            "type": topic,
            "data": data,
            "timestamp": time.time(),
        }

        dead_clients = []
        for client_id, ws in self._connections.items():
            subs = self._subscriptions.get(client_id, set())
            if Topic.ALL in subs or topic in subs:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead_clients.append(client_id)

        # Clean up dead connections
        for client_id in dead_clients:
            await self.disconnect(client_id)

    async def broadcast_stats(self, stats: dict) -> None:
        """Convenience: broadcast traffic stats."""
        await self.broadcast(Topic.STATS, stats)

    async def broadcast_signals(self, signal_state: dict) -> None:
        """Convenience: broadcast signal state."""
        await self.broadcast(Topic.SIGNALS, signal_state)

    async def broadcast_detection(self, detection: dict) -> None:
        """Convenience: broadcast a detection event."""
        await self.broadcast(Topic.DETECTIONS, detection)

    async def broadcast_alert(self, alert: dict) -> None:
        """Convenience: broadcast an alert."""
        await self.broadcast(Topic.ALERTS, alert)

    async def broadcast_density(self, density: dict) -> None:
        """Convenience: broadcast density analysis."""
        await self.broadcast(Topic.DENSITY, density)

    async def _send_to(self, client_id: str, data: dict) -> bool:
        """Send a message to a specific client. Returns False if failed."""
        ws = self._connections.get(client_id)
        if not ws:
            return False
        try:
            await ws.send_json(data)
            return True
        except Exception:
            await self.disconnect(client_id)
            return False

    async def receive_and_process(self, client_id: str) -> None:
        """Listen for messages from a client (for subscription changes, etc.)."""
        ws = self._connections.get(client_id)
        if not ws:
            return

        try:
            while True:
                data = await ws.receive_json()
                msg_type = data.get("type", "")

                if msg_type == "subscribe":
                    topics = data.get("topics", [])
                    self._subscriptions[client_id] = set(topics)
                    logger.debug("Client %s updated subscriptions: %s", client_id, topics)

                elif msg_type == "ping":
                    await self._send_to(client_id, {"type": "pong", "timestamp": time.time()})

        except WebSocketDisconnect:
            await self.disconnect(client_id)
        except Exception as e:
            logger.debug("WebSocket error for %s: %s", client_id, e)
            await self.disconnect(client_id)

    def get_status(self) -> dict:
        """Get WebSocket manager status."""
        return {
            "connected_clients": self.client_count,
            "client_ids": list(self._connections.keys()),
            "subscriptions": {
                k: list(v) for k, v in self._subscriptions.items()
            },
        }


# Singleton instance
ws_manager = WebSocketManager()

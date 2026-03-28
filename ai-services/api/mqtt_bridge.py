"""
mqtt_bridge.py — In-process pub/sub with optional Mosquitto integration.

Provides a lightweight topic-based messaging system that works without
an external broker, but can connect to Mosquitto if configured.
"""

import asyncio
import logging
import json
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("traffic.mqtt_bridge")


class InProcessBroker:
    """Lightweight in-process pub/sub broker.

    Supports topic subscriptions, wildcards, and async callbacks.
    No external dependencies required.
    """

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._message_count = 0

    def subscribe(self, topic: str, callback: Callable) -> None:
        """Subscribe a callback to a topic."""
        self._subscribers[topic].append(callback)
        logger.debug("Subscribed to topic: %s", topic)

    def unsubscribe(self, topic: str, callback: Callable) -> None:
        """Remove a callback from a topic."""
        if topic in self._subscribers:
            self._subscribers[topic] = [
                cb for cb in self._subscribers[topic] if cb != callback
            ]

    async def publish(self, topic: str, data: Any) -> int:
        """Publish data to a topic. Returns number of subscribers notified."""
        self._message_count += 1
        notified = 0

        # Exact topic match
        for callback in self._subscribers.get(topic, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(topic, data)
                else:
                    callback(topic, data)
                notified += 1
            except Exception as e:
                logger.warning("Subscriber error on topic %s: %s", topic, e)

        # Wildcard matches (e.g., "traffic/#" matches "traffic/counts")
        for sub_topic, callbacks in self._subscribers.items():
            if sub_topic.endswith("/#") and topic.startswith(sub_topic[:-2]):
                for callback in callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(topic, data)
                        else:
                            callback(topic, data)
                        notified += 1
                    except Exception as e:
                        logger.warning("Wildcard subscriber error: %s", e)

        return notified

    def get_stats(self) -> dict:
        return {
            "topics": list(self._subscribers.keys()),
            "total_subscribers": sum(len(v) for v in self._subscribers.values()),
            "total_messages": self._message_count,
        }


class MQTTBridge:
    """Bridges in-process pub/sub with optional external MQTT.

    Channels:
    - traffic/counts     — Vehicle count updates
    - traffic/signals    — Signal phase changes
    - traffic/alerts     — Alert events (emergency, etc.)
    - traffic/detections — Vehicle detection events
    - traffic/density    — Density analysis results
    """

    TOPICS = {
        "counts": "traffic/counts",
        "signals": "traffic/signals",
        "alerts": "traffic/alerts",
        "detections": "traffic/detections",
        "density": "traffic/density",
    }

    def __init__(self, broker_host: str = "", broker_port: int = 1883):
        self._local = InProcessBroker()
        self._mqtt_client = None

        if broker_host:
            self._init_external_mqtt(broker_host, broker_port)

    def _init_external_mqtt(self, host: str, port: int) -> None:
        """Initialize external MQTT client (paho-mqtt)."""
        try:
            import paho.mqtt.client as mqtt
            self._mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            self._mqtt_client.connect(host, port, 60)
            self._mqtt_client.loop_start()
            logger.info("Connected to MQTT broker at %s:%d", host, port)
        except ImportError:
            logger.warning("paho-mqtt not installed — external MQTT disabled")
        except Exception as e:
            logger.warning("Failed to connect to MQTT broker: %s", e)

    async def publish_counts(self, data: dict) -> None:
        """Publish vehicle count data."""
        await self._publish(self.TOPICS["counts"], data)

    async def publish_signals(self, data: dict) -> None:
        """Publish signal state data."""
        await self._publish(self.TOPICS["signals"], data)

    async def publish_alert(self, data: dict) -> None:
        """Publish an alert event."""
        await self._publish(self.TOPICS["alerts"], data)

    async def publish_detection(self, data: dict) -> None:
        """Publish a detection event."""
        await self._publish(self.TOPICS["detections"], data)

    async def publish_density(self, data: dict) -> None:
        """Publish density analysis."""
        await self._publish(self.TOPICS["density"], data)

    async def _publish(self, topic: str, data: Any) -> None:
        """Publish to both local and external brokers."""
        await self._local.publish(topic, data)

        if self._mqtt_client:
            try:
                payload = json.dumps(data) if isinstance(data, (dict, list)) else str(data)
                self._mqtt_client.publish(topic, payload)
            except Exception as e:
                logger.debug("External MQTT publish error: %s", e)

    def subscribe(self, topic: str, callback: Callable) -> None:
        """Subscribe to a topic on the local broker."""
        self._local.subscribe(topic, callback)

    def close(self) -> None:
        """Clean up connections."""
        if self._mqtt_client:
            self._mqtt_client.loop_stop()
            self._mqtt_client.disconnect()
            logger.info("MQTT broker disconnected")


# Singleton
mqtt_bridge = MQTTBridge()

"""
jarvis/smart_home/mqtt.py
=========================
MQTT Protocol Adapter for Smart Home & IoT Sensor / Actuator Telemetry.
Covers Feature:
  - F-27: MQTT Protocol Adapter (Topic publishing & subscription callback routing)
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Union

log = logging.getLogger("jarvis.smart_home.mqtt")

try:
    import paho.mqtt.client as mqtt_client  # type: ignore
except ImportError:
    mqtt_client = None


class MQTTAdapter:
    """MQTT Protocol publisher and subscriber coordinator with mock & paho-mqtt support."""

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: Optional[str] = None,
        keepalive: int = 60,
    ):
        self.host = broker_host
        self.port = broker_port
        self.username = username
        self.password = password
        self.client_id = client_id or f"jarvis_iot_{int(time.time())}"
        self.keepalive = keepalive

        self.is_connected: bool = False
        self._client = None
        self._subscriptions: Dict[str, List[Callable[[str, bytes], None]]] = {}
        self._lock = threading.RLock()

    def connect(self) -> bool:
        """Establishes connection to MQTT broker."""
        if mqtt_client is not None:
            try:
                self._client = mqtt_client.Client(client_id=self.client_id)
                if self.username and self.password:
                    self._client.username_pw_set(self.username, self.password)

                def _on_connect(client, userdata, flags, rc):
                    if rc == 0:
                        self.is_connected = True
                        log.info("Connected successfully to MQTT Broker at %s:%d", self.host, self.port)
                        with self._lock:
                            for topic in self._subscriptions.keys():
                                self._client.subscribe(topic)
                    else:
                        log.warning("MQTT connection returned code %d", rc)

                def _on_message(client, userdata, msg):
                    self._dispatch_message(msg.topic, msg.payload)

                self._client.on_connect = _on_connect
                self._client.on_message = _on_message
                self._client.connect(self.host, self.port, self.keepalive)
                self._client.loop_start()
                self.is_connected = True
                return True
            except Exception as exc:
                log.warning("Failed to connect to physical MQTT broker: %s. Entering offline mode.", exc)

        self.is_connected = True
        return True

    def disconnect(self) -> None:
        """Closes MQTT broker connection."""
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception as exc:
                log.warning("Error disconnecting MQTT: %s", exc)
        self.is_connected = False

    def publish(
        self,
        topic: str,
        payload: Union[str, bytes, Dict[str, Any]],
        qos: int = 0,
        retain: bool = False,
        mock_http: Optional[Any] = None,
    ) -> bool:
        """Publishes payload to target MQTT topic."""
        # Format payload
        if isinstance(payload, dict):
            raw_payload = json.dumps(payload)
        elif isinstance(payload, bytes):
            raw_payload = payload.decode("utf-8", errors="replace")
        else:
            raw_payload = str(payload)

        # 1. Mock Server Interception
        if mock_http is not None and hasattr(mock_http, "mqtt_publish"):
            mock_http.mqtt_publish(topic, raw_payload)
            return True

        # 2. Live Client Publish
        if self._client is not None and self.is_connected:
            try:
                info = self._client.publish(topic, raw_payload.encode("utf-8"), qos=qos, retain=retain)
                return bool(info.rc == 0)
            except Exception as exc:
                log.error("MQTT publish error: %s", exc)
                return False

        # 3. Local Dispatch Fallback
        self._dispatch_message(topic, raw_payload.encode("utf-8"))
        return True

    def subscribe(
        self,
        topic: str,
        callback: Callable[[str, bytes], None],
        qos: int = 0,
        mock_http: Optional[Any] = None,
    ) -> bool:
        """Subscribes callback to MQTT topic."""
        with self._lock:
            if topic not in self._subscriptions:
                self._subscriptions[topic] = []
            self._subscriptions[topic].append(callback)

        if mock_http is not None and hasattr(mock_http, "mqtt_subscribe"):
            mock_http.mqtt_subscribe(topic, callback)
            return True

        if self._client is not None and self.is_connected:
            try:
                self._client.subscribe(topic, qos=qos)
            except Exception as exc:
                log.error("MQTT subscribe error: %s", exc)
                return False

        return True

    def _dispatch_message(self, topic: str, payload_bytes: bytes) -> None:
        """Dispatches inbound message to registered callbacks matching topic."""
        with self._lock:
            for sub_topic, callbacks in self._subscriptions.items():
                if sub_topic == topic or sub_topic == "#" or (sub_topic.endswith("/#") and topic.startswith(sub_topic[:-2])):
                    for cb in callbacks:
                        try:
                            cb(topic, payload_bytes)
                        except Exception as exc:
                            log.error("Error in MQTT callback for topic '%s': %s", topic, exc)

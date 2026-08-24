"""
jarvis.smart_home
=================
Smart Home IoT integration: Home Assistant REST/WebSocket client & MQTT adapter.
"""

from jarvis.smart_home.home_assistant import HomeAssistantClient
from jarvis.smart_home.mqtt import MQTTAdapter

__all__ = [
    "HomeAssistantClient",
    "MQTTAdapter",
]

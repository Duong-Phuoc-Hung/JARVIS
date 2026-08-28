"""
tests/test_smart_home.py
========================
Test Suite for Home Assistant Integration and MQTT IoT Adapter.
Covering:
  - F-26: Home Assistant REST/WS Client (Entity state inspection & service invocations)
  - F-27: MQTT Protocol Adapter (Topic publishing & subscription callback routing)
"""

from typing import Any, Callable, Dict, List, Optional

import pytest

from jarvis.smart_home.home_assistant import HomeAssistantClient
from jarvis.smart_home.mqtt import MQTTAdapter

# ============================================================================
# TIER 1: FEATURE COVERAGE HAPPY PATHS
# ============================================================================

def test_smart_home_ha_turn_on_light_tier1(mock_http_server):
    """
    [F-26] Validate Home Assistant REST client dispatches service call to turn on light with brightness.
    """
    client = HomeAssistantClient()
    res = client.call_service(
        domain="light",
        service="turn_on",
        service_data={"entity_id": "light.living_room", "brightness": 200},
        mock_http=mock_http_server,
    )
    assert res["success"] is True

    # Verify state updated in mock hub
    state = client.get_state("light.living_room", mock_http=mock_http_server)
    assert state["state"] == "on"
    assert state["attributes"]["brightness"] == 200


def test_smart_home_ha_state_query_tier1(mock_http_server):
    """
    [F-26] Validate Home Assistant state query fetches and parses sensor telemetry.
    """
    client = HomeAssistantClient()
    sensor_state = client.get_state("sensor.temperature", mock_http=mock_http_server)
    assert sensor_state is not None
    assert sensor_state["state"] == "24.5"


def test_smart_home_mqtt_publish_and_subscribe_tier1(mock_http_server):
    """
    [F-27] Validate MQTT adapter publishes message to IoT topic and triggers subscription callback.
    """
    adapter = MQTTAdapter()
    received_messages = []

    def on_message(topic: str, payload: bytes):
        received_messages.append((topic, payload.decode("utf-8")))

    adapter.subscribe("home/sensors/power", on_message, mock_http=mock_http_server)
    adapter.publish("home/sensors/power", "145.2W", mock_http=mock_http_server)

    assert len(received_messages) == 1
    assert received_messages[0] == ("home/sensors/power", "145.2W")


def test_smart_home_ha_entity_alias_mapping_tier1(mock_http_server):
    """
    [F-26] Validate entity alias resolution maps natural language names to entity IDs.
    """
    client = HomeAssistantClient()
    assert client.resolve_entity("đèn phòng khách") == "light.living_room"
    assert client.resolve_entity("living room light") == "light.living_room"
    assert client.resolve_entity("ac") == "climate.ac_unit"


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ============================================================================

def test_smart_home_ha_server_unreachable_timeout_tier2():
    """
    [F-26] Validate offline Home Assistant endpoint returns descriptive connection error without crash.
    """
    client = HomeAssistantClient(base_url="http://invalid-ha-host.local:8123")
    res = client.call_service("light", "turn_on", {"entity_id": "light.room"}, mock_http=None)
    assert res["success"] is False
    assert "unreachable" in res["error"].lower()

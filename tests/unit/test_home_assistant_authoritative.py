"""
tests/unit/test_home_assistant_authoritative.py
================================================
Test suite for Task D-10: Home Assistant authoritative write path, security allowlist,
domain isolation, and ActionDispatcher integration.

Ensures:
  1. Authoritative allowlist of domains: light, switch, climate, media_player, fan, sensor.
  2. Strict refusal for security-sensitive domains: lock.*, alarm_control_panel.*, camera.*, siren.*.
  3. No ghost successes or silent fallbacks.
  4. Full integration with ActionDispatcher and JarvisApp.
"""
from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from jarvis.core.app import JarvisApp
from jarvis.smart_home.home_assistant import HomeAssistantClient


class MockHTTPServerDouble:
    """Mock HTTP backend simulating Home Assistant state machine."""

    def __init__(self) -> None:
        self.states: dict[str, dict[str, Any]] = {
            "light.living_room": {"state": "off", "attributes": {"brightness": 0}},
            "light.desk_lamp": {"state": "off", "attributes": {"brightness": 0}},
            "climate.ac_unit": {"state": "cool", "attributes": {"temperature": 25.0}},
            "sensor.temperature": {"state": "24.5", "attributes": {"unit_of_measurement": "°C"}},
            "switch.fan": {"state": "off", "attributes": {}},
        }
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def handle_ha_call_service(
        self, domain: str, service: str, service_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        self.calls.append((domain, service, service_data))
        entity_id = service_data.get("entity_id")
        if entity_id and entity_id in self.states:
            if service == "turn_on":
                self.states[entity_id]["state"] = "on"
                if "brightness" in service_data:
                    self.states[entity_id]["attributes"]["brightness"] = service_data["brightness"]
            elif service == "turn_off":
                self.states[entity_id]["state"] = "off"
            elif service == "set_temperature":
                if "temperature" in service_data:
                    self.states[entity_id]["attributes"]["temperature"] = service_data["temperature"]
        return [{"entity_id": entity_id, "state": self.states.get(entity_id, {}).get("state", "ok")}]

    def handle_ha_get_state(self, entity_id: str) -> dict[str, Any] | None:
        return self.states.get(entity_id)


class TestHomeAssistantSecurityGating(unittest.TestCase):
    """Verifies domain allowlist, blocked prefixes, and input sanitization."""

    def setUp(self) -> None:
        self.client = HomeAssistantClient(access_token="test_token")
        self.mock_http = MockHTTPServerDouble()

    def test_allowed_domains_and_aliases(self) -> None:
        allowed_entities = [
            ("light.living_room", True),
            ("đèn phòng khách", True),
            ("climate.ac_unit", True),
            ("ac", True),
            ("điều hòa", True),
            ("sensor.temperature", True),
            ("switch.fan", True),
            ("media_player.living_room_tv", True),
            ("fan.bedroom", True),
        ]
        for ent, expected in allowed_entities:
            with self.subTest(entity=ent):
                ok, err = self.client.validate_entity_allowed(ent)
                self.assertEqual(ok, expected, f"Expected {ent} to be allowed, error: {err}")

    def test_disallowed_security_entities_refused(self) -> None:
        disallowed_entities = [
            "lock.front_door",
            "lock.back_door",
            "alarm_control_panel.home",
            "camera.driveway",
            "siren.alarm",
            "valve.gas_main",
            "vacuum.robot",
        ]
        for ent in disallowed_entities:
            with self.subTest(entity=ent):
                ok, err = self.client.validate_entity_allowed(ent)
                self.assertFalse(ok)
                self.assertIn("SECURITY_REFUSAL", err)

    def test_unknown_domain_refused(self) -> None:
        unknown_entities = [
            "garage_door.main",
            "custom_device.hack",
            "script.run_all",
            "shell_command.reboot",
        ]
        for ent in unknown_entities:
            with self.subTest(entity=ent):
                ok, err = self.client.validate_entity_allowed(ent)
                self.assertFalse(ok)
                self.assertIn("SECURITY_REFUSAL", err)

    def test_malformed_and_injection_entities_refused(self) -> None:
        malicious_inputs = [
            "light.room; rm -rf /",
            "light.living_room && whoami",
            "light.room | cat /etc/passwd",
            "light.room\nmalicious",
            "nodotsinthisname",
            "",
        ]
        for ent in malicious_inputs:
            with self.subTest(entity=ent):
                ok, err = self.client.validate_entity_allowed(ent)
                self.assertFalse(ok)

    def test_call_service_enforces_domain_and_entity_policy(self) -> None:
        # Refused domain
        res = self.client.call_service(
            domain="lock",
            service="unlock",
            service_data={"entity_id": "lock.front_door"},
            mock_http=self.mock_http,
        )
        self.assertFalse(res["success"])
        self.assertIn("SECURITY_REFUSAL", res["error"])
        self.assertEqual(len(self.mock_http.calls), 0)

        # Refused entity inside allowed domain
        res = self.client.call_service(
            domain="light",
            service="turn_on",
            service_data={"entity_id": "camera.backyard"},
            mock_http=self.mock_http,
        )
        self.assertFalse(res["success"])
        self.assertIn("SECURITY_REFUSAL", res["error"])
        self.assertEqual(len(self.mock_http.calls), 0)

    def test_turn_on_and_set_temperature_authoritative_execution(self) -> None:
        # Turn on light with brightness
        res = self.client.turn_on("đèn phòng khách", brightness=180, mock_http=self.mock_http)
        self.assertTrue(res["success"])
        self.assertEqual(len(self.mock_http.calls), 1)
        self.assertEqual(self.mock_http.calls[0][0], "light")
        self.assertEqual(self.mock_http.calls[0][1], "turn_on")
        self.assertEqual(self.mock_http.calls[0][2]["entity_id"], "light.living_room")
        self.assertEqual(self.mock_http.calls[0][2]["brightness"], 180)

        # Set temperature
        res = self.client.set_temperature("ac", 22.0, mock_http=self.mock_http)
        self.assertTrue(res["success"])
        self.assertEqual(len(self.mock_http.calls), 2)
        self.assertEqual(self.mock_http.calls[1][0], "climate")
        self.assertEqual(self.mock_http.calls[1][1], "set_temperature")
        self.assertEqual(self.mock_http.calls[1][2]["entity_id"], "climate.ac_unit")
        self.assertEqual(self.mock_http.calls[1][2]["temperature"], 22.0)

    def test_get_state_refuses_restricted_entities(self) -> None:
        self.assertIsNone(self.client.get_state("lock.front_door", mock_http=self.mock_http))
        state = self.client.get_state("sensor.temperature", mock_http=self.mock_http)
        self.assertIsNotNone(state)
        self.assertEqual(state["state"], "24.5")


class TestJarvisAppHomeAssistantIntegration(unittest.TestCase):
    """Verifies that ActionDispatcher in JarvisApp authoritatively handles HA actions."""

    def setUp(self) -> None:
        self.app = JarvisApp(headless=True, no_hot_reload=True)
        self.app.initialize()
        self.mock_http = MockHTTPServerDouble()

    def tearDown(self) -> None:
        self.app.stop()

    def test_ha_actions_registered_in_dispatcher(self) -> None:
        expected_actions = [
            "home_assistant_call",
            "smart_home_turn_on",
            "smart_home_turn_off",
            "smart_home_set_temp",
            "smart_home_get_state",
        ]
        for act in expected_actions:
            with self.subTest(action=act):
                self.assertIsNotNone(
                    self.app.dispatcher.get_action(act),
                    f"Action '{act}' must be registered in ActionDispatcher",
                )

    def test_dispatcher_home_assistant_call_success(self) -> None:
        with patch.object(self.app.ha_client, "call_service", return_value={"success": True, "result": "ok"}) as mock_cs:
            res = self.app.dispatcher.dispatch_action(
                "home_assistant_call",
                payload={"domain": "light", "service": "turn_on", "entity_id": "light.living_room"},
            )
            self.assertTrue(res.success)
            mock_cs.assert_called_once_with("light", "turn_on", {"entity_id": "light.living_room"})

    def test_dispatcher_home_assistant_call_refuses_restricted_entity(self) -> None:
        res = self.app.dispatcher.dispatch_action(
            "home_assistant_call",
            payload={"domain": "lock", "service": "unlock", "entity_id": "lock.front_door"},
        )
        self.assertFalse(res.success)
        self.assertIn("SECURITY_REFUSAL", res.error)

    def test_dispatcher_smart_home_turn_on_and_off(self) -> None:
        with patch.object(self.app.ha_client, "turn_on", return_value={"success": True}) as mock_to:
            res = self.app.dispatcher.dispatch_action(
                "smart_home_turn_on",
                payload={"entity": "đèn phòng khách", "brightness": 150},
            )
            self.assertTrue(res.success)
            mock_to.assert_called_once_with("đèn phòng khách", brightness=150)

        with patch.object(self.app.ha_client, "turn_off", return_value={"success": True}) as mock_toff:
            res = self.app.dispatcher.dispatch_action(
                "smart_home_turn_off",
                payload={"entity": "desk_lamp"},
            )
            self.assertTrue(res.success)
            mock_toff.assert_called_once_with("desk_lamp")

    def test_dispatcher_smart_home_set_temp(self) -> None:
        with patch.object(self.app.ha_client, "set_temperature", return_value={"success": True}) as mock_st:
            res = self.app.dispatcher.dispatch_action(
                "smart_home_set_temp",
                payload={"entity": "điều hòa", "temperature": 24.5},
            )
            self.assertTrue(res.success)
            mock_st.assert_called_once_with("điều hòa", 24.5)

    def test_dispatcher_smart_home_get_state(self) -> None:
        with patch.object(
            self.app.ha_client, "get_state", return_value={"state": "24.5", "attributes": {}}
        ) as mock_gs:
            res = self.app.dispatcher.dispatch_action(
                "smart_home_get_state",
                payload={"entity": "sensor.temperature"},
            )
            self.assertTrue(res.success)
            self.assertEqual(res.data["state"]["state"], "24.5")
            mock_gs.assert_called_once_with("sensor.temperature")


if __name__ == "__main__":
    unittest.main()

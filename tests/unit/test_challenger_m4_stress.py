"""
tests/unit/test_challenger_m4_stress.py
======================================
Adversarial challenge and stress harness for Milestone M4:
Safety Classifier High-Risk Expansion.

Empirically tests:
1. Gating of smart_home_turn_on without token -> CONFIRMATION_REQUIRED, 0 actuation.
2. Valid token confirmation -> actuation succeeds.
3. smart_home_get_state -> direct execution without confirmation.
4. Comprehensive coverage of all outbound communication actions (Email, Zalo, Discord).
5. Comprehensive coverage of all Home Assistant actuation vs read-only queries.
6. Adversarial token binding: unconfirmed token, invalid token, cross-action replay,
   cross-payload tampering, double-spending (one-shot consumption), and rejected token.
7. Case and whitespace variations.
"""
from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock

from jarvis.automation.safety_gate import SafetyGate
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import ActionResult
from jarvis.planner.safety_interceptor import SafetyGateInterceptor


class TestChallengerM4StressHarness(unittest.TestCase):
    """Adversarial stress harness for M4 Safety Classifier High-Risk Expansion."""

    def setUp(self) -> None:
        self.event_bus = EventBus()
        self.gate = SafetyGate(timeout_seconds=5.0)
        self.interceptor = SafetyGateInterceptor(safety_gate=self.gate, timeout_seconds=5.0)
        self.dispatcher = ActionDispatcher(
            event_bus=self.event_bus,
            safety_interceptor=self.interceptor,
        )
        self.execution_log: list[dict[str, Any]] = []

    def _make_handler(self, name: str):
        def _handler(**kwargs):
            self.execution_log.append({"action": name, "kwargs": kwargs})
            return {"status": "success", "action": name, "echo": kwargs}
        return _handler

    # ----------------------------------------------------------------------
    # Core Requirement 1: smart_home_turn_on without token
    # ----------------------------------------------------------------------
    def test_smart_home_turn_on_without_token_blocks_actuation(self) -> None:
        act = "smart_home_turn_on"
        self.dispatcher.register_action(act, self._make_handler(act))
        payload = {"entity": "light.living_room", "brightness": 255}

        res = self.dispatcher.dispatch_action(act, payload=payload)

        self.assertFalse(res.success, "Must return success=False when unconfirmed")
        self.assertEqual(res.error_code, "CONFIRMATION_REQUIRED")
        self.assertIn("confirmation_token", res.data)
        token = res.data["confirmation_token"]
        self.assertTrue(token, "Must issue a non-empty confirmation token")
        self.assertEqual(
            self.execution_log, [],
            "CRITICAL: Underlying handler MUST NOT be executed when unconfirmed!"
        )

    # ----------------------------------------------------------------------
    # Core Requirement 2: confirming with valid token allows actuation
    # ----------------------------------------------------------------------
    def test_smart_home_turn_on_with_confirmed_token_actuates(self) -> None:
        act = "smart_home_turn_on"
        self.dispatcher.register_action(act, self._make_handler(act))
        payload = {"entity": "light.living_room", "brightness": 255}

        # Step 1: Initial dispatch generates token
        res_gated = self.dispatcher.dispatch_action(act, payload=payload)
        token = res_gated.data["confirmation_token"]

        # Step 2: Affirmative confirmation
        confirmed = self.interceptor.confirm(token)
        self.assertTrue(confirmed, "Safety interceptor must successfully confirm pending token")

        # Step 3: Re-dispatch with confirmed token
        res_exec = self.dispatcher.dispatch_action(act, payload=payload, confirmation_token=token)
        self.assertTrue(res_exec.success, "Must succeed with valid confirmed token")
        self.assertEqual(len(self.execution_log), 1, "Handler must be executed exactly once")
        self.assertEqual(self.execution_log[0]["action"], act)
        self.assertEqual(self.execution_log[0]["kwargs"], payload)

    # ----------------------------------------------------------------------
    # Core Requirement 3: smart_home_get_state executes directly
    # ----------------------------------------------------------------------
    def test_smart_home_get_state_executes_directly_without_confirmation(self) -> None:
        act = "smart_home_get_state"
        self.dispatcher.register_action(act, self._make_handler(act))
        payload = {"entity": "sensor.living_room_temp"}

        res = self.dispatcher.dispatch_action(act, payload=payload)

        self.assertTrue(res.success, "Read-only smart home state must execute immediately")
        self.assertEqual(len(self.execution_log), 1)
        self.assertEqual(self.execution_log[0]["action"], act)

    # ----------------------------------------------------------------------
    # Requirement 4: All Outbound Communication Actions Gated
    # ----------------------------------------------------------------------
    def test_all_outbound_communications_gated(self) -> None:
        comm_actions = [
            # Email
            "email_send", "send_email", "send_mail", "email_send_message",
            # Zalo
            "zalo_send_message", "zalo_send_image", "send_zalo_message", "zalo_broadcast",
            # Discord
            "discord_send_message", "discord_send_file", "send_discord_message",
        ]
        for act in comm_actions:
            with self.subTest(action=act):
                self.dispatcher.register_action(act, self._make_handler(act))
                res = self.dispatcher.dispatch_action(act, payload={"msg": "test", "to": "recipient"})
                self.assertFalse(res.success, f"Action '{act}' must require confirmation")
                self.assertEqual(res.error_code, "CONFIRMATION_REQUIRED")
                self.assertIn("confirmation_token", res.data)
        self.assertEqual(self.execution_log, [], "No communication handler must have executed")

    # ----------------------------------------------------------------------
    # Requirement 5: All Home Assistant Actuation Gated & Read-Only Ungated
    # ----------------------------------------------------------------------
    def test_all_home_assistant_actuation_actions_gated(self) -> None:
        ha_actuations = [
            "home_assistant_call",
            "smart_home_turn_on",
            "smart_home_turn_off",
            "smart_home_set_temp",
            "smart_home_toggle",
            "home_assistant_turn_on",
            "home_assistant_turn_off",
            "home_assistant_toggle",
            "home_assistant_set_temp",
            "home_assistant_set_temperature",
        ]
        for act in ha_actuations:
            with self.subTest(action=act):
                self.dispatcher.register_action(act, self._make_handler(act))
                res = self.dispatcher.dispatch_action(act, payload={"entity": "switch.heater"})
                self.assertFalse(res.success, f"Actuation '{act}' must require confirmation")
                self.assertEqual(res.error_code, "CONFIRMATION_REQUIRED")
                self.assertIn("confirmation_token", res.data)
        self.assertEqual(self.execution_log, [], "No actuation handler must have executed")

    def test_read_only_home_assistant_queries_ungated(self) -> None:
        ha_queries = [
            "smart_home_get_state",
            "smart_home_status",
            "smart_home_query",
            "smart_home_read",
            "home_assistant_get_state",
            "home_assistant_status",
            "home_assistant_get_temperature",
        ]
        for act in ha_queries:
            with self.subTest(action=act):
                self.dispatcher.register_action(act, self._make_handler(act))
                res = self.dispatcher.dispatch_action(act, payload={"entity": "sensor.temp"})
                self.assertTrue(res.success, f"Read-only query '{act}' must not be gated")
        self.assertEqual(len(self.execution_log), len(ha_queries))

    # ----------------------------------------------------------------------
    # Requirement 6: Adversarial Security & Anti-Bypass Testing
    # ----------------------------------------------------------------------
    def test_unconfirmed_token_rejected(self) -> None:
        act = "smart_home_turn_on"
        self.dispatcher.register_action(act, self._make_handler(act))
        payload = {"entity": "light.porch"}

        res_gated = self.dispatcher.dispatch_action(act, payload=payload)
        token = res_gated.data["confirmation_token"]

        # Attempt to dispatch without calling confirm(token)
        res_exec = self.dispatcher.dispatch_action(act, payload=payload, confirmation_token=token)
        self.assertFalse(res_exec.success)
        self.assertEqual(res_exec.error_code, "CONFIRMATION_NOT_CONFIRMED")
        self.assertEqual(self.execution_log, [])

    def test_invalid_arbitrary_token_rejected(self) -> None:
        act = "smart_home_turn_on"
        self.dispatcher.register_action(act, self._make_handler(act))
        payload = {"entity": "light.porch"}

        res = self.dispatcher.dispatch_action(act, payload=payload, confirmation_token="MALICIOUS_TOKEN_999")
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "CONFIRMATION_UNKNOWN_TOKEN")
        self.assertEqual(self.execution_log, [])

    def test_cross_action_token_replay_rejected(self) -> None:
        """Token generated for action A cannot be used to execute action B."""
        self.dispatcher.register_action("smart_home_turn_on", self._make_handler("smart_home_turn_on"))
        self.dispatcher.register_action("email_send", self._make_handler("email_send"))
        payload = {"target": "foo"}

        res_gated = self.dispatcher.dispatch_action("smart_home_turn_on", payload=payload)
        token = res_gated.data["confirmation_token"]
        self.interceptor.confirm(token)

        # Attacker tries to use the confirmed token to send an email!
        res_attack = self.dispatcher.dispatch_action("email_send", payload=payload, confirmation_token=token)
        self.assertFalse(res_attack.success, "Cross-action replay must be rejected")
        self.assertEqual(res_attack.error_code, "CONFIRMATION_ACTION_MISMATCH")
        self.assertEqual(self.execution_log, [])

    def test_cross_payload_tampering_rejected(self) -> None:
        """Token confirmed for entity A cannot be used to actuate entity B."""
        act = "smart_home_turn_on"
        self.dispatcher.register_action(act, self._make_handler(act))
        payload_safe = {"entity": "light.hallway"}
        payload_dangerous = {"entity": "siren.alarm_speaker"}

        res_gated = self.dispatcher.dispatch_action(act, payload=payload_safe)
        token = res_gated.data["confirmation_token"]
        self.interceptor.confirm(token)

        # Attacker tampers with the payload
        res_attack = self.dispatcher.dispatch_action(act, payload=payload_dangerous, confirmation_token=token)
        self.assertFalse(res_attack.success, "Tampered payload must be rejected")
        self.assertEqual(res_attack.error_code, "CONFIRMATION_PAYLOAD_MISMATCH")
        self.assertEqual(self.execution_log, [])

    def test_double_spending_token_rejected(self) -> None:
        """A confirmed token must be one-shot consumed and cannot be reused."""
        act = "smart_home_turn_on"
        self.dispatcher.register_action(act, self._make_handler(act))
        payload = {"entity": "light.desk"}

        res_gated = self.dispatcher.dispatch_action(act, payload=payload)
        token = res_gated.data["confirmation_token"]
        self.interceptor.confirm(token)

        # First use succeeds
        res_1 = self.dispatcher.dispatch_action(act, payload=payload, confirmation_token=token)
        self.assertTrue(res_1.success)
        self.assertEqual(len(self.execution_log), 1)

        # Second use with same token must fail!
        res_2 = self.dispatcher.dispatch_action(act, payload=payload, confirmation_token=token)
        self.assertFalse(res_2.success, "Token reuse / double-spending must be blocked")
        self.assertEqual(res_2.error_code, "CONFIRMATION_ALREADY_CONSUMED")
        self.assertEqual(len(self.execution_log), 1, "Handler must NOT have run a second time")

    def test_rejected_token_blocks_actuation(self) -> None:
        act = "smart_home_turn_on"
        self.dispatcher.register_action(act, self._make_handler(act))
        payload = {"entity": "light.desk"}

        res_gated = self.dispatcher.dispatch_action(act, payload=payload)
        token = res_gated.data["confirmation_token"]
        # Explicit rejection
        self.interceptor.reject(token)

        res_exec = self.dispatcher.dispatch_action(act, payload=payload, confirmation_token=token)
        self.assertFalse(res_exec.success)
        self.assertEqual(res_exec.error_code, "CONFIRMATION_REJECTED")
        self.assertEqual(self.execution_log, [])

    def test_casing_and_whitespace_normalization(self) -> None:
        """Adversarial action names with uppercase and whitespace cannot bypass safety gate."""
        variations = [
            "SMART_HOME_TURN_ON",
            "Smart_Home_Turn_On",
            "  smart_home_turn_on  ",
            "EMAIL_SEND",
            "  send_email  ",
        ]
        for act in variations:
            with self.subTest(action=act):
                self.dispatcher.register_action(act, self._make_handler(act))
                res = self.dispatcher.dispatch_action(act, payload={"entity": "light.1"})
                self.assertFalse(res.success, f"Action variation '{act}' must not bypass gate")
                self.assertEqual(res.error_code, "CONFIRMATION_REQUIRED")


if __name__ == "__main__":
    unittest.main()

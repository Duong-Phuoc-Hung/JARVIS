"""
Adversarial Stress-Testing and Verification Suite for Milestone M4:
Safety Classifier High-Risk Expansion & Confirmation Lifecycle.

Author: Empirical Challenger Subagent (teamwork_preview_challenger_m4_1)
Standards: AGENTS.md (Fail-Closed, Anti-Fabrication, Seam-First TDD)
"""
from __future__ import annotations

import time
import unittest
from typing import Any

from jarvis.automation.safety_gate import SafetyGate
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import PrivilegeLevel, RequesterContext
from jarvis.planner.safety_interceptor import SafetyGateInterceptor


class TestSafetyClassifierCaseInsensitivity(unittest.TestCase):
    """
    Stress-tests case-insensitivity and formatting variations in action names.
    Attack scenario: Attacker or dynamic caller supplies uppercase or mixed-case
    action names (e.g. 'EMAIL_SEND', 'Home_Assistant_Call', 'Zalo_Send_Message')
    attempting to evade high-risk safety gating.
    """

    def setUp(self) -> None:
        self.gate = SafetyGate(timeout_seconds=30.0)
        self.interceptor = SafetyGateInterceptor(safety_gate=self.gate)
        self.dispatcher = ActionDispatcher(safety_interceptor=self.interceptor)
        self.executed_actions: list[str] = []

    def _make_handler(self, name: str):
        def _handler(**kwargs):
            self.executed_actions.append(name)
            return {"status": "ok", "action": name, **kwargs}
        return _handler

    def test_uppercase_and_mixed_case_is_high_risk(self) -> None:
        test_actions = [
            # Outbound Email
            "EMAIL_SEND", "Email_Send", "email_SEND", "SEND_EMAIL", "Send_Email",
            "EMAIL_SEND_MESSAGE", "Email_Send_Message", "SEND_MAIL", "Send_Mail",
            # Outbound Zalo
            "ZALO_SEND_MESSAGE", "Zalo_Send_Message", "zalo_SEND_message",
            "ZALO_SEND_IMAGE", "Zalo_Send_Image", "SEND_ZALO_MESSAGE", "ZALO_BROADCAST",
            # Outbound Discord
            "DISCORD_SEND_MESSAGE", "Discord_Send_Message", "DISCORD_SEND_FILE", "SEND_DISCORD_MESSAGE",
            # Home Assistant Actuation
            "HOME_ASSISTANT_CALL", "Home_Assistant_Call", "home_ASSISTANT_call",
            "SMART_HOME_TURN_ON", "Smart_Home_Turn_On", "SMART_HOME_TURN_OFF",
            "SMART_HOME_SET_TEMP", "Smart_Home_Set_Temp", "SMART_HOME_TOGGLE",
            "HOME_ASSISTANT_TURN_ON", "HOME_ASSISTANT_TURN_OFF", "HOME_ASSISTANT_SET_TEMPERATURE",
            # Traditional Destructive Operations
            "FILE_DELETE", "Delete_File", "SYSTEM_SHUTDOWN", "System_Shutdown",
        ]

        for act in test_actions:
            with self.subTest(action=act):
                self.assertTrue(
                    self.interceptor.is_high_risk(act, {}),
                    f"Action '{act}' must be classified as high risk regardless of casing",
                )

    def test_whitespace_padded_action_names(self) -> None:
        padded_actions = [
            "  email_send  ",
            " \tEMAIL_SEND\n ",
            "  Home_Assistant_Call  ",
            "  Zalo_Send_Message  ",
            "  smart_home_turn_on  ",
        ]
        for act in padded_actions:
            with self.subTest(action=repr(act)):
                self.assertTrue(
                    self.interceptor.is_high_risk(act, {}),
                    f"Padded action '{act}' must be classified as high risk after strip()",
                )

    def test_dispatcher_gating_case_insensitivity(self) -> None:
        """Verifies that ActionDispatcher gates uppercase and mixed-case high-risk actions."""
        test_cases = [
            ("EMAIL_SEND", {"to": "victim@example.com", "body": "leak"}),
            ("Home_Assistant_Call", {"service": "lock.unlock", "entity": "front_door"}),
            ("Zalo_Send_Message", {"user_id": "u999", "text": "spam"}),
            ("DISCORD_SEND_MESSAGE", {"channel_id": 999, "content": "broadcast"}),
            ("Smart_Home_Turn_On", {"entity": "switch.heater"}),
        ]

        for act, payload in test_cases:
            with self.subTest(action=act):
                self.dispatcher.register_action(act, self._make_handler(act))
                res = self.dispatcher.dispatch_action(act, payload=payload)
                self.assertFalse(res.success, f"Action '{act}' must NOT execute unconfirmed")
                self.assertEqual(res.error_code, "CONFIRMATION_REQUIRED")
                self.assertIn("confirmation_token", res.data)
                self.assertEqual(self.executed_actions, [], f"Handler for '{act}' executed without confirmation")


class TestSafetyClassifierReadOnlyUngated(unittest.TestCase):
    """
    Empirically verifies that read-only actions and queries are NEVER falsely gated.
    Ensures safe operations remain non-blocking for high voice-assistant responsiveness.
    """

    def setUp(self) -> None:
        self.gate = SafetyGate(timeout_seconds=30.0)
        self.interceptor = SafetyGateInterceptor(safety_gate=self.gate)
        self.dispatcher = ActionDispatcher(safety_interceptor=self.interceptor)
        self.executed_actions: list[str] = []

    def _make_handler(self, name: str):
        def _handler(**kwargs):
            self.executed_actions.append(name)
            return {"status": "ok", "action": name, "result": "safe_data"}
        return _handler

    def test_read_only_actions_not_high_risk(self) -> None:
        safe_actions = [
            "smart_home_get_state",
            "SMART_HOME_GET_STATE",
            "sensor_status",
            "SENSOR_STATUS",
            "email_read",
            "EMAIL_READ",
            "read_email",
            "home_assistant_get_state",
            "home_assistant_status",
            "weather_query",
            "system_status",
            "device_status",
            "battery_status",
            "smart_home_query",
            "zalo_read",
            "discord_read",
            "smart_home_get_temperature",
        ]

        for act in safe_actions:
            with self.subTest(action=act):
                self.assertFalse(
                    self.interceptor.is_high_risk(act, {}),
                    f"Read-only action '{act}' must NOT be classified as high risk",
                )

    def test_dispatcher_executes_read_only_directly(self) -> None:
        safe_cases = [
            ("smart_home_get_state", {"entity": "sensor.living_room_temperature"}),
            ("sensor_status", {"sensor_id": "temp_01"}),
            ("email_read", {"folder": "inbox", "limit": 5}),
            ("home_assistant_get_state", {"entity": "binary_sensor.motion"}),
        ]

        for act, payload in safe_cases:
            with self.subTest(action=act):
                self.dispatcher.register_action(act, self._make_handler(act))
                res = self.dispatcher.dispatch_action(act, payload=payload)
                self.assertTrue(res.success, f"Safe action '{act}' should execute without gating")
                self.assertIsNone(res.error_code)
                self.assertEqual(res.data, {"status": "ok", "action": act, "result": "safe_data"})
                self.assertIn(act, self.executed_actions)


class TestTokenVerificationSecurityFailClosed(unittest.TestCase):
    """
    Stress-tests token verification lifecycle, token tampering, expiration,
    action/payload binding, replay defense, and fail-closed guarantees.
    """

    def setUp(self) -> None:
        self.gate = SafetyGate(timeout_seconds=30.0)
        self.interceptor = SafetyGateInterceptor(safety_gate=self.gate)
        self.dispatcher = ActionDispatcher(safety_interceptor=self.interceptor)
        self.executed_actions: list[str] = []

    def _make_handler(self, name: str):
        def _handler(**kwargs):
            self.executed_actions.append(name)
            return {"status": "ok", "action": name, **kwargs}
        return _handler

    def test_invalid_and_malformed_tokens(self) -> None:
        act = "email_send"
        payload = {"to": "someone@example.com", "body": "test"}
        self.dispatcher.register_action(act, self._make_handler(act))

        # Empty token is falsy in Python -> treated as no token provided -> CONFIRMATION_REQUIRED
        empty_res = self.dispatcher.dispatch_action(act, payload=payload, confirmation_token="")
        self.assertFalse(empty_res.success)
        self.assertEqual(empty_res.error_code, "CONFIRMATION_REQUIRED")
        self.assertEqual(self.executed_actions, [])

        bogus_tokens = [
            "BOGUS123",
            "NONEXIST",
            "   ",
            "../../../etc",
            "00000000",
            "X" * 64,
        ]

        for bogus in bogus_tokens:
            with self.subTest(token=bogus):
                res = self.dispatcher.dispatch_action(act, payload=payload, confirmation_token=bogus)
                self.assertFalse(res.success)
                self.assertEqual(res.error_code, "CONFIRMATION_UNKNOWN_TOKEN")
                self.assertEqual(self.executed_actions, [])

    @unittest.expectedFailure
    def test_replay_defense_case_variation(self) -> None:
        """
        Adversarial scenario: Attacker tries to replay a consumed token by altering its case
        (e.g., lowercase in call 1, uppercase in call 2).
        Known finding: SafetyGateInterceptor._consumed_tokens stores raw token instead of
        token.strip().upper(), allowing case-variation replay until normalized.
        """
        act = "email_send"
        payload = {"to": "finance@corp.com", "body": "pay"}
        self.dispatcher.register_action(act, self._make_handler(act))

        res1 = self.dispatcher.dispatch_action(act, payload=payload)
        token = res1.data["confirmation_token"]
        self.assertTrue(self.interceptor.confirm(token))

        # First execution using lowercase token
        exec1 = self.dispatcher.dispatch_action(act, payload=payload, confirmation_token=token.lower())
        self.assertTrue(exec1.success)
        self.assertEqual(self.executed_actions, [act])

        # Second execution (replay) using uppercase token
        exec2 = self.dispatcher.dispatch_action(act, payload=payload, confirmation_token=token.upper())
        # Let's see if exec2 succeeds or is blocked!
        self.assertFalse(exec2.success, "Replay attack with case variation must be blocked!")
        self.assertEqual(exec2.error_code, "CONFIRMATION_ALREADY_CONSUMED")
        self.assertEqual(self.executed_actions, [act], "Handler must NOT be called on case-altered replay")


    def test_unconfirmed_pending_token_rejected(self) -> None:
        """Token generated but user never confirmed."""
        act = "email_send"
        payload = {"to": "partner@example.com", "body": "deal"}
        self.dispatcher.register_action(act, self._make_handler(act))

        # Gate action to generate token
        gate_res = self.dispatcher.dispatch_action(act, payload=payload)
        token = gate_res.data["confirmation_token"]
        self.assertTrue(token)

        # Attempt to dispatch using the unconfirmed token
        res = self.dispatcher.dispatch_action(act, payload=payload, confirmation_token=token)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "CONFIRMATION_NOT_CONFIRMED")
        self.assertEqual(self.executed_actions, [])

    def test_rejected_token_rejected(self) -> None:
        """Token explicitly rejected by user."""
        act = "zalo_send_message"
        payload = {"user_id": "u456", "text": "confidential"}
        self.dispatcher.register_action(act, self._make_handler(act))

        gate_res = self.dispatcher.dispatch_action(act, payload=payload)
        token = gate_res.data["confirmation_token"]

        # Reject token
        rejected = self.interceptor.reject(token)
        self.assertTrue(rejected)

        # Attempt to dispatch
        res = self.dispatcher.dispatch_action(act, payload=payload, confirmation_token=token)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "CONFIRMATION_REJECTED")
        self.assertEqual(self.executed_actions, [])

    def test_expired_token_rejected(self) -> None:
        """Token expired past its timeout window."""
        act = "discord_send_message"
        payload = {"channel_id": 111, "content": "ping"}
        self.dispatcher.register_action(act, self._make_handler(act))

        gate_res = self.dispatcher.dispatch_action(act, payload=payload)
        token = gate_res.data["confirmation_token"]

        # Simulate expiration
        entry = self.gate.get_pending(token)
        self.assertIsNotNone(entry)
        entry.expires_at = time.time() - 5.0  # already expired

        # Attempt to confirm expired token -> should fail
        confirmed = self.interceptor.confirm(token)
        self.assertFalse(confirmed)

        # Attempt dispatch with expired token -> should be blocked
        res = self.dispatcher.dispatch_action(act, payload=payload, confirmation_token=token)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "CONFIRMATION_EXPIRED")
        self.assertEqual(self.executed_actions, [])

    def test_action_mismatch_cross_execution_attack(self) -> None:
        """
        Token authorized for Action A cannot be reused to execute Action B.
        Scenario: Token confirmed for 'email_send' attempted on 'zalo_send_message'.
        """
        self.dispatcher.register_action("email_send", self._make_handler("email_send"))
        self.dispatcher.register_action("zalo_send_message", self._make_handler("zalo_send_message"))

        # Gate and confirm token for email_send
        email_payload = {"to": "ceo@corp.com", "text": "hello"}
        res1 = self.dispatcher.dispatch_action("email_send", payload=email_payload)
        token = res1.data["confirmation_token"]
        self.assertTrue(self.interceptor.confirm(token))

        # Attempt to use email token for zalo_send_message
        attack_res = self.dispatcher.dispatch_action(
            "zalo_send_message",
            payload=email_payload,
            confirmation_token=token,
        )
        self.assertFalse(attack_res.success)
        self.assertEqual(attack_res.error_code, "CONFIRMATION_ACTION_MISMATCH")
        self.assertEqual(self.executed_actions, [])

    def test_payload_mismatch_parameter_tampering_attack(self) -> None:
        """
        Token authorized for payload X cannot execute modified payload Y.
        Scenario: Token authorized to send email to 'trusted@corp.com',
        attacker tampers recipient to 'adversary@evil.com'.
        """
        act = "email_send"
        self.dispatcher.register_action(act, self._make_handler(act))

        orig_payload = {"to": "trusted@corp.com", "body": "Quarterly Report"}
        res = self.dispatcher.dispatch_action(act, payload=orig_payload)
        token = res.data["confirmation_token"]
        self.assertTrue(self.interceptor.confirm(token))

        # Attacker tampers recipient
        tampered_payload = {"to": "adversary@evil.com", "body": "Quarterly Report"}
        tampered_res = self.dispatcher.dispatch_action(act, payload=tampered_payload, confirmation_token=token)
        self.assertFalse(tampered_res.success)
        self.assertEqual(tampered_res.error_code, "CONFIRMATION_PAYLOAD_MISMATCH")
        self.assertEqual(self.executed_actions, [])

    def test_replay_defense_one_shot_token_consumption(self) -> None:
        """
        A confirmed token must only be usable once.
        Subsequent execution attempts with the same token must fail.
        """
        act = "home_assistant_call"
        payload = {"service": "switch.turn_off", "entity": "switch.server_power"}
        self.dispatcher.register_action(act, self._make_handler(act))

        res1 = self.dispatcher.dispatch_action(act, payload=payload)
        token = res1.data["confirmation_token"]
        self.assertTrue(self.interceptor.confirm(token))

        # Execution 1: Must succeed
        exec1 = self.dispatcher.dispatch_action(act, payload=payload, confirmation_token=token)
        self.assertTrue(exec1.success)
        self.assertEqual(self.executed_actions, [act])

        # Execution 2 (Replay): Must be blocked
        exec2 = self.dispatcher.dispatch_action(act, payload=payload, confirmation_token=token)
        self.assertFalse(exec2.success)
        self.assertEqual(exec2.error_code, "CONFIRMATION_ALREADY_CONSUMED")
        self.assertEqual(self.executed_actions, [act], "Handler must NOT be called on token replay")


if __name__ == "__main__":
    unittest.main()

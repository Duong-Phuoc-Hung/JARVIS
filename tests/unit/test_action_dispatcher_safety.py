"""
tests/unit/test_action_dispatcher_safety.py
=============================================
Deterministic regression tests for JARVIS Phase 2 centralized safety-layer
hardening: ActionDispatcher's destructive-action confirmation gate
(jarvis/core/dispatcher.py's _evaluate_safety_gate()), the shared
SafetyGateInterceptor classifier/binding layer (jarvis/planner/safety_interceptor.py),
and the ReAct planner's PlanMode-independent high-risk interception
(jarvis/planner/engine.py).

Background: previously, only jarvis.planner.engine.ReActTaskEngine gated
high-risk TaskNodes, and only when explicitly run in PlanMode.SAFETY_GATE --
the real production caller always used the default PlanMode.FULLY_AUTONOMOUS,
so gating was effectively dead in production. ActionDispatcher, the actual
choke point for intent-routed commands, skills, Telegram, and GUIActor's
semantic call boundary (vision_click_ui/vision_type_ui), had no destructive-
action awareness at all. This file proves the corrected, centralized state
machine: ActionDispatcher.dispatch_action()/dispatch_action_async() gate any
action the shared SafetyGateInterceptor classifies as high-risk -- including
deterministically-recognized OS shutdown/reboot/sleep actions, independent of
any LLM/router-supplied confirmation flag -- and a confirmation token is
bound to the exact (action_name, payload) pair, one-shot, and rejected after
expiry/rejection/mismatch/replay.
"""
from __future__ import annotations

import asyncio
import unittest

from jarvis.automation.safety_gate import SafetyGate
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import PrivilegeLevel, RequesterContext
from jarvis.planner.dag import TaskDAG
from jarvis.planner.engine import ReActTaskEngine
from jarvis.planner.models import PlanMode, StepStatus, TaskNode
from jarvis.planner.reflection import SelfReflectionEngine
from jarvis.planner.safety_interceptor import SafetyGateInterceptor


def _make_dispatcher(timeout_seconds: float = 5.0, bypass_security: bool = False) -> tuple[ActionDispatcher, SafetyGateInterceptor, SafetyGate]:
    gate = SafetyGate(timeout_seconds=timeout_seconds)
    interceptor = SafetyGateInterceptor(safety_gate=gate, timeout_seconds=timeout_seconds)
    dispatcher = ActionDispatcher(event_bus=EventBus(), bypass_security=bypass_security)
    dispatcher.set_safety_interceptor(interceptor)
    return dispatcher, interceptor, gate


class TestBenignDispatchUnaffected(unittest.TestCase):
    """A benign action must dispatch and execute exactly as before this change."""

    def setUp(self) -> None:
        self.dispatcher, self.interceptor, self.gate = _make_dispatcher()
        self.calls: list[dict] = []

    def _handler(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True, **kwargs}

    def test_benign_sync_dispatch_executes_unchanged(self) -> None:
        self.dispatcher.register_action("get_status", self._handler)
        result = self.dispatcher.dispatch_action("get_status", payload={"x": 1})
        self.assertTrue(result.success)
        self.assertEqual(result.data, {"ok": True, "x": 1})
        self.assertEqual(self.calls, [{"x": 1}])

    def test_benign_async_dispatch_executes_unchanged(self) -> None:
        async def async_handler(**kwargs):
            self.calls.append(kwargs)
            return {"ok": True, **kwargs}

        self.dispatcher.register_action("get_status_async", async_handler)

        async def run():
            return await self.dispatcher.dispatch_action_async("get_status_async", payload={"y": 2})

        result = asyncio.run(run())
        self.assertTrue(result.success)
        self.assertEqual(result.data, {"ok": True, "y": 2})
        self.assertEqual(self.calls, [{"y": 2}])


class TestRiskyDispatchBlocked(unittest.TestCase):
    """A risky action must never execute before a valid confirmation is supplied."""

    def setUp(self) -> None:
        self.dispatcher, self.interceptor, self.gate = _make_dispatcher()
        self.executed = False

    def _destructive_handler(self, **kwargs):
        self.executed = True
        return {"deleted": True}

    def test_risky_sync_dispatch_does_not_execute_before_confirmation(self) -> None:
        self.dispatcher.register_action("delete_file", self._destructive_handler)
        result = self.dispatcher.dispatch_action("delete_file", payload={"path": "C:/tmp/a.txt"})
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "CONFIRMATION_REQUIRED")
        self.assertIn("confirmation_token", result.data)
        self.assertFalse(self.executed)

    def test_risky_async_dispatch_does_not_execute_before_confirmation(self) -> None:
        executed = {"flag": False}

        async def async_destructive(**kwargs):
            executed["flag"] = True
            return {"deleted": True}

        self.dispatcher.register_action("delete_file_async", async_destructive)

        async def run():
            return await self.dispatcher.dispatch_action_async("delete_file_async", payload={"path": "C:/tmp/a.txt"})

        result = asyncio.run(run())
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "CONFIRMATION_REQUIRED")
        self.assertIn("confirmation_token", result.data)
        self.assertFalse(executed["flag"])


class TestSystemPowerDeterministicGating(unittest.TestCase):
    """
    Shutdown/reboot/sleep must be recognized and gated deterministically by
    the shared classifier -- never by trusting an LLM/router-supplied
    IntentResult.requires_confirmation flag, which this test never even
    constructs.
    """

    def setUp(self) -> None:
        self.dispatcher, self.interceptor, self.gate = _make_dispatcher()
        self.executed_actions: list[str] = []

    def _power_handler(self, action: str = "", **kwargs):
        self.executed_actions.append(action)
        return {"done": action}

    def test_shutdown_reboot_sleep_cannot_execute_without_confirmation(self) -> None:
        self.dispatcher.register_action("system_power", self._power_handler)
        for sub_action in ("shutdown", "restart", "reboot", "sleep"):
            with self.subTest(sub_action=sub_action):
                result = self.dispatcher.dispatch_action("system_power", payload={"action": sub_action})
                self.assertFalse(result.success)
                self.assertEqual(result.error_code, "CONFIRMATION_REQUIRED")
        self.assertEqual(self.executed_actions, [])

    def test_lock_is_not_classified_as_destructive(self) -> None:
        """Precision check: 'lock' must not be swept up by the shutdown/reboot/sleep gate."""
        self.dispatcher.register_action("system_power", self._power_handler)
        result = self.dispatcher.dispatch_action("system_power", payload={"action": "lock"})
        self.assertTrue(result.success)
        self.assertEqual(self.executed_actions, ["lock"])


class TestConfirmationBinding(unittest.TestCase):
    """
    Covers the pending-action binding layer: one-shot, exact action_name +
    payload binding, expiry, rejection, and cross-action/cross-payload
    token misuse.
    """

    def setUp(self) -> None:
        self.dispatcher, self.interceptor, self.gate = _make_dispatcher()
        self.executed: list[dict] = []

    def _handler(self, **kwargs):
        self.executed.append(kwargs)
        return {"ok": True}

    def _gate_and_get_token(self, action_name: str, payload: dict) -> str:
        result = self.dispatcher.dispatch_action(action_name, payload=payload)
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "CONFIRMATION_REQUIRED")
        return result.data["confirmation_token"]

    def test_confirmed_exact_action_executes_exactly_once(self) -> None:
        self.dispatcher.register_action("delete_file", self._handler)
        payload = {"path": "C:/tmp/a.txt"}
        token = self._gate_and_get_token("delete_file", payload)

        self.assertTrue(self.gate.confirm(token))

        result = self.dispatcher.dispatch_action("delete_file", payload=payload, confirmation_token=token)
        self.assertTrue(result.success)
        self.assertEqual(len(self.executed), 1)

    def test_token_replay_fails_after_successful_confirmation(self) -> None:
        self.dispatcher.register_action("delete_file", self._handler)
        payload = {"path": "C:/tmp/a.txt"}
        token = self._gate_and_get_token("delete_file", payload)
        self.assertTrue(self.gate.confirm(token))

        first = self.dispatcher.dispatch_action("delete_file", payload=payload, confirmation_token=token)
        self.assertTrue(first.success)
        self.assertEqual(len(self.executed), 1)

        # Replay: same token, same action, same payload -- must fail closed.
        second = self.dispatcher.dispatch_action("delete_file", payload=payload, confirmation_token=token)
        self.assertFalse(second.success)
        self.assertEqual(second.error_code, "CONFIRMATION_ALREADY_CONSUMED")
        self.assertEqual(len(self.executed), 1)

    def test_rejected_action_never_executes(self) -> None:
        self.dispatcher.register_action("delete_file", self._handler)
        payload = {"path": "C:/tmp/a.txt"}
        token = self._gate_and_get_token("delete_file", payload)

        self.assertTrue(self.gate.reject(token))

        result = self.dispatcher.dispatch_action("delete_file", payload=payload, confirmation_token=token)
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "CONFIRMATION_REJECTED")
        self.assertEqual(self.executed, [])

    def test_expired_token_never_executes(self) -> None:
        dispatcher, interceptor, gate = _make_dispatcher(timeout_seconds=0.05)
        dispatcher.register_action("delete_file", self._handler)
        payload = {"path": "C:/tmp/a.txt"}

        gated = dispatcher.dispatch_action("delete_file", payload=payload)
        token = gated.data["confirmation_token"]

        import time
        time.sleep(0.15)

        # Even if confirmed after expiry, SafetyGate itself refuses to flip
        # an expired PENDING entry to CONFIRMED.
        gate.confirm(token)

        result = dispatcher.dispatch_action("delete_file", payload=payload, confirmation_token=token)
        self.assertFalse(result.success)
        self.assertIn(result.error_code, ("CONFIRMATION_EXPIRED", "CONFIRMATION_NOT_CONFIRMED"))
        self.assertEqual(self.executed, [])

    def test_token_for_action_a_cannot_confirm_action_b(self) -> None:
        self.dispatcher.register_action("delete_file", self._handler)
        self.dispatcher.register_action("format_disk", self._handler)

        token_a = self._gate_and_get_token("delete_file", {"path": "C:/tmp/a.txt"})
        self.assertTrue(self.gate.confirm(token_a))

        # Token was issued for delete_file; attempt to use it for format_disk.
        result = self.dispatcher.dispatch_action("format_disk", payload={"drive": "D:"}, confirmation_token=token_a)
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "CONFIRMATION_ACTION_MISMATCH")
        self.assertEqual(self.executed, [])

    def test_token_for_payload_x_cannot_confirm_modified_payload_y(self) -> None:
        self.dispatcher.register_action("delete_file", self._handler)

        token = self._gate_and_get_token("delete_file", {"path": "C:/tmp/a.txt"})
        self.assertTrue(self.gate.confirm(token))

        # Same action, but a different (modified) payload than what was gated.
        result = self.dispatcher.dispatch_action(
            "delete_file", payload={"path": "C:/Windows/System32"}, confirmation_token=token
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "CONFIRMATION_PAYLOAD_MISMATCH")
        self.assertEqual(self.executed, [])


class TestBypassSecurityDoesNotBypassSafety(unittest.TestCase):
    """bypass_security must remain privilege/RBAC-only; it must never skip the destructive-action gate."""

    def test_bypass_security_does_not_bypass_destructive_safety(self) -> None:
        dispatcher, interceptor, gate = _make_dispatcher(bypass_security=True)
        executed = {"flag": False}

        def handler(**kwargs):
            executed["flag"] = True
            return {"deleted": True}

        dispatcher.register_action(
            "delete_file",
            handler,
            required_privilege=PrivilegeLevel.ADMIN,
        )

        # bypass_security=True means an unauthenticated/low-privilege
        # requester would normally sail through the RBAC check -- confirm
        # it does NOT also sail through the safety gate.
        result = dispatcher.dispatch_action(
            "delete_file",
            payload={"path": "C:/tmp/a.txt"},
            requester=RequesterContext(requester_id="anon", granted_privilege=PrivilegeLevel.GUEST),
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "CONFIRMATION_REQUIRED")
        self.assertFalse(executed["flag"])


class TestPlannerHighRiskGatingBypassesActionDispatcher(unittest.TestCase):
    """
    Reproduces the exact scenario the audit flagged: a TaskNode dispatched
    through ReActTaskEngine.register_action_handler() (the custom-handler
    path in execute_step(), which bypasses ActionDispatcher entirely) must
    still be gated -- even when the plan runs in the default
    PlanMode.FULLY_AUTONOMOUS, which the real production caller always uses.
    """

    def test_high_risk_planner_action_gated_despite_fully_autonomous_and_dispatcher_bypass(self) -> None:
        event_bus = EventBus()
        dispatcher = ActionDispatcher(event_bus=event_bus)
        gate = SafetyGate(timeout_seconds=5.0)
        interceptor = SafetyGateInterceptor(safety_gate=gate, timeout_seconds=5.0)
        dispatcher.set_safety_interceptor(interceptor)
        engine = ReActTaskEngine(
            dispatcher=dispatcher,
            safety_interceptor=interceptor,
            reflection_engine=SelfReflectionEngine(),
            event_bus=event_bus,
        )

        executed = {"flag": False}

        def destructive_act(target_dir: str) -> dict:
            executed["flag"] = True
            return {"deleted": target_dir}

        # Registering a custom direct handler makes execute_step() take the
        # path that bypasses dispatcher.dispatch_action() entirely.
        engine.register_action_handler("delete_folder", destructive_act)

        dag = TaskDAG(plan_id="plan_bypass_test", goal="High-risk custom-handler bypass")
        node = TaskNode(
            step_id="delete_step",
            action_name="delete_folder",
            parameters={"target_dir": "C:/temp/build_cache"},
            is_high_risk=True,
        )
        dag.add_node(node)

        import threading
        import time

        def async_confirm() -> None:
            for _ in range(40):
                if node.confirmation_token:
                    gate.confirm(node.confirmation_token)
                    return
                time.sleep(0.05)

        t = threading.Thread(target=async_confirm)
        t.start()

        # NOTE: default mode -- explicitly the mode the real production
        # caller uses (see jarvis/core/app.py _handle_planner_execute_task).
        result = engine.execute_plan(dag, mode=PlanMode.FULLY_AUTONOMOUS)
        t.join()

        self.assertTrue(result.success)
        self.assertTrue(executed["flag"])
        self.assertEqual(dag.nodes["delete_step"].status, StepStatus.COMPLETED)

    def test_high_risk_planner_action_never_executes_without_confirmation_in_fully_autonomous(self) -> None:
        event_bus = EventBus()
        dispatcher = ActionDispatcher(event_bus=event_bus)
        gate = SafetyGate(timeout_seconds=0.2)
        interceptor = SafetyGateInterceptor(safety_gate=gate, timeout_seconds=0.2)
        dispatcher.set_safety_interceptor(interceptor)
        engine = ReActTaskEngine(
            dispatcher=dispatcher,
            safety_interceptor=interceptor,
            reflection_engine=SelfReflectionEngine(),
            event_bus=event_bus,
            default_timeout_seconds=2.0,
        )

        executed = {"flag": False}

        def destructive_act(target_dir: str) -> dict:
            executed["flag"] = True
            return {"deleted": target_dir}

        engine.register_action_handler("delete_folder", destructive_act)

        dag = TaskDAG(plan_id="plan_bypass_no_confirm", goal="High-risk custom-handler, never confirmed")
        dag.add_node(TaskNode(
            step_id="delete_step",
            action_name="delete_folder",
            parameters={"target_dir": "C:/temp/build_cache"},
            is_high_risk=True,
        ))

        # Do not confirm; let the token expire.
        result = engine.execute_plan(dag, mode=PlanMode.FULLY_AUTONOMOUS)

        self.assertFalse(result.success)
        self.assertFalse(executed["flag"])
        self.assertEqual(dag.nodes["delete_step"].status, StepStatus.FAILED)


if __name__ == "__main__":
    unittest.main()

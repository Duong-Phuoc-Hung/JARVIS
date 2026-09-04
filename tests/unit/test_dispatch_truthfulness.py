"""
tests/unit/test_dispatch_truthfulness.py
=========================================
Focused regression tests for central dispatch truthfulness
(branch fix/dispatch-truthfulness): an action handler's explicit failure must
remain failure through handler -> ActionDispatcher -> application response ->
memory -> interaction log -> events.

Covers:
  - jarvis/core/dispatcher.py's _normalize_handler_outcome() (the pure
    normalization function) and its wiring into dispatch_action()/
    dispatch_action_async() -- sync/async parity, generic-falsy protection,
    established success/failure contract recognition, action.post_dispatch
    event truthfulness.
  - jarvis/core/app.py's process_text_command() failure propagation
    (status_flag derivation, response-text precedence, memory episode success
    flag, interaction log status, CONFIRMATION_REQUIRED truthfulness).
  - jarvis/core/app.py's _on_gesture_event() triple_clap/clap_pause_clap/
    generic gesture-pattern dispatch loops, corrected to reflect actual
    per-action outcomes in the interaction log instead of an unconditional
    "success".

Deterministic synthetic handlers/mocks only -- no real destructive actions,
process kills, network, audio devices, or model downloads.
"""
from __future__ import annotations

import asyncio
import unittest
from typing import Any

from jarvis.core.app import JarvisApp
from jarvis.core.dispatcher import ActionDispatcher, EventBus, _normalize_handler_outcome
from jarvis.core.models import ActionResult
from jarvis.llm.router import IntentResult


# ============================================================================
# 1. Pure normalization function
# ============================================================================


class TestNormalizeHandlerOutcome(unittest.TestCase):
    """Direct unit tests of the pure normalization function."""

    def test_ordinary_dict_payload_is_success(self) -> None:
        success, data, error, error_code = _normalize_handler_outcome({"foo": "bar"})
        self.assertTrue(success)
        self.assertEqual(data, {"foo": "bar"})
        self.assertIsNone(error)
        self.assertIsNone(error_code)

    def test_zero_remains_success(self) -> None:
        success, data, _, _ = _normalize_handler_outcome(0)
        self.assertTrue(success)
        self.assertEqual(data, 0)

    def test_empty_string_remains_success(self) -> None:
        success, data, _, _ = _normalize_handler_outcome("")
        self.assertTrue(success)
        self.assertEqual(data, "")

    def test_empty_list_remains_success(self) -> None:
        success, data, _, _ = _normalize_handler_outcome([])
        self.assertTrue(success)
        self.assertEqual(data, [])

    def test_empty_dict_remains_success(self) -> None:
        success, data, _, _ = _normalize_handler_outcome({})
        self.assertTrue(success)
        self.assertEqual(data, {})

    def test_none_remains_success(self) -> None:
        success, data, _, _ = _normalize_handler_outcome(None)
        self.assertTrue(success)
        self.assertIsNone(data)

    def test_bare_bool_false_is_ordinary_data_not_failure(self) -> None:
        """
        Documented decision (repository-wide audit, see CLAUDE.md's
        dispatch-truthfulness invariant): no dispatcher-registered handler in
        this repository returns a bare True/False as its entire payload --
        booleans only ever appear nested inside an explicit {"success": ...}
        key. Per the "no generic falsiness" rule, a bare False is therefore
        NOT an established failure contract and must remain ordinary
        successful data.
        """
        success, data, error, error_code = _normalize_handler_outcome(False)
        self.assertTrue(success)
        self.assertIs(data, False)
        self.assertIsNone(error)

    def test_bare_bool_true_remains_success(self) -> None:
        success, data, _, _ = _normalize_handler_outcome(True)
        self.assertTrue(success)
        self.assertIs(data, True)

    def test_action_result_success_false_stays_failed(self) -> None:
        raw = ActionResult(action_name="x", success=False, error="boom", error_code="X_FAILED")
        success, data, error, error_code = _normalize_handler_outcome(raw)
        self.assertFalse(success)
        self.assertIs(data, raw.data)
        self.assertEqual(error, "boom")
        self.assertEqual(error_code, "X_FAILED")

    def test_action_result_success_true_stays_success(self) -> None:
        raw = ActionResult(action_name="x", success=True, data={"ok": True})
        success, data, error, error_code = _normalize_handler_outcome(raw)
        self.assertTrue(success)
        self.assertEqual(data, {"ok": True})
        self.assertIsNone(error)

    def test_dict_success_false_established_contract_stays_failed(self) -> None:
        success, data, error, error_code = _normalize_handler_outcome(
            {"success": False, "error": "Application name is empty"}
        )
        self.assertFalse(success)
        self.assertEqual(error, "Application name is empty")

    def test_dict_status_failed_established_contract_stays_failed(self) -> None:
        success, data, error, error_code = _normalize_handler_outcome(
            {"status": "failed", "message": "Vision subsystem unavailable"}
        )
        self.assertFalse(success)
        self.assertEqual(error, "Vision subsystem unavailable")

    def test_dict_status_error_established_contract_stays_failed(self) -> None:
        success, data, error, error_code = _normalize_handler_outcome(
            {"status": "error", "message": "boom"}
        )
        self.assertFalse(success)
        self.assertEqual(error, "boom")

    def test_dict_error_key_preferred_over_message_key(self) -> None:
        success, data, error, error_code = _normalize_handler_outcome(
            {"success": False, "error": "raw error", "message": "human message"}
        )
        self.assertFalse(success)
        self.assertEqual(error, "raw error")

    def test_dict_success_true_established_contract_stays_success(self) -> None:
        success, data, error, error_code = _normalize_handler_outcome({"success": True, "uri": "x"})
        self.assertTrue(success)
        self.assertIsNone(error)

    def test_dict_status_ok_stays_success(self) -> None:
        success, data, _, _ = _normalize_handler_outcome({"status": "ok"})
        self.assertTrue(success)

    def test_dict_status_success_literal_stays_success(self) -> None:
        success, data, _, _ = _normalize_handler_outcome({"status": "success"})
        self.assertTrue(success)

    def test_dict_ok_true_stays_success(self) -> None:
        success, data, _, _ = _normalize_handler_outcome({"ok": True})
        self.assertTrue(success)

    def test_unrecognized_custom_status_string_stays_success(self) -> None:
        """
        Custom domain-specific status strings that are neither "failed" nor
        "error" (e.g. jarvis/core/app.py's own _handle_tts_welcome()
        returning {"status": "tts_unavailable"}, or _handle_show_overlay()
        returning {"status": "overlay_unavailable"}) are NOT an established
        failure contract and must not be misclassified as failure.
        """
        success, data, error, error_code = _normalize_handler_outcome({"status": "tts_unavailable"})
        self.assertTrue(success)
        self.assertIsNone(error)


# ============================================================================
# 2. dispatch_action() (sync)
# ============================================================================


def _make_dispatcher() -> ActionDispatcher:
    return ActionDispatcher(event_bus=EventBus(), bypass_security=True)


class TestDispatchActionSyncTruthfulness(unittest.TestCase):
    def setUp(self) -> None:
        self.dispatcher = _make_dispatcher()

    def test_ordinary_successful_payload(self) -> None:
        self.dispatcher.register_action("a", lambda **kw: {"data": 42})
        res = self.dispatcher.dispatch_action("a")
        self.assertTrue(res.success)
        self.assertEqual(res.data, {"data": 42})

    def test_zero_remains_success(self) -> None:
        self.dispatcher.register_action("a", lambda **kw: 0)
        res = self.dispatcher.dispatch_action("a")
        self.assertTrue(res.success)
        self.assertEqual(res.data, 0)

    def test_empty_string_remains_success(self) -> None:
        self.dispatcher.register_action("a", lambda **kw: "")
        res = self.dispatcher.dispatch_action("a")
        self.assertTrue(res.success)
        self.assertEqual(res.data, "")

    def test_empty_list_remains_success(self) -> None:
        self.dispatcher.register_action("a", lambda **kw: [])
        res = self.dispatcher.dispatch_action("a")
        self.assertTrue(res.success)
        self.assertEqual(res.data, [])

    def test_empty_dict_remains_success(self) -> None:
        self.dispatcher.register_action("a", lambda **kw: {})
        res = self.dispatcher.dispatch_action("a")
        self.assertTrue(res.success)
        self.assertEqual(res.data, {})

    def test_none_remains_success(self) -> None:
        self.dispatcher.register_action("a", lambda **kw: None)
        res = self.dispatcher.dispatch_action("a")
        self.assertTrue(res.success)
        self.assertIsNone(res.data)

    def test_returned_action_result_failure_stays_failed(self) -> None:
        self.dispatcher.register_action(
            "a", lambda **kw: ActionResult(action_name="a", success=False, error="nope")
        )
        res = self.dispatcher.dispatch_action("a")
        self.assertFalse(res.success)
        self.assertEqual(res.error, "nope")

    def test_returned_action_result_success_stays_success(self) -> None:
        self.dispatcher.register_action(
            "a", lambda **kw: ActionResult(action_name="a", success=True, data={"x": 1})
        )
        res = self.dispatcher.dispatch_action("a")
        self.assertTrue(res.success)
        self.assertEqual(res.data, {"x": 1})

    def test_established_structured_failure_stays_failed(self) -> None:
        self.dispatcher.register_action(
            "a", lambda **kw: {"success": False, "error": "Application name is empty"}
        )
        res = self.dispatcher.dispatch_action("a")
        self.assertFalse(res.success)
        self.assertEqual(res.error, "Application name is empty")

    def test_established_structured_success_stays_successful(self) -> None:
        self.dispatcher.register_action("a", lambda **kw: {"status": "success", "message": "done"})
        res = self.dispatcher.dispatch_action("a")
        self.assertTrue(res.success)

    def test_bare_bool_false_handler_result_is_not_treated_as_failure(self) -> None:
        """Documented decision: see TestNormalizeHandlerOutcome's docstring."""
        self.dispatcher.register_action("a", lambda **kw: False)
        res = self.dispatcher.dispatch_action("a")
        self.assertTrue(res.success)
        self.assertIs(res.data, False)


# ============================================================================
# 3. dispatch_action_async()
# ============================================================================


class TestDispatchActionAsyncTruthfulness(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.dispatcher = _make_dispatcher()

    async def test_returned_action_result_failure_stays_failed(self) -> None:
        async def handler(**kw):
            return ActionResult(action_name="a", success=False, error="async nope")

        self.dispatcher.register_action("a", handler)
        res = await self.dispatcher.dispatch_action_async("a")
        self.assertFalse(res.success)
        self.assertEqual(res.error, "async nope")

    async def test_structured_failure_stays_failed(self) -> None:
        async def handler(**kw):
            return {"status": "error", "message": "async boom"}

        self.dispatcher.register_action("a", handler)
        res = await self.dispatcher.dispatch_action_async("a")
        self.assertFalse(res.success)
        self.assertEqual(res.error, "async boom")

    async def test_successful_structured_payload(self) -> None:
        async def handler(**kw):
            return {"success": True, "data": 1}

        self.dispatcher.register_action("a", handler)
        res = await self.dispatcher.dispatch_action_async("a")
        self.assertTrue(res.success)

    async def test_generic_falsy_payload_not_misclassified(self) -> None:
        async def handler(**kw):
            return 0

        self.dispatcher.register_action("a", handler)
        res = await self.dispatcher.dispatch_action_async("a")
        self.assertTrue(res.success)
        self.assertEqual(res.data, 0)

    async def test_sync_and_async_semantics_aligned(self) -> None:
        """Same raw payload shape normalizes identically through both dispatch paths."""

        def sync_handler(**kw):
            return {"status": "failed", "error": "x"}

        async def async_handler(**kw):
            return {"status": "failed", "error": "x"}

        self.dispatcher.register_action("sync_a", sync_handler)
        self.dispatcher.register_action("async_a", async_handler)

        sync_res = self.dispatcher.dispatch_action("sync_a")
        async_res = await self.dispatcher.dispatch_action_async("async_a")

        self.assertEqual(sync_res.success, async_res.success)
        self.assertEqual(sync_res.error, async_res.error)

    async def test_existing_timeout_behavior_preserved(self) -> None:
        async def handler(**kw):
            await asyncio.sleep(10)
            return {"success": True}

        self.dispatcher.register_action("slow", handler)
        res = await self.dispatcher.dispatch_action_async("slow", timeout=0.05)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "TIMEOUT")


# ============================================================================
# 4. action.post_dispatch event truthfulness
# ============================================================================


class TestEventTruthfulness(unittest.TestCase):
    def setUp(self) -> None:
        self.dispatcher = _make_dispatcher()
        self.events: list[dict] = []
        self.dispatcher.event_bus.subscribe(
            "action.post_dispatch",
            lambda **payload: self.events.append(payload),
        )

    def test_failed_normalized_result_does_not_emit_success_true(self) -> None:
        self.dispatcher.register_action("a", lambda **kw: {"success": False, "error": "boom"})
        self.dispatcher.dispatch_action("a")
        self.assertEqual(len(self.events), 1)
        self.assertFalse(self.events[0]["success"])

    def test_successful_normalized_result_emits_truthful_success_event(self) -> None:
        self.dispatcher.register_action("a", lambda **kw: {"data": 1})
        self.dispatcher.dispatch_action("a")
        self.assertEqual(len(self.events), 1)
        self.assertTrue(self.events[0]["success"])


# ============================================================================
# 5. process_text_command() failure propagation
# ============================================================================


def _make_app() -> JarvisApp:
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()
    return app


class TestProcessTextCommandTruthfulness(unittest.TestCase):
    def setUp(self) -> None:
        self.app = _make_app()
        self.logged: list[dict] = []
        self.app.log_interaction = lambda **kw: (self.logged.append(kw), "log_id")[1]
        self.episodes: list[dict] = []
        if self.app.memory_manager:
            self.app.memory_manager.log_episode = lambda **kw: self.episodes.append(kw)

    def tearDown(self) -> None:
        self.app.stop()

    def _route_to(self, action_name: str, parameters: dict | None = None) -> None:
        self.app.llm_router.parse_intent = lambda text: IntentResult(
            action_name=action_name, parameters=parameters or {}, response_text=None,
        )

    def test_failed_action_result_top_level_success_false(self) -> None:
        self.app.dispatcher.register_action(
            "test_fail", lambda **kw: {"success": False, "error": "boom"}
        )
        self._route_to("test_fail")
        res = self.app.process_text_command("kích hoạt test fail", requester="user")
        self.assertFalse(res["success"])

    def test_interaction_log_receives_failure(self) -> None:
        self.app.dispatcher.register_action(
            "test_fail", lambda **kw: {"success": False, "error": "boom"}
        )
        self._route_to("test_fail")
        self.app.process_text_command("kích hoạt test fail", requester="user")
        self.assertTrue(self.logged)
        self.assertEqual(self.logged[-1]["status"], "failed")

    def test_memory_episode_records_failure(self) -> None:
        self.app.dispatcher.register_action(
            "test_fail", lambda **kw: {"success": False, "error": "boom"}
        )
        self._route_to("test_fail")
        self.app.process_text_command("kích hoạt test fail", requester="user")
        if self.episodes:
            self.assertFalse(self.episodes[-1]["success"])

    def test_error_text_surfaced(self) -> None:
        self.app.dispatcher.register_action(
            "test_fail", lambda **kw: {"success": False, "error": "Lý do thất bại cụ thể"}
        )
        self._route_to("test_fail")
        res = self.app.process_text_command("kích hoạt test fail", requester="user")
        self.assertIn("Lý do thất bại cụ thể", res["response_text"])

    def test_structured_failure_message_surfaced_when_no_error_string(self) -> None:
        self.app.dispatcher.register_action(
            "test_fail",
            lambda **kw: {"status": "failed", "message": "Thông báo thất bại có cấu trúc"},
        )
        self._route_to("test_fail")
        res = self.app.process_text_command("kích hoạt test fail", requester="user")
        self.assertIn("Thông báo thất bại có cấu trúc", res["response_text"])

    def test_error_code_fallback_when_no_error_or_message(self) -> None:
        self.app.dispatcher.register_action(
            "test_fail", lambda **kw: {"success": False, "error_code": "CUSTOM_CODE"}
        )
        self._route_to("test_fail")
        res = self.app.process_text_command("kích hoạt test fail", requester="user")
        self.assertFalse(res["success"])
        self.assertIn("CUSTOM_CODE", res["response_text"])

    def test_neutral_fallback_when_no_detail_at_all(self) -> None:
        self.app.dispatcher.register_action("test_fail", lambda **kw: {"success": False})
        self._route_to("test_fail")
        res = self.app.process_text_command("kích hoạt test fail", requester="user")
        self.assertFalse(res["success"])
        self.assertEqual(res["response_text"], "Không thể thực hiện lệnh.")

    def test_failed_action_does_not_produce_da_thuc_hien_lenh(self) -> None:
        self.app.dispatcher.register_action(
            "test_fail", lambda **kw: {"success": False, "error": "x"}
        )
        self._route_to("test_fail")
        res = self.app.process_text_command("kích hoạt test fail", requester="user")
        self.assertNotIn("Đã thực hiện lệnh", res["response_text"])

    def test_successful_behavior_remains_unchanged(self) -> None:
        self.app.dispatcher.register_action(
            "test_ok", lambda **kw: {"success": True, "message": "Đã xong."}
        )
        self._route_to("test_ok")
        res = self.app.process_text_command("kích hoạt test ok", requester="user")
        self.assertTrue(res["success"])
        self.assertEqual(res["response_text"], "Đã xong.")
        self.assertEqual(self.logged[-1]["status"], "success")

    def test_confirmation_required_remains_failed_end_to_end(self) -> None:
        # "destroy_" is one of the deterministic high-risk name prefixes
        # recognized by SafetyGateInterceptor.is_high_risk() (see CLAUDE.md
        # §8.3) -- this handler must never actually run.
        called = []
        self.app.dispatcher.register_action(
            "destroy_test_target", lambda **kw: called.append(1) or {"success": True}
        )
        self._route_to("destroy_test_target")
        res = self.app.process_text_command("phá hủy mục tiêu test", requester="user")
        self.assertFalse(res["success"])
        self.assertEqual(res["result"]["error_code"], "CONFIRMATION_REQUIRED")
        self.assertEqual(self.logged[-1]["status"], "failed")
        self.assertFalse(called, "Gated high-risk handler must not execute without confirmation")


# ============================================================================
# 5b. system_power / toggle_mute handler truthfulness
#     (branch fix/voice-control-truthfulness)
# ============================================================================


class _FakeLockWin32:
    """
    Minimal injectable win32-platform double exposing only lock_workstation(),
    used to prove _handle_system_power()'s "lock" path is truthful without
    ever locking a real workstation.
    """

    def __init__(self, result: bool = True, raise_exc: Exception | None = None) -> None:
        self.result = result
        self.raise_exc = raise_exc
        self.calls = 0

    def lock_workstation(self) -> bool:
        self.calls += 1
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.result


class _FakeTray:
    """Minimal tray_controller double exposing only what _handle_toggle_mute() reads/writes."""

    def __init__(self, muted: bool = False) -> None:
        self._is_mic_muted = muted
        self.status_updates: list[Any] = []

    def update_status(self, status: Any) -> None:
        self.status_updates.append(status)

    def stop(self) -> None:
        """No-op: satisfies JarvisApp.stop()'s tray_controller.stop() call."""


class TestSystemPowerHandlerTruthfulness(unittest.TestCase):
    """
    jarvis/core/app.py::_handle_system_power() must never report a
    shutdown/restart/sleep/hibernate as having occurred -- no authoritative
    backend for any of those sub-actions exists anywhere in this repository
    (verified by repo-wide search; only WindowsPlatformAPI.lock_workstation()
    is a real, truthful backend, reused here via
    self.computer_controller.win32). No test in this class ever performs a
    real shutdown/restart/reboot/sleep/hibernate/lock -- lock_workstation()
    is always an injected fake.
    """

    def setUp(self) -> None:
        self.app = _make_app()

    def tearDown(self) -> None:
        self.app.stop()

    def test_destructive_actions_blocked_without_confirmation(self) -> None:
        fake_win32 = _FakeLockWin32()
        self.app.computer_controller.win32 = fake_win32
        for sub_action in ("shutdown", "restart", "sleep", "hibernate"):
            with self.subTest(sub_action=sub_action):
                result = self.app.dispatcher.dispatch_action(
                    "system_power", payload={"action": sub_action}
                )
                self.assertFalse(result.success)
                self.assertEqual(result.error_code, "CONFIRMATION_REQUIRED")
        self.assertEqual(fake_win32.calls, 0, "No power backend may be touched before confirmation")

    def test_unsupported_power_action_fails_even_after_confirmation(self) -> None:
        """
        A genuinely CONFIRMED shutdown/restart/sleep/hibernate must still
        fail closed -- confirmation only satisfies the safety gate, it does
        not conjure a backend that does not exist.
        """
        for sub_action in ("shutdown", "restart", "sleep", "hibernate"):
            with self.subTest(sub_action=sub_action):
                payload = {"action": sub_action}
                gated = self.app.dispatcher.dispatch_action("system_power", payload=payload)
                self.assertEqual(gated.error_code, "CONFIRMATION_REQUIRED")
                token = gated.data["confirmation_token"]
                self.assertTrue(self.app.dispatcher.safety_interceptor.confirm(token))

                result = self.app.dispatcher.dispatch_action(
                    "system_power", payload=payload, confirmation_token=token
                )
                self.assertFalse(result.success)
                self.assertEqual(result.error_code, "POWER_ACTION_UNSUPPORTED")

    def test_unknown_power_action_is_rejected(self) -> None:
        result = self.app.dispatcher.dispatch_action("system_power", payload={"action": "teleport"})
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "UNKNOWN_POWER_ACTION")

    def test_lock_is_not_gated_and_reports_real_backend_success(self) -> None:
        fake_win32 = _FakeLockWin32(result=True)
        self.app.computer_controller.win32 = fake_win32
        result = self.app.dispatcher.dispatch_action("system_power", payload={"action": "lock"})
        self.assertTrue(result.success)
        self.assertEqual(fake_win32.calls, 1)

    def test_lock_backend_false_is_reported_as_failure(self) -> None:
        fake_win32 = _FakeLockWin32(result=False)
        self.app.computer_controller.win32 = fake_win32
        result = self.app.dispatcher.dispatch_action("system_power", payload={"action": "lock"})
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "LOCK_WORKSTATION_FAILED")

    def test_lock_backend_exception_is_reported_as_failure_not_success(self) -> None:
        fake_win32 = _FakeLockWin32(raise_exc=RuntimeError("boom"))
        self.app.computer_controller.win32 = fake_win32
        result = self.app.dispatcher.dispatch_action("system_power", payload={"action": "lock"})
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "LOCK_WORKSTATION_FAILED")


class TestToggleMuteHandlerTruthfulness(unittest.TestCase):
    """
    jarvis/core/app.py::_handle_toggle_mute() must respect an explicit
    desired mic state instead of blindly toggling -- "tắt mic" (muted=True)
    must never unmute an already-muted mic, and "bật mic" (muted=False) must
    never mute an already-unmuted mic (the real bug this branch fixes). No
    test in this class touches a real audio device --
    AudioEngine.pause_stream()/resume_stream() only flip an in-process
    threading.Event.
    """

    def setUp(self) -> None:
        self.app = _make_app()

    def tearDown(self) -> None:
        self.app.stop()

    def test_explicit_muted_true_does_not_invert_already_muted_state(self) -> None:
        self.app._mic_muted = True
        result = self.app.dispatcher.dispatch_action("toggle_mute", payload={"muted": True})
        self.assertTrue(result.success)
        self.assertTrue(result.data["muted"])
        self.assertTrue(self.app._mic_muted)

    def test_explicit_muted_false_does_not_invert_already_unmuted_state(self) -> None:
        self.app._mic_muted = False
        result = self.app.dispatcher.dispatch_action("toggle_mute", payload={"muted": False})
        self.assertTrue(result.success)
        self.assertFalse(result.data["muted"])
        self.assertFalse(self.app._mic_muted)

    def test_toggle_with_no_desired_state_flips_current_state(self) -> None:
        self.app._mic_muted = False
        first = self.app.dispatcher.dispatch_action("toggle_mute", payload={})
        self.assertTrue(first.success)
        self.assertTrue(first.data["muted"])
        second = self.app.dispatcher.dispatch_action("toggle_mute", payload={})
        self.assertTrue(second.success)
        self.assertFalse(second.data["muted"])

    def test_explicit_desired_state_backend_failure_is_not_reported_as_success(self) -> None:
        def _raise() -> None:
            raise RuntimeError("no audio device")

        self.app.audio_engine.pause_stream = _raise
        result = self.app.dispatcher.dispatch_action("toggle_mute", payload={"muted": True})
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "AUDIO_ENGINE_EXCEPTION")

    def test_toggle_mute_syncs_tray_controller_state_when_present(self) -> None:
        tray = _FakeTray(muted=False)
        self.app.tray_controller = tray
        result = self.app.dispatcher.dispatch_action("toggle_mute", payload={"muted": True})
        self.assertTrue(result.success)
        self.assertTrue(tray._is_mic_muted)

    def test_toggle_mute_reports_failure_when_audio_engine_unavailable(self) -> None:
        self.app.audio_engine = None
        result = self.app.dispatcher.dispatch_action("toggle_mute", payload={"muted": True})
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "AUDIO_ENGINE_UNAVAILABLE")


# ============================================================================
# 6. Gesture dispatch consumer truthfulness (_on_gesture_event)
# ============================================================================


class TestGestureDispatchTruthfulness(unittest.TestCase):
    def setUp(self) -> None:
        self.app = _make_app()
        self.logged: list[dict] = []
        self.app.log_interaction = lambda **kw: (self.logged.append(kw), "log_id")[1]

    def tearDown(self) -> None:
        self.app.stop()

    def test_triple_clap_all_success_logs_success(self) -> None:
        self.app.config.set("gesture.patterns.triple_clap.actions", ["test_ok"])
        self.app.dispatcher.register_action("test_ok", lambda **kw: {"success": True})
        self.app._on_gesture_event("triple_clap", confidence=1.0)
        self.assertEqual(self.logged[-1]["status"], "success")

    def test_triple_clap_failure_logs_failed(self) -> None:
        self.app.config.set("gesture.patterns.triple_clap.actions", ["test_fail"])
        self.app.dispatcher.register_action(
            "test_fail", lambda **kw: {"success": False, "error": "x"}
        )
        self.app._on_gesture_event("triple_clap", confidence=1.0)
        self.assertEqual(self.logged[-1]["status"], "failed")

    def test_clap_pause_clap_failure_logs_failed(self) -> None:
        self.app.config.set("gesture.patterns.clap_pause_clap.actions", ["test_fail"])
        self.app.dispatcher.register_action("test_fail", lambda **kw: {"success": False})
        self.app._on_gesture_event("clap_pause_clap", confidence=1.0)
        self.assertEqual(self.logged[-1]["status"], "failed")

    def test_generic_pattern_failure_logs_failed(self) -> None:
        self.app.config.set("gesture.patterns.custom_pattern.actions", ["test_fail"])
        self.app.dispatcher.register_action("test_fail", lambda **kw: {"status": "error"})
        self.app._on_gesture_event("custom_pattern", confidence=1.0)
        self.assertEqual(self.logged[-1]["status"], "failed")


# ============================================================================
# 7. hardware_status_query compatibility alias (owner-authorized narrow fix)
# ============================================================================


class TestHardwareStatusQueryAlias(unittest.TestCase):
    """
    The LLM router (jarvis/llm/router.py) intentionally emits the intent name
    hardware_status_query for several hardware/status voice queries -- system
    prompt examples, Vietnamese rule fallback, unaccented Vietnamese fallback,
    system-status regex handling, and response-generation compatibility logic
    -- while JarvisApp historically only ever registered a dispatcher action
    named system_status. That mismatch produced a real ACTION_NOT_FOUND once
    dispatch truthfulness stopped masking it (see
    tests/unit/test_integration_e2e.py::test_memory_recording_in_process_text_command).
    Per explicit owner direction, router.py is left untouched; the fix is a
    narrow compatibility alias registered inside JarvisApp itself, reusing the
    existing _handle_system_status implementation for both names -- no
    duplicated handler logic.
    """

    def setUp(self) -> None:
        self.app = _make_app()

    def tearDown(self) -> None:
        self.app.stop()

    def test_system_status_action_exists(self) -> None:
        self.assertIsNotNone(self.app.dispatcher.get_action("system_status"))

    def test_hardware_status_query_action_exists(self) -> None:
        self.assertIsNotNone(self.app.dispatcher.get_action("hardware_status_query"))

    def test_both_names_share_the_same_handler_no_duplicated_logic(self) -> None:
        """
        Both ActionDefinitions must wrap the identical underlying function
        (self._handle_system_status), on the same JarvisApp instance -- i.e.
        no separate/duplicated implementation. Bound methods re-accessed via
        attribute lookup are distinct objects each time (so `is` would be a
        false negative here) but compare equal via `==` when they share the
        same __func__/__self__, and their __func__ identity is the strongest
        available proof of "no duplicated logic".
        """
        system_status_def = self.app.dispatcher.get_action("system_status")
        hardware_status_query_def = self.app.dispatcher.get_action("hardware_status_query")
        self.assertEqual(system_status_def.handler, hardware_status_query_def.handler)
        self.assertIs(system_status_def.handler.__func__, hardware_status_query_def.handler.__func__)
        self.assertIs(system_status_def.handler.__func__, self.app._handle_system_status.__func__)

    def test_hardware_status_query_does_not_return_action_not_found(self) -> None:
        res = self.app.dispatcher.dispatch_action("hardware_status_query")
        self.assertTrue(res.success)
        self.assertNotEqual(res.error_code, "ACTION_NOT_FOUND")

    def test_hardware_status_query_dispatches_same_behavior_as_system_status(self) -> None:
        res_alias = self.app.dispatcher.dispatch_action("hardware_status_query")
        res_direct = self.app.dispatcher.dispatch_action("system_status")
        self.assertEqual(res_alias.success, res_direct.success)
        self.assertEqual(set(res_alias.data.keys()), set(res_direct.data.keys()))
        self.assertEqual(res_alias.data.get("status"), res_direct.data.get("status"))


if __name__ == "__main__":
    unittest.main()

"""
tests/unit/test_core_fixes_m1.py
================================
Regression test suite for Milestone 1: Core Subsystem Remediation.
Verifies fixes for:
1. BUG-CORE-01: Event loop deadlock in EventBus.publish & ActionDispatcher.dispatch_action.
2. BUG-CORE-02: ActionStatus enum preservation (avoid demotion to ActionStatus.FAILED).
3. BUG-CORE-03: ActionStatus.RATE_LIMITED and LABS_DISABLED fail-closed normalization.
4. BUG-CORE-04: ComputerController.send_hotkey argument splatting in _handle_new_tab.
5. BUG-CORE-05: Inverted error/message contract in _handle_system_brightness.
6. BUG-CORE-06: Grammatical direction bug ("lên" vs "xuống") in _handle_system_volume.
7. BUG-CORE-07: Concurrency & double-initialization in JarvisApp.initialize.
8. BUG-CORE-08: Resilient subsystem teardown in JarvisApp.stop.
9. BUG-CORE-09: PassiveTriggerGuard double lockout trap when lockout_s < window_s.
"""
from __future__ import annotations

import asyncio
import threading
import unittest
from unittest.mock import MagicMock, patch

from jarvis.core.app import JarvisApp
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import ActionResult, ActionStatus
from jarvis.core.runaway_guard import PassiveTriggerGuard


class TestCoreRemediationM1(unittest.TestCase):
    """Targeted regression tests for Milestone 1 core subsystem bugs."""

    # -------------------------------------------------------------------------
    # BUG-CORE-01: Deadlock on Running Event Loop
    # -------------------------------------------------------------------------
    def test_sync_dispatch_inside_running_event_loop(self) -> None:
        """Synchronous dispatch_action with an async handler must not deadlock inside a running event loop."""
        d = ActionDispatcher()

        async def async_handler(val: int = 1) -> dict:
            await asyncio.sleep(0.01)
            return {"status": "success", "val": val * 2}

        d.register_action("sample_async", async_handler)

        async def run_in_loop() -> ActionResult:
            # Called synchronously from inside the loop thread
            return d.dispatch_action("sample_async", payload={"val": 21}, timeout=2.0)

        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(run_in_loop())
            self.assertTrue(res.success)
            self.assertEqual(res.status, ActionStatus.SUCCESS)
            self.assertEqual(res.data.get("val"), 42)
        finally:
            loop.close()

    def test_sync_eventbus_publish_inside_running_event_loop(self) -> None:
        """Synchronous EventBus.publish with an async subscriber must not deadlock inside a running event loop."""
        bus = EventBus()
        received = []

        async def async_subscriber(**payload) -> str:
            await asyncio.sleep(0.01)
            received.append(payload.get("msg"))
            return "subscriber_ok"

        bus.subscribe("test.event", async_subscriber)

        async def run_in_loop() -> list:
            return bus.publish("test.event", msg="hello_from_loop")

        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(run_in_loop())
            self.assertEqual(len(results), 1)
            self.assertTrue(results[0].success)
            self.assertEqual(results[0].result, "subscriber_ok")
            self.assertEqual(received, ["hello_from_loop"])
        finally:
            loop.close()

    # -------------------------------------------------------------------------
    # BUG-CORE-02: ActionStatus Enum Demotion
    # -------------------------------------------------------------------------
    def test_action_status_enum_preservation_sync(self) -> None:
        """Handler returning ActionStatus enum must preserve the specific status, not demote to FAILED."""
        d = ActionDispatcher()
        d.register_action(
            "blocked_action",
            lambda: {"status": ActionStatus.BLOCKED, "message": "Blocked by policy"}
        )
        d.register_action(
            "unavail_action",
            lambda: {"status": ActionStatus.UNAVAILABLE, "message": "Hardware offline"}
        )

        res_blocked = d.dispatch_action("blocked_action")
        self.assertFalse(res_blocked.success)
        self.assertEqual(res_blocked.status, ActionStatus.BLOCKED)

        res_unavail = d.dispatch_action("unavail_action")
        self.assertFalse(res_unavail.success)
        self.assertEqual(res_unavail.status, ActionStatus.UNAVAILABLE)

    def test_action_status_enum_preservation_async(self) -> None:
        """Async dispatch must preserve ActionStatus enum and not demote to FAILED."""
        d = ActionDispatcher()
        d.register_action(
            "blocked_action_async",
            lambda: {"status": ActionStatus.BLOCKED, "message": "Blocked by policy"}
        )

        async def run_test() -> ActionResult:
            return await d.dispatch_action_async("blocked_action_async")

        res = asyncio.run(run_test())
        self.assertFalse(res.success)
        self.assertEqual(res.status, ActionStatus.BLOCKED)

    # -------------------------------------------------------------------------
    # BUG-CORE-03: RATE_LIMITED and LABS_DISABLED Normalization
    # -------------------------------------------------------------------------
    def test_rate_limited_and_labs_disabled_are_fail_closed(self) -> None:
        """RATE_LIMITED and LABS_DISABLED must be normalized as success=False, not success=True."""
        d = ActionDispatcher()
        d.register_action(
            "rl_action",
            lambda: {"status": ActionStatus.RATE_LIMITED, "message": "Rate limit exceeded"}
        )
        d.register_action(
            "labs_action",
            lambda: {"status": ActionStatus.LABS_DISABLED, "message": "Feature disabled in labs"}
        )
        d.register_action(
            "rl_str_action",
            lambda: {"status": "RATE_LIMITED", "message": "Too many requests"}
        )

        res_rl = d.dispatch_action("rl_action")
        self.assertFalse(res_rl.success)
        self.assertEqual(res_rl.status, ActionStatus.RATE_LIMITED)

        res_labs = d.dispatch_action("labs_action")
        self.assertFalse(res_labs.success)
        self.assertEqual(res_labs.status, ActionStatus.LABS_DISABLED)

        res_rl_str = d.dispatch_action("rl_str_action")
        self.assertFalse(res_rl_str.success)
        self.assertEqual(res_rl_str.status, ActionStatus.RATE_LIMITED)

    # -------------------------------------------------------------------------
    # BUG-CORE-04: Hotkey Argument Splatting in _handle_new_tab
    # -------------------------------------------------------------------------
    def test_new_tab_calls_send_hotkey_with_split_args(self) -> None:
        """_handle_new_tab fallback must call send_hotkey('ctrl', 't'), not send_hotkey('ctrl+t')."""
        app = JarvisApp(headless=True, no_hot_reload=True)
        app.computer_controller = MagicMock()
        app.computer_controller.send_hotkey.return_value = True

        with patch.dict("sys.modules", {"pyautogui": None}):
            res = app._handle_new_tab()
            app.computer_controller.send_hotkey.assert_called_once_with("ctrl", "t")
            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "success")

    # -------------------------------------------------------------------------
    # BUG-CORE-05: Inverted Error/Message Contract in _handle_system_brightness
    # -------------------------------------------------------------------------
    def test_brightness_failure_contract(self) -> None:
        """_handle_system_brightness failure must populate error_code and human Vietnamese error message."""
        app = JarvisApp(headless=True, no_hot_reload=True)
        app.computer_controller = MagicMock()
        app.computer_controller.set_brightness.return_value = None
        app.computer_controller.change_brightness.return_value = None

        # Level failure
        res_set = app._handle_system_brightness(level=50)
        self.assertFalse(res_set["success"])
        self.assertEqual(res_set["error_code"], "BRIGHTNESS_SET_FAILED")
        self.assertIn("Không thể đặt độ sáng màn hình", res_set["error"])
        self.assertEqual(res_set["error"], res_set["message"])

        # Delta failure
        res_delta = app._handle_system_brightness(delta=-10)
        self.assertFalse(res_delta["success"])
        self.assertEqual(res_delta["error_code"], "BRIGHTNESS_CHANGE_FAILED")
        self.assertIn("Không thể điều chỉnh độ sáng màn hình", res_delta["error"])
        self.assertEqual(res_delta["error"], res_delta["message"])

    # -------------------------------------------------------------------------
    # BUG-CORE-06: Grammatical Direction in _handle_system_volume
    # -------------------------------------------------------------------------
    def test_volume_delta_grammar_direction(self) -> None:
        """_handle_system_volume must use 'xuống' when delta is negative and 'lên' when positive."""
        app = JarvisApp(headless=True, no_hot_reload=True)
        app.computer_controller = MagicMock()
        app.computer_controller.change_volume.return_value = 30

        # Negative delta
        res_down = app._handle_system_volume(delta=-15)
        self.assertTrue(res_down["success"])
        self.assertIn("xuống 30%", res_down["message"])

        # Positive delta
        app.computer_controller.change_volume.return_value = 70
        res_up = app._handle_system_volume(delta=20)
        self.assertTrue(res_up["success"])
        self.assertIn("lên 70%", res_up["message"])

    # -------------------------------------------------------------------------
    # BUG-CORE-07: Concurrency in JarvisApp.initialize()
    # -------------------------------------------------------------------------
    def test_concurrent_initialize_thread_safe(self) -> None:
        """Concurrent calls to initialize() must be protected by lock and not duplicate initialization."""
        app = JarvisApp(headless=True, no_hot_reload=True)
        load_count = 0

        orig_load = app.config.load

        def tracked_load() -> None:
            nonlocal load_count
            load_count += 1
            orig_load()

        app.config.load = tracked_load

        threads = [threading.Thread(target=app.initialize) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertTrue(app._initialized)
        self.assertEqual(load_count, 1)

    # -------------------------------------------------------------------------
    # BUG-CORE-08: Resilient Teardown in JarvisApp.stop()
    # -------------------------------------------------------------------------
    def test_stop_continues_when_subsystem_fails(self) -> None:
        """Failure in one subsystem during stop() must not halt cleanup of subsequent subsystems."""
        app = JarvisApp(headless=True, no_hot_reload=True)
        app.overlay = MagicMock()
        app.overlay.destroy.side_effect = RuntimeError("Dead Tk window handle")

        app.tray_controller = MagicMock()
        app.dashboard_server = MagicMock()
        app.audio_engine = MagicMock()
        app.tts_manager = MagicMock()

        app.stop()

        app.tray_controller.stop.assert_called_once()
        app.dashboard_server.stop.assert_called_once()
        app.audio_engine.stop_stream.assert_called_once()
        app.tts_manager.stop.assert_called_once()

    # -------------------------------------------------------------------------
    # BUG-CORE-09: PassiveTriggerGuard Double Lockout Trap
    # -------------------------------------------------------------------------
    def test_passive_trigger_guard_lockout_served_no_re_trip(self) -> None:
        """When lockout_s < window_s, the first trigger after lockout expiration must be allowed, not re-tripped."""
        # max_triggers = 3, window_s = 60.0s, lockout_s = 10.0s
        guard = PassiveTriggerGuard(
            min_rearm_interval_s=1.0,
            max_triggers=3,
            window_s=60.0,
            lockout_s=10.0,
        )
        key = "TEST:trigger"

        # Triggers at t=0, 1, 2 fill capacity (3 triggers)
        for t_sec in [0.0, 1.0, 2.0]:
            dec = guard.try_acquire(key, now=t_sec)
            self.assertTrue(dec.allowed)

        # 4th trigger at t=3.0 trips lockout until t=13.0
        dec_tripped = guard.try_acquire(key, now=3.0)
        self.assertFalse(dec_tripped.allowed)
        self.assertEqual(dec_tripped.reason, "LOCKOUT_TRIPPED")

        # During lockout (e.g. t=8.0), lockout is active
        dec_active = guard.try_acquire(key, now=8.0)
        self.assertFalse(dec_active.allowed)
        self.assertEqual(dec_active.reason, "LOCKOUT_ACTIVE")

        # After lockout expires at t=14.0 (> 13.0), the penalty has been served.
        # It must NOT immediately trip another lockout even though t - 0.0 (14.0) <= window_s (60.0).
        dec_after = guard.try_acquire(key, now=14.0)
        self.assertTrue(
            dec_after.allowed,
            f"Expected trigger to be allowed after serving lockout, but got reason: {dec_after.reason}"
        )
        self.assertEqual(dec_after.reason, "OK")


if __name__ == "__main__":
    unittest.main()

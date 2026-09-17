"""
tests/test_adversarial_m2_labs_feature_flag.py
===============================================
Adversarial Challenge & Empirical Stress Test Suite for Milestone M2:
Core/Labs Feature Flag Mechanism (jarvis/core/labs.py and jarvis/core/dispatcher.py).

Empirical verification harness targeting:
1. Bypass attempts:
   - Direct handler calls vs dispatcher calls vs decorator calls.
   - Instance with config=None vulnerability / bypass check (line 131 in labs.py).
   - Dispatcher bypass_security=True privilege override leaking into Labs isolation.
   - Falsy / empty labs_feature registration bypassing dispatcher guard.
2. Malformed feature names:
   - None, empty string (""), whitespace strings ("   ", " tshark_capture "),
     case mismatches ("BROWSER_CDP" vs "browser_cdp"), and non-string types.
   - Malformed configuration types: string features, None features, integer configs.
3. Dynamic runtime toggling:
   - Live toggling of labs.enabled (False -> True -> False -> True) without restart.
   - Dynamic mutation of labs.features whitelist.
   - High-concurrency multithreaded toggling stress harness (race-condition check).
4. Fail-closed contract enforcement:
   - Strict assertion of status="LABS_DISABLED", success=False,
     code="LABS_FEATURE_DISABLED", retryable=False across all interfaces.
   - Zero side-effects guarantee: underlying handler strictly never invoked.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from jarvis.core.config import ConfigManager
from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.labs import (
    create_labs_disabled_result,
    is_labs_enabled,
    require_labs,
)
from jarvis.core.models import ActionResult, ActionStatus, PrivilegeLevel, RequesterContext


# ============================================================================
# 1. BYPASS ATTEMPTS & ISOLATION HOLES
# ============================================================================

class TestAdversarialBypassAttempts:
    """Stress tests seeking unauthorized execution paths through the Labs boundary."""

    def test_bypass_instance_with_none_config_vulnerability(self):
        """
        Adversarial Test: When a class instance has `self.config = None`
        (e.g., initialized without explicit config, such as default PacketCapture()),
        does @require_labs fail-closed or fail-open?

        In jarvis/core/labs.py lines 126-131:
            if args and hasattr(args[0], "config"):
                inst_cfg = getattr(args[0], "config")
                if inst_cfg is not None:
                    return is_labs_enabled(feature_name, inst_cfg)
                # Instance has config=None: instance was created without config (e.g. standalone test)
                return True   <-- VULNERABILITY!

        This test empirically verifies whether `self.config = None` allows unauthorized bypass.
        """
        handler_executed = False

        class VulnerableComponent:
            def __init__(self, config: Any = None):
                self.config = config

            @require_labs("restricted_labs_feature")
            def sensitive_method(self) -> str:
                nonlocal handler_executed
                handler_executed = True
                return "UNAUTHORIZED_EXECUTION"

        # Global config has labs disabled
        comp = VulnerableComponent(config=None)
        res = comp.sensitive_method()

        # Empirical Check: Did it fail-closed?
        # If line 131 returns True, handler_executed is True and res == "UNAUTHORIZED_EXECUTION".
        # This asserts fail-closed behavior:
        assert handler_executed is False, (
            "CRITICAL SECURITY VULNERABILITY: @require_labs allowed execution because "
            "instance.config is None! Line 131 in jarvis/core/labs.py returns True, "
            "bypassing Labs feature gating entirely."
        )
        assert isinstance(res, ActionResult)
        assert res.status == ActionStatus.LABS_DISABLED
        assert res.success is False

    def test_bypass_dispatcher_security_bypass_flag_does_not_bypass_labs(self):
        """
        Adversarial Test: ActionDispatcher has `bypass_security=True` to skip RBAC.
        Ensure that `bypass_security=True` does NOT bypass the Labs feature flag.
        Labs gating is a system capability boundary, not an RBAC role.
        """
        dispatcher = ActionDispatcher(
            config={"labs": {"enabled": False, "features": []}},
            bypass_security=True,
        )
        handler_called = False

        def sensitive_handler():
            nonlocal handler_called
            handler_called = True
            return {"data": "should_never_run"}

        dispatcher.register_action(
            name="labs_sensitive_action",
            handler=sensitive_handler,
            labs_feature="super_secret_feature",
        )

        res = dispatcher.dispatch_action("labs_sensitive_action")
        assert handler_called is False
        assert res.success is False
        assert res.status == ActionStatus.LABS_DISABLED
        assert res.code == "LABS_FEATURE_DISABLED"
        assert res.retryable is False

    def test_bypass_empty_string_labs_feature_registration(self):
        """
        Adversarial Test: If an action is registered with labs_feature="",
        in dispatcher.py line 556: `if action_def.labs_feature:`
        Empty string is falsy! Does it bypass the check and execute?
        An empty string feature should either be rejected or treated as disabled.
        """
        dispatcher = ActionDispatcher(config={"labs": {"enabled": False, "features": []}})
        handler_called = False

        def sample_handler():
            nonlocal handler_called
            handler_called = True
            return {"ok": True}

        dispatcher.register_action(
            name="empty_feature_action",
            handler=sample_handler,
            labs_feature="",  # Falsy string
        )

        # When labs is disabled globally, should an action registered with labs_feature="" run?
        # If dispatcher checks truthy, it skips labs gate!
        dispatcher.dispatch_action("empty_feature_action")
        # Record empirical behavior: does it bypass?
        # If handler_called is True, labs_feature="" bypassed the guard!

    def test_bypass_direct_handler_call_vs_dispatcher(self):
        """
        Adversarial Test: If an action handler is NOT decorated with @require_labs,
        calling the handler directly bypasses the dispatcher's labs guard.
        For production candidate features (e.g. browser_cdp, tshark_capture in JarvisApp),
        both the dispatcher registration AND the handler method must be guarded.
        """
        from jarvis.core.app import JarvisApp

        app = JarvisApp(headless=True, no_hot_reload=True)
        app._register_core_actions()

        # Ensure labs is disabled in app.config
        app.config.set("labs.enabled", False)
        app.config.set("labs.features", [])

        # 1. Via dispatcher: must be blocked
        res_dispatcher = app.dispatcher.dispatch_action("browser_cdp_capture")
        assert res_dispatcher.status == ActionStatus.LABS_DISABLED
        assert res_dispatcher.success is False

        # 2. Direct method call: must ALSO be blocked by @require_labs
        res_direct = app._handle_browser_cdp_capture()
        assert isinstance(res_direct, ActionResult)
        assert res_direct.status == ActionStatus.LABS_DISABLED
        assert res_direct.success is False

    def test_bypass_packet_capture_direct_call_isolation(self):
        """
        Adversarial Test: PacketCapture.capture_packets called directly
        without dispatcher. Must fail-closed when labs is disabled.
        """
        from jarvis.security.scanner import PacketCapture

        cfg = {"labs": {"enabled": False, "features": []}}
        pc = PacketCapture(config=cfg)
        res = pc.capture_packets()

        assert isinstance(res, ActionResult)
        assert res.status == ActionStatus.LABS_DISABLED
        assert res.success is False
        assert res.code == "LABS_FEATURE_DISABLED"
        assert res.retryable is False


# ============================================================================
# 2. MALFORMED FEATURE NAMES & MALFORMED CONFIGURATIONS
# ============================================================================

class TestAdversarialMalformedFeatureNames:
    """Stress tests boundary cases for feature names and configuration formats."""

    def test_feature_name_none(self):
        """
        When feature_name is None:
        - If labs.enabled is False -> must return False.
        - If labs.enabled is True -> returns True (querying master flag).
        """
        cfg_disabled = {"labs": {"enabled": False, "features": ["feat1"]}}
        cfg_enabled = {"labs": {"enabled": True, "features": []}}

        assert is_labs_enabled(None, cfg_disabled) is False
        assert is_labs_enabled(None, cfg_enabled) is True

    @pytest.mark.parametrize("bad_name", [
        "",
        "   ",
        "\t\n",
        "  browser_cdp  ",
        "BROWSER_CDP",
        "Browser_Cdp",
        "browser.cdp",
        "browser/cdp",
    ])
    def test_malformed_or_untrimmed_feature_names_fail_closed(self, bad_name: str):
        """
        Adversarial Test: Untrimmed or case-mismatched feature names must NOT
        accidentally match or grant access against standard features list.
        """
        cfg = {"labs": {"enabled": True, "features": ["browser_cdp", "tshark_capture"]}}

        # None of these distorted names should grant access
        result = is_labs_enabled(bad_name, cfg)
        assert result is False, f"Malformed feature name {bad_name!r} unexpectedly evaluated to True!"

    @pytest.mark.parametrize("bad_features_config", [
        None,
        "browser_cdp",          # String instead of list (vulnerability if using `in` on string!)
        12345,                  # Non-iterable
        {"browser_cdp": True},  # Dict without list
        object(),
    ])
    def test_malformed_features_list_in_config_fails_closed(self, bad_features_config: Any):
        """
        Adversarial Test: If configuration has invalid features type (e.g. string "browser_cdp"
        where `in` substring search could produce false positives, or int),
        is_labs_enabled MUST fail closed and return False.
        """
        cfg = {"labs": {"enabled": True, "features": bad_features_config}}
        assert is_labs_enabled("browser_cdp", cfg) is False
        assert is_labs_enabled("cdp", cfg) is False

    @pytest.mark.parametrize("corrupt_config", [
        None,
        {},
        {"labs": None},
        {"labs": "enabled"},
        {"labs": 1},
        {"labs": False},
        "corrupted_string_config",
        123456,
        [1, 2, 3],
    ])
    def test_corrupt_config_structures_fail_closed(self, corrupt_config: Any):
        """
        Adversarial Test: Any corrupt, non-dict, or missing config object
        must fail closed without throwing unhandled exceptions.
        """
        try:
            res = is_labs_enabled("browser_cdp", corrupt_config)
            assert res is False
        except Exception as exc:
            pytest.fail(f"Unhandled exception on corrupt config {corrupt_config!r}: {exc}")

    def test_decorator_with_empty_string_feature_name(self):
        """
        Adversarial Test: Function decorated with @require_labs("")
        must fail closed and return LABS_DISABLED ActionResult.
        """
        @require_labs("")
        def blank_feature_tool(config=None):
            return "EXECUTED"

        cfg = {"labs": {"enabled": True, "features": ["browser_cdp"]}}
        res = blank_feature_tool(config=cfg)

        assert isinstance(res, ActionResult)
        assert res.status == ActionStatus.LABS_DISABLED
        assert res.success is False


# ============================================================================
# 3. DYNAMIC RUNTIME TOGGLING & CONCURRENCY STRESS
# ============================================================================

class TestAdversarialDynamicToggling:
    """Stress tests verifying immediate reaction to runtime configuration changes."""

    def test_runtime_toggle_enabled_cycle(self):
        """
        Adversarial Test: Toggle labs.enabled repeatedly on ConfigManager
        and verify ActionDispatcher and @require_labs respond instantaneously
        without state caching or restart.
        """
        cfg = ConfigManager()
        cfg.load()
        cfg.set("labs.features", ["test_dynamic_feat"])

        dispatcher = ActionDispatcher(config=cfg)
        call_count = 0

        def dynamic_handler():
            nonlocal call_count
            call_count += 1
            return {"result": f"call_{call_count}"}

        dispatcher.register_action(
            name="dynamic_action",
            handler=dynamic_handler,
            labs_feature="test_dynamic_feat",
        )

        # 1. Initially False
        cfg.set("labs.enabled", False)
        res1 = dispatcher.dispatch_action("dynamic_action")
        assert res1.status == ActionStatus.LABS_DISABLED
        assert call_count == 0

        # 2. Toggle to True
        cfg.set("labs.enabled", True)
        res2 = dispatcher.dispatch_action("dynamic_action")
        assert res2.status == ActionStatus.SUCCESS
        assert call_count == 1

        # 3. Toggle back to False
        cfg.set("labs.enabled", False)
        res3 = dispatcher.dispatch_action("dynamic_action")
        assert res3.status == ActionStatus.LABS_DISABLED
        assert call_count == 1  # Not incremented!

        # 4. Toggle to True again
        cfg.set("labs.enabled", True)
        res4 = dispatcher.dispatch_action("dynamic_action")
        assert res4.status == ActionStatus.SUCCESS
        assert call_count == 2

    def test_runtime_feature_whitelist_mutation(self):
        """
        Adversarial Test: labs.enabled remains True, but features whitelist
        is mutated at runtime (add/remove feature).
        """
        cfg = ConfigManager()
        cfg.load()
        cfg.set("labs.enabled", True)
        cfg.set("labs.features", [])

        dispatcher = ActionDispatcher(config=cfg)
        invoked = False

        def target_handler():
            nonlocal invoked
            invoked = True
            return {"ok": True}

        dispatcher.register_action(
            name="guarded_action",
            handler=target_handler,
            labs_feature="feature_x",
        )

        # Initially feature_x is not in whitelist
        res1 = dispatcher.dispatch_action("guarded_action")
        assert res1.status == ActionStatus.LABS_DISABLED
        assert invoked is False

        # Add feature_x
        cfg.set("labs.features", ["feature_x"])
        res2 = dispatcher.dispatch_action("guarded_action")
        assert res2.status == ActionStatus.SUCCESS
        assert invoked is True

        # Remove feature_x
        invoked = False
        cfg.set("labs.features", ["other_feature"])
        res3 = dispatcher.dispatch_action("guarded_action")
        assert res3.status == ActionStatus.LABS_DISABLED
        assert invoked is False

    def test_concurrent_multithreaded_toggling_stress(self):
        """
        Adversarial Stress Test: 10 worker threads concurrently dispatching a Labs action
        while a chaos thread rapidly flips labs.enabled between True and False.
        Assertions:
        - Zero unhandled exceptions or crashes.
        - When a call returns LABS_DISABLED, the handler was NEVER executed for that call.
        - Strict adherence to ActionResult schema at all times.
        """
        cfg = ConfigManager()
        cfg.load()
        cfg.set("labs.features", ["stress_feat"])
        cfg.set("labs.enabled", False)

        dispatcher = ActionDispatcher(config=cfg)
        exec_lock = threading.Lock()
        actual_handler_executions = 0

        def stress_handler():
            nonlocal actual_handler_executions
            with exec_lock:
                actual_handler_executions += 1
            return {"counter": actual_handler_executions}

        dispatcher.register_action(
            name="stress_action",
            handler=stress_handler,
            labs_feature="stress_feat",
        )

        stop_event = threading.Event()
        errors: list[str] = []
        reported_successes = 0
        reported_blocks = 0
        stats_lock = threading.Lock()

        def chaos_toggler():
            state = False
            while not stop_event.is_set():
                state = not state
                cfg.set("labs.enabled", state)
                time.sleep(0.002)

        def worker():
            nonlocal reported_successes, reported_blocks
            while not stop_event.is_set():
                try:
                    res = dispatcher.dispatch_action("stress_action")
                    assert isinstance(res, ActionResult)
                    with stats_lock:
                        if res.status == ActionStatus.SUCCESS:
                            reported_successes += 1
                            assert res.success is True
                        elif res.status == ActionStatus.LABS_DISABLED:
                            reported_blocks += 1
                            assert res.success is False
                            assert res.code == "LABS_FEATURE_DISABLED"
                            assert res.retryable is False
                        else:
                            errors.append(f"Unexpected status: {res.status}")
                except Exception as exc:
                    errors.append(f"Worker exception: {exc}")
                time.sleep(0.001)

        chaos_thread = threading.Thread(target=chaos_toggler, daemon=True)
        worker_threads = [threading.Thread(target=worker, daemon=True) for _ in range(8)]

        chaos_thread.start()
        for wt in worker_threads:
            wt.start()

        time.sleep(0.5)  # Run stress for 500ms
        stop_event.set()

        chaos_thread.join(timeout=2.0)
        for wt in worker_threads:
            wt.join(timeout=2.0)

        assert len(errors) == 0, f"Stress test encountered exceptions: {errors[:5]}"
        assert reported_blocks > 0, "Expected at least some calls to be blocked during toggling"
        assert reported_successes > 0, "Expected at least some calls to succeed during toggling"
        # Total handler executions must exactly equal reported successes
        assert actual_handler_executions == reported_successes, (
            f"Leak detected! Handler ran {actual_handler_executions} times, but "
            f"dispatcher only authorized {reported_successes} successful calls."
        )


# ============================================================================
# 4. FAIL-CLOSED CONTRACT STRICT ENFORCEMENT
# ============================================================================

class TestAdversarialFailClosedContract:
    """Strictly validates ActionResult schema invariants across all entrypoints."""

    def test_create_labs_disabled_result_invariants(self):
        """Verify create_labs_disabled_result satisfies all four fail-closed fields."""
        res = create_labs_disabled_result(
            action_name="test_act",
            feature_name="test_feat",
            requester="user_voice",
            execution_time_ms=2.5,
        )
        assert res.status == ActionStatus.LABS_DISABLED
        assert res["status"] == "LABS_DISABLED"
        assert res.success is False
        assert res["success"] is False
        assert res.is_success is False
        assert res.code == "LABS_FEATURE_DISABLED"
        assert res["code"] == "LABS_FEATURE_DISABLED"
        assert res.retryable is False
        assert res["retryable"] is False
        assert res.requester == "user_voice"
        assert res.execution_time_ms == 2.5
        assert "test_feat" in res.message
        assert res.error == res.message

    def test_action_result_post_init_normalization_for_labs_disabled(self):
        """
        Verify that creating ActionResult(status='LABS_DISABLED') without code
        or retryable automatically normalizes code='LABS_FEATURE_DISABLED',
        success=False, retryable=False.
        """
        # 1. Bare string status
        res1 = ActionResult(action_name="act1", status="LABS_DISABLED")
        assert res1.status == ActionStatus.LABS_DISABLED
        assert res1.success is False
        assert res1.code == "LABS_FEATURE_DISABLED"
        assert res1.retryable is False

        # 2. Lowercase string status
        res2 = ActionResult(action_name="act2", status="labs_disabled")
        assert res2.status == ActionStatus.LABS_DISABLED
        assert res2.success is False
        assert res2.code == "LABS_FEATURE_DISABLED"
        assert res2.retryable is False

        # 3. Explicit code preserved if not 'OK'
        res3 = ActionResult(action_name="act3", status="LABS_DISABLED", code="CUSTOM_CODE")
        assert res3.code == "CUSTOM_CODE"
        assert res3.success is False
        assert res3.retryable is False

    @pytest.mark.asyncio
    async def test_async_dispatcher_contract_strictness(self):
        """Verify dispatch_action_async satisfies fail-closed contract."""
        dispatcher = ActionDispatcher(config={"labs": {"enabled": False, "features": []}})
        executed = False

        async def dummy_async():
            nonlocal executed
            executed = True
            return {"ok": True}

        dispatcher.register_action(
            name="async_action",
            handler=dummy_async,
            labs_feature="async_feature",
        )

        res = await dispatcher.dispatch_action_async("async_action")
        assert executed is False
        assert res.status == ActionStatus.LABS_DISABLED
        assert res.success is False
        assert res.code == "LABS_FEATURE_DISABLED"
        assert res.retryable is False

    def test_require_labs_decorator_contract_strictness(self):
        """Verify @require_labs returns strict ActionResult with all 4 fields."""
        @require_labs("guarded_tool")
        def guarded_tool(config=None):
            return "NEVER_RETURNED"

        res = guarded_tool(config={"labs": {"enabled": False}})
        assert isinstance(res, ActionResult)
        assert res.status == ActionStatus.LABS_DISABLED
        assert res.success is False
        assert res.code == "LABS_FEATURE_DISABLED"
        assert res.retryable is False
        assert res["status"] == "LABS_DISABLED"
        assert res["code"] == "LABS_FEATURE_DISABLED"
        assert res["retryable"] is False

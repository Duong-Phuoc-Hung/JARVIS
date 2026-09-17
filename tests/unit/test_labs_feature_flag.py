"""
tests/unit/test_labs_feature_flag.py
====================================
Comprehensive Test Suite for Core/Labs Feature Flag Mechanism (Requirement R6).

Validates:
  1. Default config: labs.enabled=False, labs.features=[].
  2. Dot-notation config access and in-memory mutation.
  3. Environment variable override support.
  4. is_labs_enabled logic for all permutations (enabled/disabled, feature listed/missing).
  5. create_labs_disabled_result contract and fail-closed fields (success=False, retryable=False, LABS_DISABLED).
  6. ActionStatus enum expansion with LABS_DISABLED and ActionResult harmonization.
  7. ActionDispatcher blocks disabled Labs actions (status=LABS_DISABLED, handler never invoked).
  8. ActionDispatcher executes enabled Labs actions normally.
  9. ActionDispatcher blocks when labs.enabled=True but requested feature not in labs.features.
  10. Async ActionDispatcher exhibits identical fail-closed behavior.
  11. @require_labs decorator blocks direct sync calls when disabled.
  12. @require_labs decorator executes direct sync calls when enabled.
  13. @require_labs decorator handles coroutines correctly (async block and execute).
  14. Candidate 1: browser_cdp_capture action tested via ActionDispatcher.
  15. Candidate 2: tshark_capture action tested via ActionDispatcher.
  16. PacketCapture direct method call respects config when passed.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from jarvis.core.config import ConfigManager
from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.labs import (
    create_labs_disabled_result,
    is_labs_enabled,
    require_labs,
)
from jarvis.core.models import ActionResult, ActionStatus
from jarvis.security.scanner import PacketCapture


# ── 1. Configuration System Tests ─────────────────────────────────────────────

def test_default_config_labs_disabled_and_empty_features():
    """Verify default configuration has labs.enabled=False and labs.features=[]."""
    cfg = ConfigManager()
    cfg.load()
    assert cfg.get("labs.enabled") is False
    assert cfg.get("labs.features") == []
    assert cfg.labs.enabled is False
    assert cfg.labs.features == []


def test_config_labs_dot_notation_and_mutation():
    """Verify dot-notation read and write works cleanly for labs section."""
    cfg = ConfigManager()
    cfg.load()

    cfg.set("labs.enabled", True)
    cfg.set("labs.features", ["browser_cdp", "tshark_capture"])

    assert cfg.get("labs.enabled") is True
    assert cfg.get("labs.features") == ["browser_cdp", "tshark_capture"]
    assert cfg.labs.enabled is True
    assert cfg.labs.features == ["browser_cdp", "tshark_capture"]


def test_config_labs_legacy_env_var_override(monkeypatch):
    """Verify JARVIS_LABS_ENABLED legacy environment variable activates labs."""
    monkeypatch.setenv("JARVIS_LABS_ENABLED", "true")
    cfg = ConfigManager()
    cfg.load()
    assert cfg.get("labs.enabled") is True
    assert cfg.labs.enabled is True


# ── 2. is_labs_enabled Logic Tests ───────────────────────────────────────────

def test_is_labs_enabled_permutations():
    """Verify is_labs_enabled under all boolean and list combinations."""
    # 1. labs.enabled = False, features = []
    cfg_disabled = {"labs": {"enabled": False, "features": []}}
    assert is_labs_enabled(None, cfg_disabled) is False
    assert is_labs_enabled("browser_cdp", cfg_disabled) is False

    # 2. labs.enabled = False, features = ["browser_cdp"] (fail-closed!)
    cfg_feature_only = {"labs": {"enabled": False, "features": ["browser_cdp"]}}
    assert is_labs_enabled("browser_cdp", cfg_feature_only) is False

    # 3. labs.enabled = True, features = []
    cfg_master_only = {"labs": {"enabled": True, "features": []}}
    assert is_labs_enabled(None, cfg_master_only) is True
    assert is_labs_enabled("browser_cdp", cfg_master_only) is False

    # 4. labs.enabled = True, features = ["tshark_capture"]
    cfg_tshark = {"labs": {"enabled": True, "features": ["tshark_capture"]}}
    assert is_labs_enabled("browser_cdp", cfg_tshark) is False
    assert is_labs_enabled("tshark_capture", cfg_tshark) is True

    # 5. labs.enabled = True, features = ["browser_cdp", "tshark_capture"]
    cfg_both = {"labs": {"enabled": True, "features": ["browser_cdp", "tshark_capture"]}}
    assert is_labs_enabled("browser_cdp", cfg_both) is True
    assert is_labs_enabled("tshark_capture", cfg_both) is True
    assert is_labs_enabled("unregistered_feature", cfg_both) is False


def test_is_labs_enabled_with_config_manager():
    """Verify is_labs_enabled operates against a structured ConfigManager."""
    cfg = ConfigManager()
    cfg.load()
    assert is_labs_enabled("browser_cdp", cfg) is False

    cfg.set("labs.enabled", True)
    cfg.set("labs.features", ["browser_cdp"])
    assert is_labs_enabled("browser_cdp", cfg) is True
    assert is_labs_enabled("tshark_capture", cfg) is False


# ── 3. Result Model & Harmonization Tests ─────────────────────────────────────

def test_create_labs_disabled_result_structure():
    """Verify create_labs_disabled_result constructs authoritative fail-closed ActionResult."""
    res = create_labs_disabled_result(
        action_name="browser_cdp_capture",
        feature_name="browser_cdp",
        requester="planner",
        execution_time_ms=1.5,
    )
    assert res.success is False
    assert res.status == ActionStatus.LABS_DISABLED
    assert res["status"] == "LABS_DISABLED"
    assert res.code == "LABS_FEATURE_DISABLED"
    assert res["code"] == "LABS_FEATURE_DISABLED"
    assert res.retryable is False
    assert res["retryable"] is False
    assert "browser_cdp" in res.message
    assert res.error == res.message
    assert res.error_code == "LABS_FEATURE_DISABLED"
    assert res.requester == "planner"
    assert res.execution_time_ms == 1.5
    assert res.data == {
        "feature_name": "browser_cdp",
        "status": "LABS_DISABLED",
        "reason": "Feature flag not enabled in configuration",
    }


def test_action_status_enum_and_post_init_harmonization():
    """Verify ActionStatus.LABS_DISABLED enum and automatic harmonization."""
    assert ActionStatus.LABS_DISABLED == "LABS_DISABLED"
    assert ActionStatus("LABS_DISABLED") == ActionStatus.LABS_DISABLED

    # String input normalized to ActionStatus enum with automatic success=False
    res = ActionResult(action_name="test_action", status="LABS_DISABLED")
    assert res.status == ActionStatus.LABS_DISABLED
    assert res.success is False
    assert res.code == "LABS_FEATURE_DISABLED"
    assert res.retryable is False

    # Explicit custom error_code preserved
    res2 = ActionResult(action_name="test_action", status="LABS_DISABLED", code="CUSTOM_CODE")
    assert res2.code == "CUSTOM_CODE"
    assert res2.success is False
    assert res2.retryable is False


# ── 4. ActionDispatcher Integration Tests ─────────────────────────────────────

def test_dispatcher_blocks_disabled_labs_action():
    """Verify dispatcher rejects an action when labs is disabled, handler never executes."""
    dispatcher = ActionDispatcher(config={"labs": {"enabled": False, "features": []}})
    handler_executed = False

    def test_handler():
        nonlocal handler_executed
        handler_executed = True
        return {"data": "should_not_run"}

    dispatcher.register_action(
        name="test_labs_action",
        handler=test_handler,
        labs_feature="test_feature",
    )

    result = dispatcher.dispatch_action("test_labs_action")

    assert handler_executed is False
    assert result.success is False
    assert result.status == ActionStatus.LABS_DISABLED
    assert result.code == "LABS_FEATURE_DISABLED"
    assert result.retryable is False
    assert "test_feature" in result.message


def test_dispatcher_executes_enabled_labs_action():
    """Verify dispatcher executes action when labs.enabled=True and feature is in features."""
    dispatcher = ActionDispatcher(
        config={"labs": {"enabled": True, "features": ["test_feature"]}}
    )
    handler_executed = False

    def test_handler():
        nonlocal handler_executed
        handler_executed = True
        return {"data": "executed_successfully"}

    dispatcher.register_action(
        name="test_labs_action",
        handler=test_handler,
        labs_feature="test_feature",
    )

    result = dispatcher.dispatch_action("test_labs_action")

    assert handler_executed is True
    assert result.success is True
    assert result.status == ActionStatus.SUCCESS
    assert result.data == {"data": "executed_successfully"}


def test_dispatcher_blocks_when_feature_not_in_whitelist():
    """Verify dispatcher blocks action when labs is enabled but specific feature is missing."""
    dispatcher = ActionDispatcher(
        config={"labs": {"enabled": True, "features": ["other_feature"]}}
    )
    handler_executed = False

    def test_handler():
        nonlocal handler_executed
        handler_executed = True
        return {"data": "should_not_run"}

    dispatcher.register_action(
        name="test_labs_action",
        handler=test_handler,
        labs_feature="target_feature",
    )

    result = dispatcher.dispatch_action("test_labs_action")

    assert handler_executed is False
    assert result.status == ActionStatus.LABS_DISABLED
    assert result.code == "LABS_FEATURE_DISABLED"
    assert result.success is False


@pytest.mark.asyncio
async def test_async_dispatcher_labs_guard():
    """Verify dispatch_action_async honors the labs feature flag check."""
    dispatcher = ActionDispatcher(config={"labs": {"enabled": False, "features": []}})
    handler_called = False

    async def async_handler():
        nonlocal handler_called
        handler_called = True
        return {"ok": True}

    dispatcher.register_action(
        name="async_labs_action",
        handler=async_handler,
        labs_feature="async_feature",
    )

    # 1. Blocked when disabled
    result = await dispatcher.dispatch_action_async("async_labs_action")
    assert handler_called is False
    assert result.status == ActionStatus.LABS_DISABLED
    assert result.success is False

    # 2. Permitted when enabled
    dispatcher.config = {"labs": {"enabled": True, "features": ["async_feature"]}}
    result_enabled = await dispatcher.dispatch_action_async("async_labs_action")
    assert handler_called is True
    assert result_enabled.status == ActionStatus.SUCCESS
    assert result_enabled.success is True


# ── 5. @require_labs Decorator Tests ──────────────────────────────────────────

def test_require_labs_decorator_sync():
    """Verify @require_labs blocks sync function when disabled and executes when enabled."""
    called = False

    @require_labs("my_sync_tool")
    def sync_tool(config=None):
        nonlocal called
        called = True
        return "completed"

    # Blocked
    res_disabled = sync_tool(config={"labs": {"enabled": False}})
    assert called is False
    assert res_disabled.status == ActionStatus.LABS_DISABLED
    assert res_disabled.success is False

    # Allowed
    res_enabled = sync_tool(config={"labs": {"enabled": True, "features": ["my_sync_tool"]}})
    assert called is True
    assert res_enabled == "completed"


@pytest.mark.asyncio
async def test_require_labs_decorator_async():
    """Verify @require_labs blocks async function when disabled and executes when enabled."""
    called = False

    @require_labs("my_async_tool")
    async def async_tool(config=None):
        nonlocal called
        called = True
        return "async_completed"

    # Blocked
    res_disabled = await async_tool(config={"labs": {"enabled": False}})
    assert called is False
    assert res_disabled.status == ActionStatus.LABS_DISABLED
    assert res_disabled.success is False

    # Allowed
    res_enabled = await async_tool(config={"labs": {"enabled": True, "features": ["my_async_tool"]}})
    assert called is True
    assert res_enabled == "async_completed"


def test_require_labs_standalone_function_respects_global_config():
    """Verify standalone function without config argument checks global ConfigManager."""
    from jarvis.core.config import get_config
    cfg = get_config()

    orig_enabled = cfg.get("labs.enabled", False)
    orig_features = list(cfg.get("labs.features", []))

    try:
        cfg.set("labs.enabled", False)
        cfg.set("labs.features", [])

        @require_labs("standalone_tool")
        def standalone_tool():
            return "ok"

        # Blocked by global config
        res = standalone_tool()
        assert isinstance(res, ActionResult)
        assert res.status == ActionStatus.LABS_DISABLED

        # Enabled by global config
        cfg.set("labs.enabled", True)
        cfg.set("labs.features", ["standalone_tool"])

        res2 = standalone_tool()
        assert res2 == "ok"
    finally:
        cfg.set("labs.enabled", orig_enabled)
        cfg.set("labs.features", orig_features)


# ── 6. Candidate Actions via JarvisApp / Dispatcher ───────────────────────────

def test_candidate_browser_cdp_capture_via_dispatcher():
    """Verify browser_cdp_capture action registered in app.py is gated by labs flag."""
    from jarvis.core.app import JarvisApp
    app = JarvisApp(headless=True, no_hot_reload=True)
    app._register_core_actions()

    # By default, labs is disabled
    res_disabled = app.dispatcher.dispatch_action("browser_cdp_capture")
    assert res_disabled.status == ActionStatus.LABS_DISABLED
    assert res_disabled.code == "LABS_FEATURE_DISABLED"
    assert res_disabled.success is False

    # Enable browser_cdp in app.config
    app.config.set("labs.enabled", True)
    app.config.set("labs.features", ["browser_cdp"])

    res_enabled = app.dispatcher.dispatch_action("browser_cdp_capture")
    # Action was allowed through the dispatcher Labs gate
    assert res_enabled.status != ActionStatus.LABS_DISABLED
    assert res_enabled.code != "LABS_FEATURE_DISABLED"
    # When Labs is enabled and Chrome is not running, it truthfully fails closed
    assert res_enabled.status == "FAILED"
    assert res_enabled.code == "CDP_ENDPOINT_UNAVAILABLE"
    assert res_enabled.success is False


def test_candidate_tshark_capture_via_dispatcher():
    """Verify tshark_capture action registered in app.py is gated by labs flag."""
    from jarvis.core.app import JarvisApp
    app = JarvisApp(headless=True, no_hot_reload=True)
    app._register_core_actions()

    # By default, labs is disabled
    res_disabled = app.dispatcher.dispatch_action("tshark_capture")
    assert res_disabled.status == ActionStatus.LABS_DISABLED
    assert res_disabled.code == "LABS_FEATURE_DISABLED"
    assert res_disabled.success is False

    # Enable tshark_capture in app.config
    app.config.set("labs.enabled", True)
    app.config.set("labs.features", ["tshark_capture"])

    with patch("jarvis.security.scanner.resolve_tshark_binary", return_value=None):
        res_enabled = app.dispatcher.dispatch_action("tshark_capture")
        # Allowed through dispatcher Labs gate (underlying handler reached and reported TOOL_NOT_FOUND)
        assert res_enabled.status != ActionStatus.LABS_DISABLED
        assert res_enabled.code != "LABS_FEATURE_DISABLED"
        assert res_enabled.data["status"] == "TOOL_NOT_FOUND"


def test_packet_capture_direct_call_with_config():
    """Verify PacketCapture.capture_packets respects config when provided."""
    cfg_disabled = {"labs": {"enabled": False, "features": []}}
    pc = PacketCapture(config=cfg_disabled)

    # With disabled config, capture_packets returns LABS_DISABLED
    res = pc.capture_packets()
    assert res.status == ActionStatus.LABS_DISABLED
    assert res["status"] == "LABS_DISABLED"
    assert res.code == "LABS_FEATURE_DISABLED"
    assert res.success is False

    # With enabled config, capture_packets proceeds to normal execution
    cfg_enabled = {"labs": {"enabled": True, "features": ["tshark_capture"]}}
    pc_enabled = PacketCapture(config=cfg_enabled)
    with patch("jarvis.security.scanner.resolve_tshark_binary", return_value=None):
        res_enabled = pc_enabled.capture_packets()
        assert res_enabled.status == "TOOL_NOT_FOUND"


def test_packet_capture_direct_call_default_none_config_fails_closed():
    """
    Verify PacketCapture.capture_packets with default config=None fails closed
    when labs is disabled in global configuration (verifying backdoor is closed).
    """
    from jarvis.core.config import get_config
    cfg = get_config()
    orig_enabled = cfg.get("labs.enabled", False)
    orig_features = list(cfg.get("labs.features", []))

    try:
        cfg.set("labs.enabled", False)
        cfg.set("labs.features", [])

        pc_default = PacketCapture()  # default config=None
        res = pc_default.capture_packets()
        assert isinstance(res, ActionResult)
        assert res.status == ActionStatus.LABS_DISABLED
        assert res.status == "LABS_DISABLED"
        assert res.code == "LABS_FEATURE_DISABLED"
        assert res.success is False
        assert res.retryable is False
    finally:
        cfg.set("labs.enabled", orig_enabled)
        cfg.set("labs.features", orig_features)



# NOTE: Concurrency and async adversarial tests for M2 are in their own dedicated file:
# tests/unit/test_adversarial_m2_concurrency_labs.py
# Do NOT wildcard-import test modules — pytest collects them automatically.

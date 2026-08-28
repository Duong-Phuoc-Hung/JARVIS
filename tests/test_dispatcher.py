"""
tests/test_dispatcher.py
========================
Test Suite for Action Dispatcher, Event Bus, and Privilege Gating.
Covering:
  - F-08: Dynamic Action Dispatcher (Sync/Async execution, Priority Event Bus, Wildcards, Error Isolation, RBAC)
"""

import asyncio
import time
from typing import Any, Dict, List

import pytest

from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import (
    ActionResult,
    HandlerResult,
    PrivilegeLevel,
    RequesterContext,
)

# ============================================================================
# TIER 1: FEATURE COVERAGE HAPPY PATHS
# ============================================================================

def test_event_bus_priority_ordering_tier1():
    """
    [F-08] Validate EventBus executes subscribers in descending priority order.
    """
    bus = EventBus()
    execution_order = []

    bus.subscribe("test.event", lambda **kw: execution_order.append("low"), priority=10)
    bus.subscribe("test.event", lambda **kw: execution_order.append("high"), priority=100)
    bus.subscribe("test.event", lambda **kw: execution_order.append("med"), priority=50)

    results = bus.publish("test.event")
    assert len(results) == 3
    assert execution_order == ["high", "med", "low"]


def test_event_bus_wildcard_matching_tier1():
    """
    [F-08] Validate EventBus wildcard topic matching (e.g. 'audio.*' matches 'audio.clap').
    """
    bus = EventBus()
    received_events = []

    bus.subscribe("audio.*", lambda **kw: received_events.append("audio_wildcard"))
    bus.subscribe("*", lambda **kw: received_events.append("global_wildcard"))
    bus.subscribe("system.status", lambda **kw: received_events.append("system_exact"))

    bus.publish("audio.clap", type="double")
    assert "audio_wildcard" in received_events
    assert "global_wildcard" in received_events
    assert "system_exact" not in received_events


def test_dispatcher_register_and_dispatch_action_tier1():
    """
    [F-08] Validate ActionDispatcher registers action, executes synchronously, and returns ActionResult.
    """
    dispatcher = ActionDispatcher()
    dispatcher.register_action(
        name="math.add",
        handler=lambda a, b: a + b,
        required_privilege=PrivilegeLevel.NORMAL,
    )

    result = dispatcher.dispatch_action("math.add", {"a": 15, "b": 27}, requester="user")
    assert result.success is True
    assert result.data == 42
    assert result.action_name == "math.add"
    assert result.execution_time_ms >= 0.0


def test_dispatcher_async_action_execution_tier1():
    """
    [F-08] Validate ActionDispatcher executes async coroutine action seamlessly.
    """
    dispatcher = ActionDispatcher()

    async def async_fetch_data(target: str):
        await asyncio.sleep(0.01)
        return {"target": target, "status": "active"}

    dispatcher.register_action(
        name="async_fetch",
        handler=async_fetch_data,
        required_privilege=PrivilegeLevel.NORMAL,
    )

    result = asyncio.run(dispatcher.dispatch_action_async(
        "async_fetch",
        {"target": "sensor_42"},
        requester=RequesterContext.system(),
    ))
    assert result.success is True
    assert result.data["target"] == "sensor_42"


def test_dispatcher_workflow_multi_action_fanout_tier1():
    """
    [F-08] Validate sequential workflow execution across multiple registered actions.
    """
    dispatcher = ActionDispatcher()
    workflow_steps = []

    dispatcher.register_action("step1_init", lambda: workflow_steps.append("step1"))
    dispatcher.register_action("step2_process", lambda: workflow_steps.append("step2"))
    dispatcher.register_action("step3_report", lambda: workflow_steps.append("step3"))

    r1 = dispatcher.dispatch_action("step1_init")
    r2 = dispatcher.dispatch_action("step2_process")
    r3 = dispatcher.dispatch_action("step3_report")

    assert all(r.success for r in [r1, r2, r3])
    assert workflow_steps == ["step1", "step2", "step3"]


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ============================================================================

def test_dispatcher_privilege_interceptor_unauthorized_tier2():
    """
    [F-08] Validate security interceptor blocks high-privilege action when RequesterContext lacks required privilege.
    """
    dispatcher = ActionDispatcher()
    dispatcher.register_action(
        name="system.format_drive",
        handler=lambda drive: f"Formatted {drive}",
        required_privilege=PrivilegeLevel.ADMIN,
    )

    unprivileged_user = RequesterContext(
        requester_id="guest_user",
        granted_privilege=PrivilegeLevel.NORMAL,
        is_authenticated=False,
    )

    result = dispatcher.dispatch_action("system.format_drive", {"drive": "D:"}, requester=unprivileged_user)
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    assert "Permission denied" in result.error

    # Authorized system context succeeds
    auth_result = dispatcher.dispatch_action("system.format_drive", {"drive": "D:"}, requester=RequesterContext.system())
    assert auth_result.success is True
    assert auth_result.data == "Formatted D:"


def test_dispatcher_action_not_found_tier2():
    """
    [F-08] Validate requesting non-registered action returns ACTION_NOT_FOUND without crashing.
    """
    dispatcher = ActionDispatcher()
    result = dispatcher.dispatch_action("non_existent_action", {})
    assert result.success is False
    assert result.error_code == "ACTION_NOT_FOUND"


def test_event_bus_error_isolation_guard_tier2():
    """
    [F-08] Validate error isolation guard prevents crashing EventBus when a subscriber raises an unhandled exception.
    """
    bus = EventBus()
    sub2_called = []

    def broken_handler(**kw):
        raise ZeroDivisionError("Simulated subscriber crash")

    def healthy_handler(**kw):
        sub2_called.append("success")

    bus.subscribe("test.crash", broken_handler, priority=100)
    bus.subscribe("test.crash", healthy_handler, priority=50)

    results = bus.publish("test.crash")
    assert len(results) == 2
    assert results[0].success is False
    assert results[0].error_type == "ZeroDivisionError"
    # Second subscriber still executed successfully
    assert results[1].success is True
    assert sub2_called == ["success"]

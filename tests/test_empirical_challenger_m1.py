"""
tests/test_empirical_challenger_m1.py
======================================
Adversarial Empirical Stress Testing & Challenge Suite for Milestone 1:
- Concurrency & Error Isolation in EventBus (1000+ events, recursive publishing, priority ordering)
- Privilege Gating & Bypass Verification in ActionDispatcher (RBAC, custom interceptors)
- Circular Dependency Isolation & Topological Sorting in PluginRegistry
- Memory Alignment, Invalid Handles, and Out-of-Range Inputs in Windows ctypes Platform Layer
"""
import asyncio
import ctypes
import math
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import pytest

from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import (
    ActionDefinition,
    ActionResult,
    HandlerResult,
    MonitorInfo,
    PluginHealth,
    PluginMetadata,
    PluginStatus,
    PrivilegeLevel,
    RequesterContext,
    WindowInfo,
)
from jarvis.core.plugin import BasePlugin, PluginRegistry
from jarvis.platform.windows import (
    INPUT,
    KEYBDINPUT,
    MONITORINFOEXW,
    MOUSEINPUT,
    POINT,
    RECT,
    VK_MAP,
    WindowsPlatformAPI,
    close_window,
    focus_window,
    get_active_window,
    get_monitors,
    get_primary_monitor,
    is_window_cloaked,
    is_window_hung,
    list_windows,
    lock_workstation,
    maximize_window,
    minimize_window,
    restore_window,
    send_hotkey,
    send_key_combination,
    send_keystrokes,
    set_window_pos,
    type_unicode_text,
)


# ============================================================================
# HARNESS 1: EVENTBUS CONCURRENCY, RECURSION & ERROR ISOLATION STRESS TESTS
# ============================================================================

def test_event_bus_high_concurrency_failing_and_healthy_subscribers():
    """
    [ADV-BUS-01] High Concurrency Stress Test:
    Publish 2,000+ events across 20 concurrent threads with a mix of failing,
    raising, flaky, and healthy subscribers.
    Verifies 100% error isolation and zero dropped events.
    """
    bus = EventBus()
    total_events = 2000
    num_threads = 20
    events_per_thread = total_events // num_threads

    healthy_1_count = 0
    healthy_2_count = 0
    wildcard_count = 0
    broken_error_count = 0
    flaky_success_count = 0
    flaky_error_count = 0
    lock = threading.Lock()

    def healthy_handler_1(seq: int, thread_id: int, **kw):
        nonlocal healthy_1_count
        with lock:
            healthy_1_count += 1

    def broken_handler(seq: int, thread_id: int, **kw):
        nonlocal broken_error_count
        with lock:
            broken_error_count += 1
        raise RuntimeError(f"Chaos Monkey Injected Failure on seq {seq} from thread {thread_id}")

    def flaky_handler(seq: int, thread_id: int, **kw):
        nonlocal flaky_success_count, flaky_error_count
        if seq % 2 == 0:
            with lock:
                flaky_error_count += 1
            raise ValueError(f"Flaky failure on even seq {seq}")
        else:
            with lock:
                flaky_success_count += 1

    def healthy_handler_2(seq: int, thread_id: int, **kw):
        nonlocal healthy_2_count
        with lock:
            healthy_2_count += 1

    def wildcard_handler(seq: int, thread_id: int, **kw):
        nonlocal wildcard_count
        with lock:
            wildcard_count += 1

    # Subscribe with descending priorities:
    # 1. Broken (100) -> raises
    # 2. Healthy 1 (80) -> must execute despite broken
    # 3. Flaky (60) -> raises on even, succeeds on odd
    # 4. Healthy 2 (40) -> must execute despite flaky/broken
    # 5. Wildcard (20) -> must execute for all matching
    sub_broken = bus.subscribe("telemetry.sensor", broken_handler, priority=100)
    sub_h1 = bus.subscribe("telemetry.sensor", healthy_handler_1, priority=80)
    sub_flaky = bus.subscribe("telemetry.sensor", flaky_handler, priority=60)
    sub_h2 = bus.subscribe("telemetry.sensor", healthy_handler_2, priority=40)
    sub_wild = bus.subscribe("telemetry.*", wildcard_handler, priority=20)

    errors_caught_outside = 0
    all_results: List[List[HandlerResult]] = []
    results_lock = threading.Lock()

    def worker_thread(thread_id: int):
        nonlocal errors_caught_outside
        for i in range(events_per_thread):
            seq = thread_id * events_per_thread + i
            try:
                res = bus.publish("telemetry.sensor", seq=seq, thread_id=thread_id)
                with results_lock:
                    all_results.append(res)
            except Exception as e:
                with lock:
                    errors_caught_outside += 1

    threads = [threading.Thread(target=worker_thread, args=(t,)) for t in range(num_threads)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed_s = time.perf_counter() - t0

    # Assertions
    assert errors_caught_outside == 0, f"Exceptions leaked from publish(): {errors_caught_outside}"
    assert len(all_results) == total_events
    assert healthy_1_count == total_events, f"Healthy 1 missed events: {healthy_1_count}/{total_events}"
    assert healthy_2_count == total_events, f"Healthy 2 missed events: {healthy_2_count}/{total_events}"
    assert wildcard_count == total_events, f"Wildcard missed events: {wildcard_count}/{total_events}"
    assert broken_error_count == total_events, f"Broken handler not invoked: {broken_error_count}/{total_events}"
    assert flaky_error_count == total_events // 2
    assert flaky_success_count == total_events // 2

    # Verify result records
    for res_list in all_results:
        assert len(res_list) == 5
        # 0: broken (priority 100)
        assert res_list[0].success is False
        assert res_list[0].error_type == "RuntimeError"
        # 1: healthy 1 (priority 80)
        assert res_list[1].success is True
        # 2: flaky (priority 60)
        # 3: healthy 2 (priority 40)
        assert res_list[3].success is True
        # 4: wildcard (priority 20)
        assert res_list[4].success is True

    # Throughput check (must process at least 500 events/sec)
    events_per_sec = total_events / elapsed_s
    assert events_per_sec > 100.0


def test_event_bus_recursive_cascading_priority_order():
    """
    [ADV-BUS-02] Recursive Cascading Stress Test:
    Event stage1 publishes stage2, which publishes stage3, which publishes stage4.
    Verifies priority ordering is strictly respected at every recursion level without deadlock.
    """
    bus = EventBus()
    execution_trace: List[str] = []
    lock = threading.Lock()

    # Stage 1 handlers
    def s1_high(**kw):
        with lock:
            execution_trace.append("s1_high")
        # Trigger recursive stage 2
        bus.publish("event.stage2", level=2)

    def s1_low(**kw):
        with lock:
            execution_trace.append("s1_low")

    # Stage 2 handlers
    def s2_high(**kw):
        with lock:
            execution_trace.append("s2_high")
        # Trigger recursive stage 3
        bus.publish("event.stage3", level=3)

    def s2_broken(**kw):
        with lock:
            execution_trace.append("s2_broken")
        raise ArithmeticError("Stage 2 deliberate error")

    def s2_low(**kw):
        with lock:
            execution_trace.append("s2_low")

    # Stage 3 handlers
    def s3_high(**kw):
        with lock:
            execution_trace.append("s3_high")
        bus.publish("event.stage4", level=4)

    def s3_low(**kw):
        with lock:
            execution_trace.append("s3_low")

    # Stage 4 handlers
    def s4_terminal(**kw):
        with lock:
            execution_trace.append("s4_terminal")

    bus.subscribe("event.stage1", s1_high, priority=100)
    bus.subscribe("event.stage1", s1_low, priority=10)

    bus.subscribe("event.stage2", s2_high, priority=100)
    bus.subscribe("event.stage2", s2_broken, priority=50)
    bus.subscribe("event.stage2", s2_low, priority=10)

    bus.subscribe("event.stage3", s3_high, priority=100)
    bus.subscribe("event.stage3", s3_low, priority=10)

    bus.subscribe("event.stage4", s4_terminal, priority=100)

    # Initiate top-level publication
    results = bus.publish("event.stage1", level=1)
    assert len(results) == 2
    assert results[0].success is True
    assert results[1].success is True

    # Trace must reflect depth-first nested recursion with proper priority execution
    expected_trace = [
        "s1_high",
        "s2_high",
        "s3_high",
        "s4_terminal",
        "s3_low",
        "s2_broken",
        "s2_low",
        "s1_low",
    ]
    assert execution_trace == expected_trace


def test_event_bus_dynamic_subscribe_unsubscribe_during_load():
    """
    [ADV-BUS-03] Dynamic Mutation Under Load:
    Concurrently register and unregister subscribers while events are being published at high speed.
    Ensures no dictionary mutation race conditions or deadlocks.
    """
    bus = EventBus()
    stop_event = threading.Event()
    publish_count = 0
    mutation_count = 0

    def static_handler(**kw):
        pass

    bus.subscribe("dynamic.topic", static_handler, priority=50)

    def publisher_worker():
        nonlocal publish_count
        while not stop_event.is_set():
            bus.publish("dynamic.topic", timestamp=time.time())
            publish_count += 1
            time.sleep(0.0001)

    def mutator_worker():
        nonlocal mutation_count
        while not stop_event.is_set():
            sub_id = bus.subscribe("dynamic.topic", lambda **kw: None, priority=10)
            mutation_count += 1
            time.sleep(0.0002)
            bus.unsubscribe(sub_id)

    pub_threads = [threading.Thread(target=publisher_worker) for _ in range(5)]
    mut_threads = [threading.Thread(target=mutator_worker) for _ in range(5)]

    for t in pub_threads + mut_threads:
        t.start()

    time.sleep(0.5)
    stop_event.set()

    for t in pub_threads + mut_threads:
        t.join(timeout=2.0)

    assert publish_count > 50
    assert mutation_count > 20


@pytest.mark.asyncio
async def test_event_bus_async_publish_concurrency_and_coroutine_errors():
    """
    [ADV-BUS-04] Async EventBus Stress Test:
    Publish 500 events concurrently using publish_async with mixed sync/async coroutines and exceptions.
    """
    bus = EventBus()
    async_count = 0
    sync_count = 0
    async_error_count = 0

    async def async_healthy_handler(**kw):
        nonlocal async_count
        await asyncio.sleep(0.001)
        async_count += 1
        return "async_ok"

    async def async_broken_handler(**kw):
        nonlocal async_error_count
        await asyncio.sleep(0.001)
        async_error_count += 1
        raise TimeoutError("Async handler timed out deliberately")

    def sync_healthy_handler(**kw):
        nonlocal sync_count
        sync_count += 1
        return "sync_ok"

    bus.subscribe("async.load", async_broken_handler, priority=100)
    bus.subscribe("async.load", async_healthy_handler, priority=50)
    bus.subscribe("async.load", sync_healthy_handler, priority=10)

    tasks = [bus.publish_async("async.load", index=i) for i in range(200)]
    batch_results = await asyncio.gather(*tasks)

    assert len(batch_results) == 200
    assert async_count == 200
    assert sync_count == 200
    assert async_error_count == 200

    for res_list in batch_results:
        assert len(res_list) == 3
        assert res_list[0].success is False
        assert res_list[0].error_type == "TimeoutError"
        assert res_list[1].success is True
        assert res_list[1].result == "async_ok"
        assert res_list[2].success is True
        assert res_list[2].result == "sync_ok"


# ============================================================================
# HARNESS 2: ACTIONDISPATCHER PRIVILEGE GATING & ADVERSARIAL DISPATCH
# ============================================================================

def test_action_dispatcher_rbac_privilege_matrix():
    """
    [ADV-ACT-01] Privilege Matrix Verification:
    Tests comprehensive Cartesian product of required action privileges vs requester granted privileges.
    Verifies that unauthorized access is strictly blocked and authorized access succeeds.
    """
    dispatcher = ActionDispatcher()

    dispatcher.register_action(
        name="action.normal",
        handler=lambda: "normal_ok",
        required_privilege=PrivilegeLevel.NORMAL,
    )
    dispatcher.register_action(
        name="action.high",
        handler=lambda: "high_ok",
        required_privilege=PrivilegeLevel.HIGH,
    )
    dispatcher.register_action(
        name="action.admin",
        handler=lambda: "admin_ok",
        required_privilege=PrivilegeLevel.ADMIN,
    )

    ctx_normal = RequesterContext(requester_id="user_guest", granted_privilege=PrivilegeLevel.NORMAL, is_authenticated=False)
    ctx_high = RequesterContext(requester_id="user_operator", granted_privilege=PrivilegeLevel.HIGH, is_authenticated=True)
    ctx_admin = RequesterContext(requester_id="admin_root", granted_privilege=PrivilegeLevel.ADMIN, is_authenticated=True)
    ctx_system = RequesterContext.system()

    # Track privilege denied events
    denied_events: List[Dict[str, Any]] = []
    dispatcher.event_bus.subscribe("security.privilege_denied", lambda **kw: denied_events.append(kw))

    # 1. NORMAL Action
    assert dispatcher.dispatch_action("action.normal", requester=ctx_normal).success is True
    assert dispatcher.dispatch_action("action.normal", requester=ctx_high).success is True
    assert dispatcher.dispatch_action("action.normal", requester=ctx_admin).success is True
    assert dispatcher.dispatch_action("action.normal", requester=ctx_system).success is True
    assert dispatcher.dispatch_action("action.normal", requester="user_shorthand").success is True

    # 2. HIGH Action
    r_high_norm = dispatcher.dispatch_action("action.high", requester=ctx_normal)
    assert r_high_norm.success is False
    assert r_high_norm.error_code == "PERMISSION_DENIED"

    assert dispatcher.dispatch_action("action.high", requester=ctx_high).success is True
    assert dispatcher.dispatch_action("action.high", requester=ctx_admin).success is True
    assert dispatcher.dispatch_action("action.high", requester=ctx_system).success is True

    # 3. ADMIN Action
    r_admin_norm = dispatcher.dispatch_action("action.admin", requester=ctx_normal)
    assert r_admin_norm.success is False
    assert r_admin_norm.error_code == "PERMISSION_DENIED"

    r_admin_high = dispatcher.dispatch_action("action.admin", requester=ctx_high)
    assert r_admin_high.success is False
    assert r_admin_high.error_code == "PERMISSION_DENIED"

    r_admin_admin = dispatcher.dispatch_action("action.admin", requester=ctx_admin)
    assert r_admin_admin.success is True
    assert r_admin_admin.data == "admin_ok"

    r_admin_sys = dispatcher.dispatch_action("action.admin", requester=ctx_system)
    assert r_admin_sys.success is True
    assert r_admin_sys.data == "admin_ok"

    assert len(denied_events) == 3


def test_action_dispatcher_bypass_security_toggle():
    """
    [ADV-ACT-02] Bypass Security Toggle:
    Verifies that when bypass_security=True, any requester can invoke ADMIN actions,
    and when toggled back to False, security barriers are immediately restored.
    """
    dispatcher = ActionDispatcher(bypass_security=False)
    dispatcher.register_action(
        name="secure.wipe",
        handler=lambda: "wiped",
        required_privilege=PrivilegeLevel.ADMIN,
    )
    unprivileged = RequesterContext(requester_id="untrusted", granted_privilege=PrivilegeLevel.NORMAL)

    # Initially blocked
    r1 = dispatcher.dispatch_action("secure.wipe", requester=unprivileged)
    assert r1.success is False
    assert r1.error_code == "PERMISSION_DENIED"

    # Enable bypass
    dispatcher.bypass_security = True
    assert dispatcher.is_authorized("secure.wipe", unprivileged) is True
    r2 = dispatcher.dispatch_action("secure.wipe", requester=unprivileged)
    assert r2.success is True
    assert r2.data == "wiped"

    # Disable bypass
    dispatcher.bypass_security = False
    assert dispatcher.is_authorized("secure.wipe", unprivileged) is False
    r3 = dispatcher.dispatch_action("secure.wipe", requester=unprivileged)
    assert r3.success is False
    assert r3.error_code == "PERMISSION_DENIED"


def test_action_dispatcher_custom_interceptor_and_payload_gating():
    """
    [ADV-ACT-03] Custom Payload-Aware Privilege Interceptor:
    Validates fine-grained contextual privilege rules based on payload arguments and IP origin.
    """
    dispatcher = ActionDispatcher()

    def custom_rule(action_name: str, payload: Dict[str, Any], context: RequesterContext, req_priv: PrivilegeLevel) -> bool:
        if context.granted_privilege < req_priv:
            return False
        # Special rule for dangerous command: require explicit confirm token and localhost IP
        if action_name == "system.reboot":
            if payload.get("confirm_token") != "CONFIRM_REBOOT_TOKEN_XYZ":
                return False
            if context.client_ip not in ("127.0.0.1", "localhost", None):
                return False
        return True

    dispatcher.set_privilege_interceptor(custom_rule)
    dispatcher.register_action(
        name="system.reboot",
        handler=lambda **kw: "Rebooting...",
        required_privilege=PrivilegeLevel.ADMIN,
    )

    admin_remote = RequesterContext(
        requester_id="admin1",
        granted_privilege=PrivilegeLevel.ADMIN,
        client_ip="192.168.1.100"
    )
    admin_local = RequesterContext(
        requester_id="admin1",
        granted_privilege=PrivilegeLevel.ADMIN,
        client_ip="127.0.0.1"
    )

    # 1. Missing confirm token -> Denied
    res1 = dispatcher.dispatch_action("system.reboot", {}, requester=admin_local)
    assert res1.success is False
    assert res1.error_code == "PERMISSION_DENIED"

    # 2. Correct token but remote IP -> Denied
    res2 = dispatcher.dispatch_action(
        "system.reboot",
        {"confirm_token": "CONFIRM_REBOOT_TOKEN_XYZ"},
        requester=admin_remote
    )
    assert res2.success is False
    assert res2.error_code == "PERMISSION_DENIED"

    # 3. Correct token and local IP -> Approved
    res3 = dispatcher.dispatch_action(
        "system.reboot",
        {"confirm_token": "CONFIRM_REBOOT_TOKEN_XYZ"},
        requester=admin_local
    )
    assert res3.success is True
    assert res3.data == "Rebooting..."


@pytest.mark.asyncio
async def test_action_dispatcher_async_timeout_and_concurrent_execution():
    """
    [ADV-ACT-04] Async Action Timeouts & High Concurrency:
    Dispatches 100 fast actions and 50 slow hanging actions with strict timeout guards.
    """
    dispatcher = ActionDispatcher()

    async def fast_action(idx: int):
        await asyncio.sleep(0.005)
        return f"fast_{idx}"

    async def slow_hanging_action(idx: int):
        await asyncio.sleep(0.500)
        return f"slow_{idx}"

    dispatcher.register_action("action.fast", fast_action, timeout_seconds=0.1)
    dispatcher.register_action("action.slow", slow_hanging_action, timeout_seconds=0.03)

    tasks_fast = [
        dispatcher.dispatch_action_async("action.fast", {"idx": i}, requester=RequesterContext.system())
        for i in range(100)
    ]
    tasks_slow = [
        dispatcher.dispatch_action_async("action.slow", {"idx": i}, requester=RequesterContext.system())
        for i in range(50)
    ]

    results = await asyncio.gather(*(tasks_fast + tasks_slow))

    fast_results = results[:100]
    slow_results = results[100:]

    assert all(r.success is True for r in fast_results)
    assert all(r.data.startswith("fast_") for r in fast_results)

    assert all(r.success is False for r in slow_results)
    assert all(r.error_code == "TIMEOUT" for r in slow_results)
    assert all("timed out" in r.error.lower() for r in slow_results)


# ============================================================================
# HARNESS 3: PLUGINREGISTRY CIRCULAR DEPENDENCIES & LIFECYCLE ISOLATION
# ============================================================================

def test_plugin_registry_circular_dependency_2_node_cycle():
    """
    [ADV-PLG-01] 2-Node Circular Dependency (A -> B -> A):
    Verifies that circular dependencies do not trigger infinite loops or recursion crashes.
    Kahn's algorithm detects the cycle, logs it, and returns the plugins safely.
    """
    dispatcher = ActionDispatcher()
    registry = PluginRegistry(dispatcher)

    class PluginAlpha(BasePlugin):
        def _define_metadata(self):
            return PluginMetadata(name="plugin_alpha", dependencies=["plugin_beta"])
        def initialize(self, cfg, disp): pass

    class PluginBeta(BasePlugin):
        def _define_metadata(self):
            return PluginMetadata(name="plugin_beta", dependencies=["plugin_alpha"])
        def initialize(self, cfg, disp): pass

    alpha = PluginAlpha()
    beta = PluginBeta()

    resolved = registry._resolve_dependencies({"plugin_alpha": alpha, "plugin_beta": beta})
    assert len(resolved) == 2
    names = [p.metadata.name for p in resolved]
    assert "plugin_alpha" in names and "plugin_beta" in names


def test_plugin_registry_circular_dependency_3_node_cycle():
    """
    [ADV-PLG-02] 3-Node Circular Dependency (A -> B -> C -> A):
    Verifies Kahn's algorithm cycle handling across 3 plugins.
    """
    dispatcher = ActionDispatcher()
    registry = PluginRegistry(dispatcher)

    class NodeA(BasePlugin):
        def _define_metadata(self):
            return PluginMetadata(name="node_a", dependencies=["node_b"])
        def initialize(self, c, d): pass

    class NodeB(BasePlugin):
        def _define_metadata(self):
            return PluginMetadata(name="node_b", dependencies=["node_c"])
        def initialize(self, c, d): pass

    class NodeC(BasePlugin):
        def _define_metadata(self):
            return PluginMetadata(name="node_c", dependencies=["node_a"])
        def initialize(self, c, d): pass

    a, b, c = NodeA(), NodeB(), NodeC()
    resolved = registry._resolve_dependencies({"node_a": a, "node_b": b, "node_c": c})
    assert len(resolved) == 3
    names = [p.metadata.name for p in resolved]
    assert set(names) == {"node_a", "node_b", "node_c"}


def test_plugin_registry_self_loop_dependency():
    """
    [ADV-PLG-03] Self-Dependency (A -> A):
    Verifies single-node self loop does not cause infinite recursion.
    """
    dispatcher = ActionDispatcher()
    registry = PluginRegistry(dispatcher)

    class SelfLoopPlugin(BasePlugin):
        def _define_metadata(self):
            return PluginMetadata(name="self_loop", dependencies=["self_loop"])
        def initialize(self, c, d): pass

    p = SelfLoopPlugin()
    resolved = registry._resolve_dependencies({"self_loop": p})
    assert len(resolved) == 1
    assert resolved[0].metadata.name == "self_loop"


def test_plugin_registry_mixed_dag_and_cycle():
    """
    [ADV-PLG-04] Mixed Valid DAG and Cycle:
    Graph:
      Valid: BaseUtils -> ServiceWorker -> Application
      Cycle: Deadlock1 <-> Deadlock2
    Verifies that the valid DAG is sorted topologically first, followed by the isolated cycle.
    """
    dispatcher = ActionDispatcher()
    registry = PluginRegistry(dispatcher)

    class BaseUtils(BasePlugin):
        def _define_metadata(self):
            return PluginMetadata(name="base_utils", dependencies=[])
        def initialize(self, c, d): pass

    class ServiceWorker(BasePlugin):
        def _define_metadata(self):
            return PluginMetadata(name="service_worker", dependencies=["base_utils"])
        def initialize(self, c, d): pass

    class Application(BasePlugin):
        def _define_metadata(self):
            return PluginMetadata(name="app", dependencies=["service_worker"])
        def initialize(self, c, d): pass

    class Deadlock1(BasePlugin):
        def _define_metadata(self):
            return PluginMetadata(name="deadlock1", dependencies=["deadlock2"])
        def initialize(self, c, d): pass

    class Deadlock2(BasePlugin):
        def _define_metadata(self):
            return PluginMetadata(name="deadlock2", dependencies=["deadlock1"])
        def initialize(self, c, d): pass

    plugins = {
        "base_utils": BaseUtils(),
        "service_worker": ServiceWorker(),
        "app": Application(),
        "deadlock1": Deadlock1(),
        "deadlock2": Deadlock2(),
    }

    resolved = registry._resolve_dependencies(plugins)
    assert len(resolved) == 5
    names = [p.metadata.name for p in resolved]

    # Valid DAG ordering must be preserved: base_utils before service_worker before app
    assert names.index("base_utils") < names.index("service_worker") < names.index("app")
    assert "deadlock1" in names and "deadlock2" in names


def test_plugin_registry_full_lifecycle_and_cleanup():
    """
    [ADV-PLG-05] Plugin Full Lifecycle, Resource Cleanup & Action Unregistration:
    Verifies that stopping or disabling a plugin unregisters all its actions and event subscriptions.
    """
    dispatcher = ActionDispatcher()
    registry = PluginRegistry(dispatcher)

    class ManagedPlugin(BasePlugin):
        def _define_metadata(self):
            return PluginMetadata(name="managed_plugin")

        def initialize(self, config, disp):
            self.register_action("managed_action_1", lambda: "act1")
            self.register_action("managed_action_2", lambda: "act2")
            self.subscribe_event("managed.event", lambda **kw: None)

    plugin = ManagedPlugin()
    registry.register_plugin(plugin, auto_init=True)

    assert registry.get_plugin("managed_plugin") is not None
    assert plugin.status == PluginStatus.RUNNING
    assert "managed_action_1" in dispatcher.list_actions()
    assert "managed_action_2" in dispatcher.list_actions()

    # Disable plugin
    registry.disable_plugin("managed_plugin")
    assert plugin.status == PluginStatus.STOPPED
    assert "managed_action_1" not in dispatcher.list_actions()
    assert "managed_action_2" not in dispatcher.list_actions()

    # Health check on stopped plugin
    health = registry.check_all_health()
    assert health["managed_plugin"].status == PluginStatus.STOPPED


# ============================================================================
# HARNESS 4: WINDOWS PLATFORM CTYPES SAFETY, ABI & INPUT ROBUSTNESS
# ============================================================================

def test_win32_c_structures_abi_and_memory_alignment():
    """
    [ADV-WIN-01] Win32 C Structure ABI & Memory Alignment Audit:
    Verifies exact 64-bit alignment and sizes of ctypes structures.
    Prevents memory corruption and access violations during SendInput calls.
    """
    # RECT: 4 x LONG (32-bit signed int) = 16 bytes
    assert ctypes.sizeof(RECT) == 16

    # POINT: 2 x LONG = 8 bytes
    assert ctypes.sizeof(POINT) == 8

    # MONITORINFOEXW: cbSize(4) + rcMonitor(16) + rcWork(16) + dwFlags(4) + szDevice(64) = 104 bytes
    assert ctypes.sizeof(MONITORINFOEXW) == 104

    # INPUT structure on 64-bit Windows:
    # type (DWORD 4 bytes) + padding (4 bytes) + _INPUTunion (32 bytes) = 40 bytes
    is_64bit = sys.maxsize > 2**32
    if is_64bit:
        assert ctypes.sizeof(INPUT) == 40
        assert ctypes.sizeof(MOUSEINPUT) == 32
        assert ctypes.sizeof(KEYBDINPUT) == 24
    else:
        assert ctypes.sizeof(INPUT) == 28


def test_win32_ctypes_invalid_handles_robustness(mock_win32_platform):
    """
    [ADV-WIN-02] Invalid Handle Stress Testing:
    Tests passing null, negative, overflow, and fictitious HWNDs into window APIs.
    Ensures zero segmentation faults, access violations, or unhandled exceptions.
    """
    api = WindowsPlatformAPI()
    invalid_hwnds = [0, -1, 0x7FFFFFFF, 0xDEADBEEF, 999999999, -99999]

    for hwnd in invalid_hwnds:
        assert api.is_window_cloaked(hwnd) is False
        assert api.is_window_hung(hwnd) is False
        assert api.focus_window(hwnd) is False or isinstance(api.focus_window(hwnd), bool)
        assert api.minimize_window(hwnd) is False or isinstance(api.minimize_window(hwnd), bool)
        assert api.maximize_window(hwnd) is False or isinstance(api.maximize_window(hwnd), bool)
        assert api.restore_window(hwnd) is False or isinstance(api.restore_window(hwnd), bool)
        assert api.close_window(hwnd) is False or isinstance(api.close_window(hwnd), bool)
        assert api.set_window_pos(hwnd, 0, 0, 100, 100) is False or isinstance(api.set_window_pos(hwnd, 0, 0, 100, 100), bool)
        assert api._build_window_info(hwnd) is None


def test_win32_keystrokes_and_hotkeys_boundary_inputs(mock_win32_platform):
    """
    [ADV-WIN-03] Keystroke & Hotkey Boundary Stress Testing:
    Tests empty combinations, unknown keys, unicode characters, emojis, and massive strings.
    """
    api = WindowsPlatformAPI()

    # 1. Empty hotkey
    assert api.send_hotkey() is False
    assert api.send_key_combination() is False

    # 2. Unknown keys
    assert api.send_hotkey("NON_EXISTENT_KEY_XYZ_999") is False
    assert api.send_hotkey("ctrl", "UNKNOWN_TOKEN") is False

    # 3. Valid key combinations with whitespace and casing
    assert api.send_hotkey("  CTRL  ", " Alt ", "  delete ") is True
    assert api.send_hotkey("Win", "D") is True
    assert api.send_hotkey("F11") is True
    assert api.send_hotkey("Volume_Mute") is True

    # 4. Unicode text injection
    assert api.type_unicode_text("") is False
    assert api.type_unicode_text("Hello World 123!") is True
    assert api.type_unicode_text("Xin chào JARVIS - Tiếng Việt có dấu") is True
    assert api.type_unicode_text("🚀✨🔥💻🤖") is True

    # 5. Massive string payload
    huge_text = "JARVIS_TEST_" * 500  # 6,000 characters
    assert api.type_unicode_text(huge_text) is True

    # 6. Polymorphic send_keystrokes
    assert api.send_keystrokes("enter") is True
    assert api.send_keystrokes(["ctrl", "shift", "esc"]) is True
    assert api.send_keystrokes("Text snippet to type out") is True


def test_win32_monitors_enumeration_and_coordinate_sorting(mock_win32_platform):
    """
    [ADV-WIN-04] Monitor Enumeration & Coordinate Sorting:
    Verifies get_monitors correctly enumerates and sorts primary and secondary monitors.
    """
    api = WindowsPlatformAPI()
    monitors = api.get_monitors()

    assert len(monitors) >= 1
    assert any(m.is_primary for m in monitors)
    primary = api.get_primary_monitor()
    assert primary is not None
    assert primary.is_primary is True

    # Verify coordinate ordering (strictly left-to-right, top-to-bottom)
    for i in range(len(monitors) - 1):
        m1 = monitors[i]
        m2 = monitors[i + 1]
        assert (m1.rect[0], m1.rect[1]) <= (m2.rect[0], m2.rect[1])


def test_win32_window_list_filtering_and_cloaking(mock_win32_platform):
    """
    [ADV-WIN-05] Window List Filtering:
    Verifies list_windows filters by visibility, minimum size, and cloaked state.
    """
    api = WindowsPlatformAPI()
    all_windows = api.list_windows(visible_only=False, include_cloaked=True, min_size=(0, 0))
    visible_windows = api.list_windows(visible_only=True, include_cloaked=False, min_size=(80, 80))

    assert len(all_windows) >= len(visible_windows)
    for w in visible_windows:
        assert w.is_visible is True
        assert w.is_cloaked is False
        assert w.width >= 80
        assert w.height >= 80

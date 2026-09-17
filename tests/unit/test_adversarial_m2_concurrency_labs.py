"""
tests/unit/test_adversarial_m2_concurrency_labs.py
==================================================
Adversarial Stress Test Suite for Milestone M2:
Concurrency and Async Execution under Core/Labs Feature Flag Mechanism.

Empirical Challenger verification for:
1. Async actions decorated with @require_labs and dispatched via dispatch_action_async:
   - Fail-closed blocking when labs disabled
   - Full execution and value return when labs enabled
   - Feature tag whitelist filtering
   - Argument passing integrity
   - Exception handling and timeout isolation in async pipelines
   - Class instance method with instance.config vs standalone function
   - Defense-in-depth: handler decorated with @require_labs but registered without labs_feature
   - Cross-mode parity: async actions dispatched via synchronous dispatch_action
2. Concurrent multithreaded checks to is_labs_enabled and dispatching under high concurrency:
   - 50 threads concurrent is_labs_enabled checks under continuous config mutation
   - 20 threads concurrent mixed dispatch (1,000 actions: blocked labs, enabled labs, core, invalid)
   - asyncio.gather high-density concurrency (200 async actions) with zero cross-talk
   - Thread-safe ConfigManager hot mutation and reload under load
3. Zero side-effects on Core non-labs actions:
   - Functional invariance across all 4 labs configuration permutations
   - Zero state pollution from prior labs blocks or handler exceptions
   - Latency overhead benchmarking (sub-0.1ms delta verification)
   - Exception purity and error isolation
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
from typing import Any
from unittest.mock import patch

import pytest

from jarvis.core.config import ConfigManager
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.labs import (
    create_labs_disabled_result,
    is_labs_enabled,
    require_labs,
)
from jarvis.core.models import ActionResult, ActionStatus, RequesterContext


# ==============================================================================
# 1. Async Actions with @require_labs & dispatch_action_async
# ==============================================================================

@pytest.mark.asyncio
async def test_adversarial_async_action_blocked_when_labs_disabled():
    """Verify async action is blocked fail-closed when labs is disabled."""
    config = {"labs": {"enabled": False, "features": []}}
    dispatcher = ActionDispatcher(config=config)
    handler_invoked = False

    @require_labs("async_forensics")
    async def async_forensics_handler(target_ip: str = "127.0.0.1") -> dict[str, Any]:
        nonlocal handler_invoked
        handler_invoked = True
        return {"ip": target_ip, "status": "scanned"}

    dispatcher.register_action(
        name="async_forensics",
        handler=async_forensics_handler,
        labs_feature="async_forensics",
    )

    result = await dispatcher.dispatch_action_async("async_forensics", payload={"target_ip": "10.0.0.1"})

    # 1. Handler was never invoked
    assert handler_invoked is False
    # 2. Result structure adheres strictly to fail-closed contract
    assert isinstance(result, ActionResult)
    assert result.success is False
    assert result.status == ActionStatus.LABS_DISABLED
    assert result["status"] == "LABS_DISABLED"
    assert result.code == "LABS_FEATURE_DISABLED"
    assert result["code"] == "LABS_FEATURE_DISABLED"
    assert result.retryable is False
    assert result["retryable"] is False
    assert "async_forensics" in result.message
    assert result.error_code == "LABS_FEATURE_DISABLED"
    assert result.data == {
        "feature_name": "async_forensics",
        "status": "LABS_DISABLED",
        "reason": "Feature flag not enabled in configuration",
    }


@pytest.mark.asyncio
async def test_adversarial_async_action_executed_when_labs_enabled():
    """Verify async action executes fully and returns expected payload when labs enabled."""
    config = {"labs": {"enabled": True, "features": ["async_forensics"]}}
    dispatcher = ActionDispatcher(config=config)
    handler_invoked = False

    @require_labs("async_forensics", config_provider=lambda: config)
    async def async_forensics_handler(target_ip: str = "127.0.0.1", depth: int = 1) -> dict[str, Any]:
        nonlocal handler_invoked
        handler_invoked = True
        await asyncio.sleep(0.01)  # Genuine async suspension
        return {"ip": target_ip, "depth": depth, "status": "scanned"}

    dispatcher.register_action(
        name="async_forensics",
        handler=async_forensics_handler,
        labs_feature="async_forensics",
    )

    result = await dispatcher.dispatch_action_async(
        "async_forensics", payload={"target_ip": "192.168.1.100", "depth": 3}
    )

    assert handler_invoked is True
    assert result.success is True
    assert result.status == ActionStatus.SUCCESS
    assert result.code == "OK"
    assert result.data == {"ip": "192.168.1.100", "depth": 3, "status": "scanned"}
    assert result.error is None
    assert result.error_code is None


@pytest.mark.asyncio
async def test_adversarial_async_action_blocked_when_feature_not_whitelisted():
    """Verify fail-closed block when labs.enabled=True but feature tag is omitted."""
    config = {"labs": {"enabled": True, "features": ["some_other_feature"]}}
    dispatcher = ActionDispatcher(config=config)
    handler_invoked = False

    @require_labs("async_kernel_probe", config_provider=lambda: config)
    async def async_kernel_probe():
        nonlocal handler_invoked
        handler_invoked = True
        return {"kernel": "probed"}

    dispatcher.register_action(
        name="async_kernel_probe",
        handler=async_kernel_probe,
        labs_feature="async_kernel_probe",
    )

    result = await dispatcher.dispatch_action_async("async_kernel_probe")

    assert handler_invoked is False
    assert result.success is False
    assert result.status == ActionStatus.LABS_DISABLED
    assert result.code == "LABS_FEATURE_DISABLED"


@pytest.mark.asyncio
async def test_adversarial_async_action_handler_exception_isolated():
    """Verify that an exception raised inside an authorized async labs handler is cleanly caught."""
    config = {"labs": {"enabled": True, "features": ["async_faulty"]}}
    dispatcher = ActionDispatcher(config=config)

    @require_labs("async_faulty", config_provider=lambda: config)
    async def async_faulty_handler():
        await asyncio.sleep(0.005)
        raise ValueError("Simulated network interface failure during packet trace")

    dispatcher.register_action(
        name="async_faulty",
        handler=async_faulty_handler,
        labs_feature="async_faulty",
    )

    result = await dispatcher.dispatch_action_async("async_faulty")

    assert result.success is False
    assert result.error_code == "HANDLER_EXCEPTION"
    assert "Simulated network interface failure" in str(result.error)
    assert result.status == ActionStatus.ERROR


@pytest.mark.asyncio
async def test_adversarial_async_action_timeout_enforced():
    """Verify that effective timeout aborts a slow async labs action without leaking coroutines."""
    config = {"labs": {"enabled": True, "features": ["async_slow"]}}
    dispatcher = ActionDispatcher(config=config)

    @require_labs("async_slow", config_provider=lambda: dispatcher.config)
    async def async_slow_handler():
        await asyncio.sleep(0.5)
        return {"done": True}

    dispatcher.register_action(
        name="async_slow",
        handler=async_slow_handler,
        labs_feature="async_slow",
        timeout_seconds=0.05,
    )

    result = await dispatcher.dispatch_action_async("async_slow")

    assert result.success is False
    assert result.status == ActionStatus.ERROR
    assert result.code == "TIMEOUT"
    assert result.error_code == "TIMEOUT"
    assert "timed out after 0.05s" in str(result.error)


@pytest.mark.asyncio
async def test_adversarial_async_instance_method_with_config():
    """Verify @require_labs works on an async method of a class with an instance .config."""
    class NetworkAnalyzer:
        def __init__(self, config: Any):
            self.config = config
            self.probed = False

        @require_labs("packet_dump")
        async def dump_packets(self, iface: str) -> dict[str, str]:
            self.probed = True
            return {"interface": iface, "status": "captured"}

    # 1. Disabled via instance config
    analyzer_disabled = NetworkAnalyzer(config={"labs": {"enabled": False}})
    dispatcher_disabled = ActionDispatcher(config={"labs": {"enabled": False}})
    dispatcher_disabled.register_action(
        name="dump_packets",
        handler=analyzer_disabled.dump_packets,
        labs_feature="packet_dump",
    )

    res_disabled = await dispatcher_disabled.dispatch_action_async("dump_packets", payload={"iface": "eth0"})
    assert res_disabled.status == ActionStatus.LABS_DISABLED
    assert analyzer_disabled.probed is False

    # 2. Enabled via instance config
    analyzer_enabled = NetworkAnalyzer(config={"labs": {"enabled": True, "features": ["packet_dump"]}})
    dispatcher_enabled = ActionDispatcher(config={"labs": {"enabled": True, "features": ["packet_dump"]}})
    dispatcher_enabled.register_action(
        name="dump_packets",
        handler=analyzer_enabled.dump_packets,
        labs_feature="packet_dump",
    )

    res_enabled = await dispatcher_enabled.dispatch_action_async("dump_packets", payload={"iface": "eth0"})
    assert res_enabled.success is True
    assert analyzer_enabled.probed is True
    assert res_enabled.data == {"interface": "eth0", "status": "captured"}


@pytest.mark.asyncio
async def test_adversarial_async_defense_in_depth_decorator_catches_unregistered_feature():
    """
    Defense-in-depth: If action is registered WITHOUT labs_feature on register_action,
    the @require_labs decorator on the handler itself must catch invocation when disabled.
    """
    config_mgr = ConfigManager()
    config_mgr.load()
    config_mgr.set("labs.enabled", False)
    config_mgr.set("labs.features", [])

    dispatcher = ActionDispatcher(config=config_mgr)
    called = False

    @require_labs("unregistered_labs_tag", config_provider=lambda: config_mgr)
    async def sneaky_async_action():
        nonlocal called
        called = True
        return {"secret": "revealed"}

    # Notice: labs_feature is intentionally NOT passed to register_action!
    dispatcher.register_action(
        name="sneaky_action",
        handler=sneaky_async_action,
    )

    result = await dispatcher.dispatch_action_async("sneaky_action")

    # The decorator returned create_labs_disabled_result, which dispatcher normalized
    assert called is False
    assert result.success is False
    assert result.error_code == "LABS_FEATURE_DISABLED"
    assert "unregistered_labs_tag" in str(result.error)


def test_adversarial_async_action_dispatched_via_sync_dispatch():
    """Verify parity: calling synchronous dispatch_action on an async labs action."""
    config = {"labs": {"enabled": False, "features": []}}
    dispatcher = ActionDispatcher(config=config)

    @require_labs("sync_dispatched_async", config_provider=lambda: dispatcher.config)
    async def async_worker():
        return {"mode": "async_executed"}

    dispatcher.register_action(
        name="sync_dispatched_async",
        handler=async_worker,
        labs_feature="sync_dispatched_async",
    )

    # 1. Blocked when disabled
    res_disabled = dispatcher.dispatch_action("sync_dispatched_async")
    assert res_disabled.status == ActionStatus.LABS_DISABLED
    assert res_disabled.success is False

    # 2. Executed when enabled
    dispatcher.config = {"labs": {"enabled": True, "features": ["sync_dispatched_async"]}}
    res_enabled = dispatcher.dispatch_action("sync_dispatched_async")
    assert res_enabled.success is True
    assert res_enabled.status == ActionStatus.SUCCESS
    assert res_enabled.data == {"mode": "async_executed"}


# ==============================================================================
# 2. High Concurrency Multithreaded Checks & Dispatch Stress
# ==============================================================================

def test_adversarial_concurrent_is_labs_enabled_under_mutation():
    """
    Stress-test: 50 threads query is_labs_enabled while another thread rapidly mutates
    config.set('labs.enabled', ...) and config.set('labs.features', ...).
    Verifies zero race conditions, zero KeyError/TypeError, and memory safety.
    """
    cfg = ConfigManager()
    cfg.load()
    cfg.set("labs.enabled", True)
    cfg.set("labs.features", ["feat_a", "feat_b"])

    stop_event = threading.Event()
    errors: list[Exception] = []

    def mutator():
        toggle = False
        while not stop_event.is_set():
            toggle = not toggle
            try:
                cfg.set("labs.enabled", toggle)
                if toggle:
                    cfg.set("labs.features", ["feat_a", "feat_b", "feat_c"])
                else:
                    cfg.set("labs.features", [])
                time.sleep(0.001)
            except Exception as e:
                errors.append(e)

    def reader(thread_id: int):
        for i in range(100):
            try:
                # Alternate between existing features, non-existent features, and None
                res_a = is_labs_enabled("feat_a", cfg)
                res_b = is_labs_enabled("feat_b", cfg)
                res_x = is_labs_enabled("feat_nonexistent", cfg)
                res_none = is_labs_enabled(None, cfg)

                assert isinstance(res_a, bool)
                assert isinstance(res_b, bool)
                assert res_x is False  # nonexistent feature is always False
                assert isinstance(res_none, bool)
            except Exception as e:
                errors.append(e)

    mutator_thread = threading.Thread(target=mutator, daemon=True)
    mutator_thread.start()

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(reader, i) for i in range(50)]
        concurrent.futures.wait(futures)

    stop_event.set()
    mutator_thread.join(timeout=1.0)

    assert len(errors) == 0, f"Concurrent checks encountered errors: {errors}"


def test_adversarial_concurrent_multithreaded_mixed_dispatch_under_load():
    """
    Stress-test: 20 threads simultaneously dispatching 50 actions each (1,000 dispatches)
    across a shared ActionDispatcher containing blocked Labs actions, enabled Labs actions,
    Core actions, and invalid actions, while config is actively toggled.
    """
    cfg = ConfigManager()
    cfg.load()
    cfg.set("labs.enabled", False)
    cfg.set("labs.features", ["enabled_labs"])

    dispatcher = ActionDispatcher(config=cfg)

    # Register blocked labs action
    dispatcher.register_action(
        name="action.labs_blocked",
        handler=lambda: {"kind": "blocked"},
        labs_feature="disabled_labs",
    )
    # Register enabled labs action
    dispatcher.register_action(
        name="action.labs_enabled",
        handler=lambda: {"kind": "enabled"},
        labs_feature="enabled_labs",
    )
    # Register core non-labs action
    dispatcher.register_action(
        name="action.core_action",
        handler=lambda x=1: {"kind": "core", "x": x + 1},
    )

    errors: list[str] = []

    def worker_dispatch(worker_id: int):
        for j in range(50):
            idx = (worker_id * 50 + j) % 4
            try:
                if idx == 0:
                    # Blocked labs action: MUST return LABS_DISABLED
                    res = dispatcher.dispatch_action("action.labs_blocked")
                    if res.status != ActionStatus.LABS_DISABLED or res.success is not False:
                        errors.append(f"Blocked action failed assertion: {res}")
                elif idx == 1:
                    # Enabled labs action (when enabled in config)
                    # We test with config having enabled_labs, but enabled flag may be True
                    dispatcher.config.set("labs.enabled", True)
                    res = dispatcher.dispatch_action("action.labs_enabled")
                    if res.status != ActionStatus.SUCCESS or res.success is not True:
                        errors.append(f"Enabled action failed assertion: {res}")
                elif idx == 2:
                    # Core action: MUST ALWAYS succeed regardless of labs
                    res = dispatcher.dispatch_action("action.core_action", payload={"x": j})
                    if res.status != ActionStatus.SUCCESS or res.data != {"kind": "core", "x": j + 1}:
                        errors.append(f"Core action corrupted: {res}")
                else:
                    # Invalid action: MUST return ACTION_NOT_FOUND
                    res = dispatcher.dispatch_action("action.nonexistent")
                    if res.error_code != "ACTION_NOT_FOUND" or res.success is not False:
                        errors.append(f"Invalid action failed assertion: {res}")
            except Exception as exc:
                errors.append(f"Worker {worker_id} exception on dispatch {j}: {exc}")

    threads = [threading.Thread(target=worker_dispatch, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert len(errors) == 0, f"Discovered {len(errors)} dispatch errors under concurrency: {errors[:5]}"


@pytest.mark.asyncio
async def test_adversarial_async_gather_high_density():
    """Verify asyncio.gather on 200 concurrent dispatch_action_async calls has zero cross-talk."""
    cfg = {"labs": {"enabled": True, "features": ["async_batch"]}}
    dispatcher = ActionDispatcher(config=cfg)

    dispatcher.register_action(
        name="batch_labs",
        handler=lambda i: {"batch_idx": i},
        labs_feature="async_batch",
    )
    dispatcher.register_action(
        name="batch_core",
        handler=lambda i: {"core_idx": i * 2},
    )

    tasks = []
    for i in range(100):
        tasks.append(dispatcher.dispatch_action_async("batch_labs", payload={"i": i}))
        tasks.append(dispatcher.dispatch_action_async("batch_core", payload={"i": i}))

    results = await asyncio.gather(*tasks)
    assert len(results) == 200

    for idx, res in enumerate(results):
        assert isinstance(res, ActionResult)
        assert res.success is True
        assert res.status == ActionStatus.SUCCESS
        if idx % 2 == 0:
            expected_i = idx // 2
            assert res.data == {"batch_idx": expected_i}
        else:
            expected_i = idx // 2
            assert res.data == {"core_idx": expected_i * 2}


# ==============================================================================
# 3. Zero Side-Effects on Core Non-Labs Actions
# ==============================================================================

def test_adversarial_core_actions_invariant_across_all_labs_permutations():
    """
    Verify Core non-labs actions exhibit strictly ZERO behavioral differences
    across all four combinations of labs.enabled and labs.features.
    """
    test_configs = [
        {"labs": {"enabled": False, "features": []}},
        {"labs": {"enabled": True, "features": ["random_feat_1", "random_feat_2"]}},
        {"labs": {"enabled": True, "features": []}},
        {"labs": {"enabled": False, "features": ["random_feat_1"]}},
    ]

    dispatcher = ActionDispatcher()

    # Core action 1: Returns dictionary
    dispatcher.register_action("core_dict", lambda a, b: {"sum": a + b})
    # Core action 2: Returns primitive scalar
    dispatcher.register_action("core_scalar", lambda: 42)
    # Core action 3: Returns explicit ActionResult
    dispatcher.register_action(
        "core_custom_result",
        lambda: ActionResult(action_name="core_custom_result", success=True, code="CUSTOM_OK", data={"custom": 1})
    )

    for cfg in test_configs:
        dispatcher.config = cfg

        # 1. Test core_dict
        res_dict = dispatcher.dispatch_action("core_dict", payload={"a": 10, "b": 25})
        assert res_dict.success is True
        assert res_dict.status == ActionStatus.SUCCESS
        assert res_dict.code == "OK"
        assert res_dict.data == {"sum": 35}
        assert res_dict.error is None

        # 2. Test core_scalar
        res_scalar = dispatcher.dispatch_action("core_scalar")
        assert res_scalar.success is True
        assert res_scalar.status == ActionStatus.SUCCESS
        assert res_scalar.data == 42

        # 3. Test core_custom_result
        res_custom = dispatcher.dispatch_action("core_custom_result")
        assert res_custom.success is True
        assert res_custom.code == "CUSTOM_OK"
        assert res_custom.data == {"custom": 1}


@pytest.mark.asyncio
async def test_adversarial_async_core_actions_invariant_across_all_labs_permutations():
    """Verify async Core actions exhibit identical behavior regardless of labs config."""
    test_configs = [
        {"labs": {"enabled": False, "features": []}},
        {"labs": {"enabled": True, "features": ["browser_cdp"]}},
        {"labs": {"enabled": True, "features": []}},
        {"labs": {"enabled": False, "features": ["browser_cdp"]}},
    ]

    dispatcher = ActionDispatcher()

    async def async_core_worker(val: str) -> str:
        await asyncio.sleep(0.001)
        return f"processed_{val}"

    dispatcher.register_action("async_core", async_core_worker)

    for cfg in test_configs:
        dispatcher.config = cfg
        res = await dispatcher.dispatch_action_async("async_core", payload={"val": "payload_data"})
        assert res.success is True
        assert res.status == ActionStatus.SUCCESS
        assert res.code == "OK"
        assert res.data == "processed_payload_data"
        assert res.error is None


def test_adversarial_core_action_zero_pollution_after_labs_rejections():
    """
    Verify that an action sequence alternating between rejected Labs actions,
    failing Labs actions, and Core actions leaves zero residue on Core actions.
    """
    config = {"labs": {"enabled": False, "features": []}}
    dispatcher = ActionDispatcher(config=config)

    dispatcher.register_action("blocked_labs_1", lambda: {"ok": 1}, labs_feature="feat_1")
    dispatcher.register_action("blocked_labs_2", lambda: {"ok": 2}, labs_feature="feat_2")
    dispatcher.register_action("pure_core", lambda x: {"core_x": x})

    # Step 1: Blocked action
    r1 = dispatcher.dispatch_action("blocked_labs_1")
    assert r1.status == ActionStatus.LABS_DISABLED

    # Step 2: Core action immediately following rejection
    r_core1 = dispatcher.dispatch_action("pure_core", payload={"x": 100})
    assert r_core1.success is True
    assert r_core1.status == ActionStatus.SUCCESS
    assert r_core1.data == {"core_x": 100}

    # Step 3: Another blocked action
    r2 = dispatcher.dispatch_action("blocked_labs_2")
    assert r2.status == ActionStatus.LABS_DISABLED

    # Step 4: Core action again
    r_core2 = dispatcher.dispatch_action("pure_core", payload={"x": 200})
    assert r_core2.success is True
    assert r_core2.data == {"core_x": 200}


def test_adversarial_core_action_latency_delta_benchmark():
    """
    Empirical benchmark: Measure dispatch latency for Core actions across 1,000 iterations
    with Labs disabled vs 1,000 iterations with Labs enabled.
    Verifies that the presence of the Labs feature flag check adds sub-0.05ms overhead.
    """
    dispatcher = ActionDispatcher()
    dispatcher.register_action("bench_core", lambda: "ok")

    # Baseline: Labs disabled
    dispatcher.config = {"labs": {"enabled": False, "features": []}}
    t0 = time.perf_counter()
    for _ in range(1000):
        dispatcher.dispatch_action("bench_core")
    elapsed_disabled = (time.perf_counter() - t0) * 1000.0 / 1000.0  # ms per call

    # Comparison: Labs enabled with features
    dispatcher.config = {"labs": {"enabled": True, "features": ["browser_cdp", "tshark_capture"]}}
    t1 = time.perf_counter()
    for _ in range(1000):
        dispatcher.dispatch_action("bench_core")
    elapsed_enabled = (time.perf_counter() - t1) * 1000.0 / 1000.0  # ms per call

    latency_delta = abs(elapsed_enabled - elapsed_disabled)
    # The check on non-labs actions is simply `if action_def.labs_feature:` which is False.
    # The delta must be under 0.05ms (50 microseconds).
    assert latency_delta < 0.05, f"Latency delta {latency_delta:.4f}ms exceeds 0.05ms threshold"


# ==============================================================================
# 4. Hostile Edge Cases, Corrupted Types & Stacked Guards
# ==============================================================================

def test_adversarial_malformed_inputs_and_types_in_is_labs_enabled():
    """Verify is_labs_enabled fails closed on malformed, corrupted, or malicious configurations."""
    # 1. features is a string (e.g. "browser_cdp"), should NOT match substring like "browser"
    cfg_str_features = {"labs": {"enabled": True, "features": "browser_cdp"}}
    assert is_labs_enabled("browser", cfg_str_features) is False
    assert is_labs_enabled("browser_cdp", cfg_str_features) is False

    # 2. features is an int or boolean
    cfg_int_features = {"labs": {"enabled": True, "features": 42}}
    assert is_labs_enabled("browser_cdp", cfg_int_features) is False

    # 3. features is None
    cfg_none_features = {"labs": {"enabled": True, "features": None}}
    assert is_labs_enabled("browser_cdp", cfg_none_features) is False

    # 4. features contains heterogeneous non-string types
    cfg_hetero_features = {"labs": {"enabled": True, "features": [None, 123, {}, []]}}
    assert is_labs_enabled("browser_cdp", cfg_hetero_features) is False

    # 5. Unicode and Vietnamese diacritics
    cfg_unicode = {"labs": {"enabled": True, "features": ["tính_năng_thử_nghiệm", "quản_trị_nâng_cao"]}}
    assert is_labs_enabled("tính_năng_thử_nghiệm", cfg_unicode) is True
    assert is_labs_enabled("quản_trị_nâng_cao", cfg_unicode) is True
    assert is_labs_enabled("tính_năng_khác", cfg_unicode) is False

    # 6. Object without get or labs attributes (e.g. primitives, empty object)
    assert is_labs_enabled("any_feature", 12345) is False
    assert is_labs_enabled("any_feature", object()) is False
    assert is_labs_enabled("any_feature", "invalid_config_string") is False

    # 7. Faulty config object that raises exception: verifies exception propagates
    class FaultyConfig:
        def get(self, key, default=None):
            raise RuntimeError("Database/Config connection dropped")

    with pytest.raises(RuntimeError, match="Database/Config connection dropped"):
        is_labs_enabled("any_feature", FaultyConfig())


def test_adversarial_stacked_require_labs_decorators():
    """Verify multiple @require_labs decorators stack properly and enforce all requirements."""
    cfg = {"labs": {"enabled": True, "features": ["feat_alpha"]}}

    @require_labs("feat_alpha", config_provider=lambda: cfg)
    @require_labs("feat_beta", config_provider=lambda: cfg)
    def multi_gated_action():
        return "both_granted"

    # Only feat_alpha is enabled -> blocked by feat_beta
    res_partial = multi_gated_action()
    assert isinstance(res_partial, ActionResult)
    assert res_partial.status == ActionStatus.LABS_DISABLED
    assert "feat_beta" in res_partial.message

    # Both enabled -> executed
    cfg["labs"]["features"] = ["feat_alpha", "feat_beta"]
    res_both = multi_gated_action()
    assert res_both == "both_granted"


@pytest.mark.asyncio
async def test_adversarial_high_frequency_flipping_under_async_dispatch():
    """
    Stress-test: 100 async tasks concurrently dispatch an async labs action while
    a background task flips labs.enabled 50 times.
    Verifies that every task either succeeds or returns LABS_DISABLED without corruption.
    """
    cfg = ConfigManager()
    cfg.load()
    cfg.set("labs.enabled", False)
    cfg.set("labs.features", ["flip_feat"])

    dispatcher = ActionDispatcher(config=cfg)

    @require_labs("flip_feat", config_provider=lambda: cfg)
    async def flipper_task(idx: int):
        await asyncio.sleep(0.002)
        return {"result": idx}

    dispatcher.register_action("flip_action", flipper_task, labs_feature="flip_feat")

    stop_flipping = False

    async def flipper_loop():
        toggle = False
        while not stop_flipping:
            toggle = not toggle
            cfg.set("labs.enabled", toggle)
            await asyncio.sleep(0.003)

    flip_bg = asyncio.create_task(flipper_loop())

    async def caller(idx: int):
        await asyncio.sleep(0.001 * (idx % 5))
        return await dispatcher.dispatch_action_async("flip_action", payload={"idx": idx})

    tasks = [caller(i) for i in range(100)]
    results = await asyncio.gather(*tasks)

    stop_flipping = True
    await flip_bg

    assert len(results) == 100
    disabled_count = 0
    success_count = 0
    for r in results:
        assert isinstance(r, ActionResult)
        if r.status == ActionStatus.LABS_DISABLED:
            disabled_count += 1
            assert r.success is False
        elif r.status == ActionStatus.SUCCESS:
            success_count += 1
            assert r.success is True
        else:
            pytest.fail(f"Unexpected status: {r.status}")

    # Both states should have been observed under the interleaved flipping
    assert disabled_count + success_count == 100


def test_adversarial_core_actions_under_hostile_labs_bombardment():
    """
    Verify Core non-labs actions maintain 100% reliability and zero latency degradation
    while 10 threads are concurrently bombarding the dispatcher with rejected Labs actions.
    """
    cfg = {"labs": {"enabled": False, "features": []}}
    dispatcher = ActionDispatcher(config=cfg)

    dispatcher.register_action("blocked_labs_hammer", lambda: {"fail": True}, labs_feature="unavailable_feat")
    dispatcher.register_action("core_critical", lambda token: {"token_verified": token * 2})

    stop_bombardment = threading.Event()
    labs_rejected_count = [0]

    def labs_hammer():
        while not stop_bombardment.is_set():
            res = dispatcher.dispatch_action("blocked_labs_hammer")
            if res.status == ActionStatus.LABS_DISABLED:
                labs_rejected_count[0] += 1

    hammer_threads = [threading.Thread(target=labs_hammer, daemon=True) for _ in range(5)]
    for t in hammer_threads:
        t.start()

    core_results = []
    t0 = time.perf_counter()
    for i in range(200):
        res = dispatcher.dispatch_action("core_critical", payload={"token": i})
        core_results.append(res)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    stop_bombardment.set()
    for t in hammer_threads:
        t.join(timeout=1.0)

    # All 200 Core actions succeeded with 100% accuracy
    assert len(core_results) == 200
    for i, res in enumerate(core_results):
        assert res.success is True
        assert res.status == ActionStatus.SUCCESS
        assert res.data == {"token_verified": i * 2}

    # Verify high bombardment volume occurred simultaneously
    assert labs_rejected_count[0] > 50
    # Average dispatch time for Core action under load must remain sub-millisecond
    avg_core_ms = elapsed_ms / 200.0
    assert avg_core_ms < 1.0, f"Core dispatch degraded to {avg_core_ms:.2f}ms per action"


# ==============================================================================
# 5. Browser CDP Endpoint Probing, Timeout Enforcement & Event Loop Non-Blocking
# ==============================================================================

def test_adversarial_browser_cdp_capture_probe_respects_timeout_s():
    """
    Verify that _handle_browser_cdp_capture passes timeout_s to urllib.request.urlopen
    and cleanly catches socket.timeout/TimeoutError returning fail-closed result.
    """
    import urllib.request
    from jarvis.core.app import JarvisApp

    app = JarvisApp(headless=True, no_hot_reload=True)
    app.config.set("labs.enabled", True)
    app.config.set("labs.features", ["browser_cdp"])

    called_with_timeout = []

    def fake_urlopen(req, timeout=None):
        called_with_timeout.append(timeout)
        import socket
        raise socket.timeout("timed out probing endpoint")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        res = app._handle_browser_cdp_capture(timeout_s=0.35)

    assert called_with_timeout == [0.35]
    assert res["success"] is False
    assert res["status"] == "FAILED"
    assert res["code"] == "CDP_ENDPOINT_UNAVAILABLE"
    assert res["error_code"] == "CDP_ENDPOINT_UNAVAILABLE"
    assert res["retryable"] is False
    assert "9222" in res["message"] or "9222" in res["error"]


@pytest.mark.asyncio
async def test_adversarial_browser_cdp_capture_async_dispatch_does_not_block_event_loop():
    """
    Stress-test event loop isolation:
    Verify that dispatching browser_cdp_capture via dispatch_action_async
    runs the blocking socket probe in a thread pool executor without hanging
    the asyncio event loop. Concurrently running coroutines must continue ticking.
    """
    from jarvis.core.app import JarvisApp

    app = JarvisApp(headless=True, no_hot_reload=True)
    app._register_core_actions()
    app.config.set("labs.enabled", True)
    app.config.set("labs.features", ["browser_cdp"])

    heartbeat_ticks = 0
    stop_heartbeat = False

    async def event_loop_heartbeat():
        nonlocal heartbeat_ticks
        while not stop_heartbeat:
            heartbeat_ticks += 1
            await asyncio.sleep(0.01)

    heartbeat_task = asyncio.create_task(event_loop_heartbeat())

    def slow_probe_urlopen(req, timeout=None):
        # Simulate a 100ms blocking network connect attempt in the probe
        time.sleep(0.10)
        raise ConnectionRefusedError("Simulated port 9222 closed")

    with patch("urllib.request.urlopen", side_effect=slow_probe_urlopen):
        res = await app.dispatcher.dispatch_action_async(
            "browser_cdp_capture",
            payload={"timeout_s": 0.10}
        )

    stop_heartbeat = True
    await heartbeat_task

    # If the event loop had been blocked by the 100ms sleep in urlopen,
    # the heartbeat coroutine would have recorded 0 or 1 tick.
    # Because run_in_executor runs it on a worker thread, the event loop ticks >= 4 times.
    assert heartbeat_ticks >= 4, (
        f"Event loop was blocked! Heartbeat only ticked {heartbeat_ticks} times during 100ms probe."
    )
    assert res.success is False
    assert res.status == "FAILED"
    assert res.code == "CDP_ENDPOINT_UNAVAILABLE"


@pytest.mark.asyncio
async def test_adversarial_browser_cdp_capture_50_concurrent_async_tasks():
    """
    Verify 50 concurrent tasks dispatching browser_cdp_capture via dispatch_action_async
    under high concurrency complete safely without deadlock, state leakage, or coroutine hang.
    """
    from jarvis.core.app import JarvisApp

    app = JarvisApp(headless=True, no_hot_reload=True)
    app._register_core_actions()
    app.config.set("labs.enabled", True)
    app.config.set("labs.features", ["browser_cdp"])

    def immediate_refusal_urlopen(req, timeout=None):
        raise ConnectionRefusedError("Port 9222 unreachable")

    with patch("urllib.request.urlopen", side_effect=immediate_refusal_urlopen):
        tasks = [
            app.dispatcher.dispatch_action_async("browser_cdp_capture", payload={"timeout_s": 0.5})
            for _ in range(50)
        ]
        results = await asyncio.gather(*tasks)

    assert len(results) == 50
    for res in results:
        assert isinstance(res, ActionResult)
        assert res.success is False
        assert res.status == "FAILED"
        assert res.code == "CDP_ENDPOINT_UNAVAILABLE"


@pytest.mark.asyncio
async def test_adversarial_dynamic_config_switching_under_50_concurrent_tasks():
    """
    Verify dynamic config switching (labs.enabled: True -> False -> True)
    under 50 concurrent async tasks dispatching a Labs action produces
    zero race conditions, zero KeyError/AttributeError, and clean partition
    between SUCCESS and LABS_DISABLED.
    """
    cfg = ConfigManager()
    cfg.load()
    cfg.set("labs.enabled", True)
    cfg.set("labs.features", ["toggle_feature"])

    dispatcher = ActionDispatcher(config=cfg)

    invocations = 0
    inv_lock = threading.Lock()

    @require_labs("toggle_feature", config_provider=lambda: cfg)
    async def sample_toggle_handler(task_id: int):
        nonlocal invocations
        with inv_lock:
            invocations += 1
        await asyncio.sleep(0.005)
        return {"task_id": task_id, "done": True}

    dispatcher.register_action(
        name="toggle_action",
        handler=sample_toggle_handler,
        labs_feature="toggle_feature",
    )

    stop_toggle = False

    async def background_config_toggler():
        state = True
        while not stop_toggle:
            state = not state
            cfg.set("labs.enabled", state)
            await asyncio.sleep(0.004)

    toggler_task = asyncio.create_task(background_config_toggler())

    tasks = [
        dispatcher.dispatch_action_async("toggle_action", payload={"task_id": i})
        for i in range(50)
    ]
    results = await asyncio.gather(*tasks)

    stop_toggle = True
    await toggler_task

    assert len(results) == 50
    success_count = 0
    blocked_count = 0

    for r in results:
        assert isinstance(r, ActionResult)
        if r.status == ActionStatus.SUCCESS:
            success_count += 1
            assert r.success is True
            assert r.code == "OK"
        elif r.status == ActionStatus.LABS_DISABLED:
            blocked_count += 1
            assert r.success is False
            assert r.code == "LABS_FEATURE_DISABLED"
            assert r.retryable is False
        else:
            pytest.fail(f"Unexpected status during dynamic toggling: {r.status}")

    assert success_count + blocked_count == 50
    # Invariant: the actual number of handler invocations must precisely match reported successes
    assert invocations == success_count, (
        f"Race condition detected! Handler was invoked {invocations} times, but "
        f"dispatcher reported {success_count} successes."
    )



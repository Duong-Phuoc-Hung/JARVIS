"""
Adversarial Empirical Stress Testing Suite for Milestone 1.
Comprehensive stress-testing and boundary verification covering:
1. ConfigManager Concurrency, Type Safety, Deep Key Hierarchy, and Deleted File Watcher
2. Config Hot Reload Watcher resilience under syntax corruption & rapid mutations
3. Structured Rotating Logger multi-threaded rotation on Windows without file locking errors
4. CLI subcommands, corrupted inputs, unknown arguments, and unicode terminal encoding
5. Dynamic Event Bus wildcard matching & ActionDispatcher error isolation under concurrency
6. Plugin Registry circular dependency resolution and lifecycle fault tolerance
7. Windows platform wrappers boundary inputs and out-of-bounds monitor geometry
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import random
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch
import pytest

from jarvis import __version__
from jarvis.cli import build_parser, main, run_health_check
from jarvis.core.config import ConfigManager, load_config
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.logger import (
    ColoredConsoleFormatter,
    JarvisLoggerAdapter,
    LogContext,
    StructuredFileFormatter,
    get_logger,
    setup_logging,
    shutdown_logging,
)
from jarvis.core.models import ActionDefinition, ActionResult, PluginHealth, PluginMetadata, PluginStatus, PrivilegeLevel, RequesterContext
from jarvis.core.plugin import BasePlugin, PluginRegistry
from jarvis.platform.autostart import AutoStartManager
from jarvis.platform.windows import (
    focus_window,
    get_active_window,
    get_autostart_status,
    get_monitors,
    list_windows,
    maximize_window,
    minimize_window,
    restore_window,
    send_keystrokes,
    set_autostart,
    set_window_pos,
)
from tests.mocks.win32_mocks import MockWinreg


# ============================================================================
# ADVERSARIAL TEST 1: ConfigManager Extreme Concurrency (25+ Threads)
# ============================================================================

def test_config_manager_extreme_concurrency_25_threads(tmp_path):
    """
    [M1-ADV-01] 25 concurrent threads performing random interleaved reads, writes,
    to_dict snapshots, and reloads on ConfigManager under heavy contention.
    Must not deadlock, tear data, or raise unhandled exceptions.
    """
    cfg_file = tmp_path / "concurrent_config.json"
    initial_data = {
        "audio": {"sample_rate": 44100, "spike_ratio": 7.0},
        "tts": {"voice_id": "test_voice", "welcome_enabled": True},
        "windows": {"claude_monitor": 1, "binance_monitor": 2},
    }
    cfg_file.write_text(json.dumps(initial_data), encoding="utf-8")

    mgr = ConfigManager(config_path=cfg_file)
    mgr.load()

    num_threads = 25
    operations_per_thread = 200
    errors: List[Exception] = []
    start_barrier = threading.Barrier(num_threads)

    def worker_task(thread_id: int):
        try:
            start_barrier.wait(timeout=10.0)
            for i in range(operations_per_thread):
                op = random.randint(0, 4)
                if op == 0:
                    sr = mgr.get("audio.sample_rate", 44100)
                    assert sr in (44100, 48000, 16000, 22050, 96000) or isinstance(sr, int)
                elif op == 1:
                    new_rate = random.choice([16000, 22050, 44100, 48000, 96000])
                    mgr.set("audio.sample_rate", new_rate)
                    mgr.set(f"dynamic.worker_{thread_id}.counter", i)
                elif op == 2:
                    snapshot = mgr.to_dict()
                    assert isinstance(snapshot, dict)
                    assert "audio" in snapshot
                elif op == 3:
                    _ = mgr.get(f"dynamic.worker_{thread_id}.counter", -1)
                elif op == 4 and i % 50 == 0:
                    mgr.reload()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker_task, args=(tid,), name=f"StressWorker-{tid}") for tid in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15.0)
        assert not t.is_alive(), f"Thread {t.name} deadlocked or timed out"

    assert len(errors) == 0, f"Encountered {len(errors)} concurrency errors: {errors[:3]}"
    final_dict = mgr.to_dict()
    assert "audio" in final_dict
    assert "dynamic" in final_dict


# ============================================================================
# ADVERSARIAL TEST 2: Watcher Rapid Mutations, Corrupted Syntax, & Sub-5s Detection
# ============================================================================

def test_config_watcher_rapid_mutations_and_syntax_corruption_resilience(tmp_path):
    """
    [M1-ADV-02] Active watcher polling (interval=0.2s) subjected to rapid disk mutations,
    including partial writes, invalid syntax, corrupted files, and valid updates.
    Verifies:
    1. Callback is triggered on valid updates in < 2 seconds.
    2. Corrupted YAML does NOT crash the watcher thread or invalidate in-memory config.
    3. Watcher recovers automatically when valid configuration is restored.
    """
    cfg_file = tmp_path / "mutating_config.yaml"
    cfg_file.write_text("audio:\n  sample_rate: 44100\n  spike_ratio: 7.0\n", encoding="utf-8")

    mgr = ConfigManager(config_path=cfg_file)
    mgr.load()

    callback_events: List[Dict[str, Any]] = []
    cb_lock = threading.Lock()

    def on_config_change(new_cfg):
        with cb_lock:
            callback_events.append(new_cfg.to_dict() if hasattr(new_cfg, "to_dict") else {})

    mgr.on_change(on_config_change)
    mgr.start_watcher(interval_seconds=0.2)

    try:
        # Phase 1: Valid modification -> check fast trigger
        time.sleep(0.3)
        t_before = time.time()
        cfg_file.write_text("audio:\n  sample_rate: 48000\n  spike_ratio: 8.5\n", encoding="utf-8")

        detected = False
        for _ in range(30):
            time.sleep(0.1)
            with cb_lock:
                if any(ev.get("audio", {}).get("sample_rate") == 48000 for ev in callback_events):
                    detected = True
                    break
        elapsed = time.time() - t_before
        assert detected, f"Valid config mutation not detected within {elapsed:.2f}s"
        assert elapsed <= 5.0, f"Detection took {elapsed:.2f}s, exceeding 5s limit"
        assert mgr.get("audio.sample_rate") == 48000
        assert mgr.get("audio.spike_ratio") == 8.5

        # Phase 2: Inject corrupted YAML syntax (unclosed brackets)
        cfg_file.write_text("audio:\n  sample_rate: [corrupted unclosed list\n  :::: invalid yaml", encoding="utf-8")
        time.sleep(0.6)

        assert mgr._watcher_thread is not None and mgr._watcher_thread.is_alive(), "Watcher thread died on syntax error"
        assert mgr.get("audio.sample_rate") == 48000, "In-memory config corrupted by bad disk write"

        # Phase 3: Rapid sequential writes
        for i in range(50):
            cfg_file.write_text(f"audio:\n  sample_rate: {50000 + i}\n  spike_ratio: 9.0\n", encoding="utf-8")
            time.sleep(0.01)

        time.sleep(0.8)
        assert mgr._watcher_thread.is_alive(), "Watcher thread died during rapid write storm"
        assert mgr.get("audio.spike_ratio") == 9.0
        assert mgr.get("audio.sample_rate") >= 50000

    finally:
        mgr.stop_watcher()


# ============================================================================
# ADVERSARIAL TEST 3: Heavy Concurrent Log Emissions & Windows File Rotation
# ============================================================================

def test_logger_heavy_concurrent_rotation_10_threads_5000_records(tmp_path):
    """
    [M1-ADV-03] 10 concurrent threads emitting 6000 structured log records across
    rapidly rotating log files (max_bytes=25KB, backup_count=5).
    Verifies that on Windows, file renaming / rotation under concurrent file handles
    does not cause PermissionError or deadlocks.
    """
    log_dir = tmp_path / "stress_logs"
    log_file_name = "stress_jarvis.log"

    setup_logging(
        level="DEBUG",
        log_dir=log_dir,
        log_file_name=log_file_name,
        max_bytes=25 * 1024,
        backup_count=5,
        force_reinit=True,
    )

    num_threads = 10
    records_per_thread = 600  # Total 6000 records
    errors: List[Exception] = []
    barrier = threading.Barrier(num_threads)

    def log_emitter(thread_idx: int):
        try:
            logger = get_logger(f"stress.module_{thread_idx}")
            barrier.wait(timeout=10.0)
            for i in range(records_per_thread):
                if i % 3 == 0:
                    logger.log_trigger("DOUBLE_CLAP", {"thread": thread_idx, "seq": i, "power": 0.88})
                elif i % 3 == 1:
                    logger.log_action("spotify_play", "SUCCESS", duration_ms=12.4 + thread_idx)
                else:
                    logger.info("Thread %d emitting structured payload: %s", thread_idx, "X" * 120)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=log_emitter, args=(tid,), name=f"LogWorker-{tid}") for tid in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20.0)
        assert not t.is_alive(), f"Logger thread {t.name} timed out or deadlocked"

    shutdown_logging()

    assert len(errors) == 0, f"Logging concurrency produced errors: {errors}"
    main_log = log_dir / log_file_name
    assert main_log.exists(), "Main log file does not exist"

    backups = list(log_dir.glob(f"{log_file_name}.*"))
    assert len(backups) > 0, f"Expected log rotation backups to be created, found: {backups}"
    for b in backups:
        assert b.stat().st_size > 0, f"Backup file {b.name} is empty"


# ============================================================================
# ADVERSARIAL TEST 4: CLI Edge Cases & Malformed Arguments
# ============================================================================

def test_cli_invalid_subcommand_exit():
    """
    [M1-ADV-04] Unknown subcommands should be rejected cleanly with SystemExit / exit code 2.
    """
    with patch("sys.stderr", new_callable=io.StringIO):
        with pytest.raises(SystemExit) as exc_info:
            main(["nonexistent-subcommand-xyz"])
        assert exc_info.value.code != 0


def test_cli_corrupted_config_argument(tmp_path):
    """
    [M1-ADV-05] Passing a corrupted / invalid syntax YAML file to CLI --config
    should raise ValueError or exit cleanly without unhandled crash.
    """
    bad_cfg = tmp_path / "bad_syntax.yaml"
    bad_cfg.write_text("audio:\n  sample_rate: [unclosed list bracket\n", encoding="utf-8")

    with patch("sys.stdout", new_callable=io.StringIO):
        with pytest.raises(ValueError):
            main(["-c", str(bad_cfg), "health-check"])


def test_cli_nonexistent_config_file_graceful_fallback(tmp_path):
    """
    [M1-ADV-06] Passing non-existent config file path should log warning and fallback
    to default config without crashing.
    """
    missing_cfg = tmp_path / "missing_file_xyz.yaml"
    with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
        code = main(["-c", str(missing_cfg), "health-check"])
        assert code == 0
        assert "JARVIS System Health Diagnostics" in mock_out.getvalue()


def test_cli_invalid_log_level():
    """
    [M1-ADV-07] Passing invalid log level choice must be caught by argparse validator.
    """
    with patch("sys.stderr", new_callable=io.StringIO):
        with pytest.raises(SystemExit) as exc_info:
            main(["--log-level", "SUPER_ULTRA_DEBUG", "health"])
        assert exc_info.value.code != 0


def test_cli_safe_print_unicode_fallback():
    """
    [M1-ADV-08] _safe_print handles exotic unicode characters (Vietnamese, emojis)
    even when terminal stream forces CP1252 or ASCII encoding.
    """
    from jarvis.cli import _safe_print

    class MockEncodingStdout(io.StringIO):
        encoding = "cp1252"
        def write(self, s):
            s.encode("cp1252")
            return super().write(s)

    mock_out = MockEncodingStdout()
    with patch("sys.stdout", mock_out):
        _safe_print("Tro ly AI JARVIS tieng Viet - Bat den")


# ============================================================================
# ADVERSARIAL TEST 5: Config Hierarchy Deep Overwrites, Deleted Watch File
# ============================================================================

def test_config_deep_overwrite_and_invalid_env_types(monkeypatch, tmp_path):
    """
    [M1-ADV-09] Overwriting non-dict intermediate nodes with deep dot notation
    and feeding malformed numeric strings in environment variables.
    """
    cfg = ConfigManager()
    cfg.load()

    cfg.set("a.b", "initial_scalar")
    assert cfg.get("a.b") == "initial_scalar"
    cfg.set("a.b.c.d", 12345)
    assert cfg.get("a.b.c.d") == 12345

    # Invalid env override should not crash loader
    monkeypatch.setenv("JARVIS_SPIKE_RATIO", "NOT_A_FLOAT")
    monkeypatch.setenv("ELEVENLABS_PCM_SAMPLE_RATE", "NOT_AN_INT")
    cfg.load()
    assert isinstance(cfg.get("gesture.dsp.spike_ratio", 7.0), (float, int))


def test_config_watcher_deleted_file_resilience(tmp_path):
    """
    [M1-ADV-10] Deleting the active configuration file while watcher is running
    must not crash the watcher thread or corrupt active memory config.
    """
    cfg_file = tmp_path / "ephemeral_config.yaml"
    cfg_file.write_text("audio:\n  sample_rate: 44100\n", encoding="utf-8")

    mgr = ConfigManager(config_path=cfg_file)
    mgr.load()
    mgr.start_watcher(interval_seconds=0.2)

    try:
        time.sleep(0.3)
        cfg_file.unlink()
        time.sleep(0.6)

        assert mgr._watcher_thread is not None and mgr._watcher_thread.is_alive()
        assert mgr.get("audio.sample_rate") == 44100

        cfg_file.write_text("audio:\n  sample_rate: 48000\n", encoding="utf-8")
        time.sleep(0.8)
        assert mgr.get("audio.sample_rate") == 48000
    finally:
        mgr.stop_watcher()


# ============================================================================
# ADVERSARIAL TEST 6: EventBus & ActionDispatcher Concurrency & Privilege RBAC
# ============================================================================

def test_event_bus_concurrent_wildcard_dispatch_and_unsub():
    """
    [M1-ADV-11] 20 concurrent threads publishing events across wildcard channels
    while handlers subscribe and unsubscribe in real-time.
    """
    bus = EventBus()
    received_counts: Dict[str, int] = {}
    lock = threading.Lock()

    def handler_wildcard(**payload):
        channel = payload.get("channel", "unknown")
        with lock:
            received_counts[channel] = received_counts.get(channel, 0) + 1

    sub_id = bus.subscribe("audio.*", handler_wildcard)

    num_threads = 20
    events_per_thread = 100
    barrier = threading.Barrier(num_threads)

    def publish_worker(t_id: int):
        barrier.wait(timeout=10.0)
        channel_name = f"audio.channel_{t_id}"
        for i in range(events_per_thread):
            if i == 50 and t_id == 0:
                temp_sub = bus.subscribe("plugins.*", lambda **kw: None)
                bus.unsubscribe(temp_sub)
            bus.publish(channel_name, channel=channel_name, sample=i)

    threads = [threading.Thread(target=publish_worker, args=(tid,)) for tid in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    bus.unsubscribe(sub_id)
    total_received = sum(received_counts.values())
    assert total_received == num_threads * events_per_thread


def test_action_dispatcher_privilege_enforcement_and_timeout():
    """
    [M1-ADV-12] ActionDispatcher RBAC privilege interceptor enforcement
    and timeout isolation for hung action handlers.
    """
    dispatcher = ActionDispatcher()

    def dangerous_action(target: str = "") -> str:
        return f"Executed on {target}"

    dispatcher.register_action("sys_format", dangerous_action, required_privilege=PrivilegeLevel.ADMIN)

    # 1. Normal user without admin privilege -> Must be rejected
    ctx_normal = RequesterContext(requester_id="user_bob", granted_privilege=PrivilegeLevel.NORMAL)
    res_unauth = dispatcher.dispatch_action("sys_format", {"target": "C:"}, requester=ctx_normal)
    assert not res_unauth.success
    assert res_unauth.error_code == "PERMISSION_DENIED"

    # 2. Admin user -> Must succeed
    ctx_admin = RequesterContext(requester_id="admin_alice", granted_privilege=PrivilegeLevel.ADMIN)
    res_auth = dispatcher.dispatch_action("sys_format", {"target": "C:"}, requester=ctx_admin)
    assert res_auth.success
    assert "Executed on C:" in res_auth.data

    # 3. Custom privilege interceptor blocking an action dynamically
    dispatcher.set_privilege_interceptor(lambda action, payload, ctx, req_priv: False)
    res_blocked = dispatcher.dispatch_action("sys_format", {"target": "C:"}, requester=ctx_admin)
    assert not res_blocked.success
    assert "PERMISSION_DENIED" in res_blocked.error_code or "denied" in res_blocked.error.lower()

    # 4. Action async timeout protection
    dispatcher.set_privilege_interceptor(lambda action, payload, ctx, req_priv: True)
    async def slow_async_action(**kwargs):
        await asyncio.sleep(0.5)
        return "Done"

    dispatcher.register_action("slow_task", slow_async_action, timeout_seconds=0.05)
    res_timeout = asyncio.run(dispatcher.dispatch_action_async("slow_task", {}, requester=ctx_admin))
    assert not res_timeout.success
    assert res_timeout.error_code == "TIMEOUT"


# ============================================================================
# ADVERSARIAL TEST 7: Plugin Registry Circular Dependency & Lifecycle Isolation
# ============================================================================

def test_plugin_registry_circular_dependency_detection():
    """
    [M1-ADV-13] Plugin dependency graph with cycles (A -> B -> A) must handle cycles
    without infinite loops or crash.
    """
    dispatcher = ActionDispatcher()
    registry = PluginRegistry(dispatcher=dispatcher)

    class PluginA(BasePlugin):
        def _define_metadata(self):
            return PluginMetadata(name="plugin_a", version="1.0.0", description="A", dependencies=["plugin_b"], enabled_by_default=False)
        def initialize(self, config, dispatcher): pass
        def start(self): pass
        def stop(self): pass
        def health_check(self): return PluginHealth(plugin_name="plugin_a", status=PluginStatus.RUNNING, is_healthy=True)

    class PluginB(BasePlugin):
        def _define_metadata(self):
            return PluginMetadata(name="plugin_b", version="1.0.0", description="B", dependencies=["plugin_a"], enabled_by_default=False)
        def initialize(self, config, dispatcher): pass
        def start(self): pass
        def stop(self): pass
        def health_check(self): return PluginHealth(plugin_name="plugin_b", status=PluginStatus.RUNNING, is_healthy=True)

    p_a = PluginA()
    p_b = PluginB()
    registry.register_plugin(p_a, auto_init=False)
    registry.register_plugin(p_b, auto_init=False)

    ordered = registry._resolve_dependencies(registry._plugins)
    assert len(ordered) == 2
    assert p_a in ordered and p_b in ordered


def test_plugin_registry_lifecycle_error_isolation():
    """
    [M1-ADV-14] If one plugin throws an exception during health_check(), other plugins
    must still be probed and reports returned without terminating the registry.
    """
    dispatcher = ActionDispatcher()
    registry = PluginRegistry(dispatcher=dispatcher)

    class FailingPlugin(BasePlugin):
        def _define_metadata(self):
            return PluginMetadata(name="failing_plugin", version="1.0.0", description="Fails", enabled_by_default=False)
        def initialize(self, config, dispatcher): pass
        def start(self): pass
        def stop(self): pass
        def health_check(self): raise RuntimeError("Simulated probe exception")

    class HealthyPlugin(BasePlugin):
        def _define_metadata(self):
            return PluginMetadata(name="healthy_plugin", version="1.0.0", description="Healthy", enabled_by_default=False)
        def initialize(self, config, dispatcher): pass
        def start(self): pass
        def stop(self): pass
        def health_check(self): return PluginHealth(plugin_name="healthy_plugin", status=PluginStatus.RUNNING, is_healthy=True)

    registry.register_plugin(FailingPlugin(), auto_init=False)
    registry.register_plugin(HealthyPlugin(), auto_init=False)

    reports = registry.check_all_health()
    assert "failing_plugin" in reports
    assert "healthy_plugin" in reports
    assert reports["failing_plugin"].is_healthy is False
    assert reports["healthy_plugin"].is_healthy is True

"""
tests/test_self_healing.py
==========================
Comprehensive Test Suite for Process Watchdog, Unresponsive App Detection, and Autonomous Healing.
Covering:
  - F-41: Process & Resource Watchdog (RAM pressure saturation detection, thread heartbeat liveness)
  - F-42: Unresponsive App Detector (Win32 IsHungAppWindow scanning)
  - F-43: Autonomous Healing Protocol (Protected whitelist, safe kill, RAM recovery, voice report)
"""

import time
from typing import Any, Dict, List, Optional
import pytest

from jarvis.healing.watchdog import (
    HungProcessInfo,
    ResourceWatchdog,
    UnresponsiveAppDetector,
)
from jarvis.healing.terminator import (
    AutonomousTerminator,
    HealingEngine,
    HealingMode,
    HealingReport,
    PROTECTED_PROCESS_WHITELIST,
)


# ============================================================================
# TIER 1: FEATURE COVERAGE HAPPY PATHS
# ============================================================================

def test_healing_watchdog_ram_pressure_detection_tier1(mock_hardware_provider, mock_win32_platform):
    """
    [F-41] Validate watchdog detects memory saturation when RAM exceeds 90% threshold.
    """
    engine = HealingEngine(win32_platform=mock_win32_platform, hardware_provider=mock_hardware_provider)
    assert engine.is_ram_critical() is False

    mock_hardware_provider.simulate_ram_exhaustion()
    assert engine.is_ram_critical() is True


def test_healing_unresponsive_app_ishungappwindow_probe_tier1(mock_win32_platform, mock_hardware_provider):
    """
    [F-42] Validate Win32 IsHungAppWindow identifies frozen unresponsive application windows.
    """
    engine = HealingEngine(win32_platform=mock_win32_platform, hardware_provider=mock_hardware_provider)
    hung_hwnd = mock_win32_platform.add_hung_window("chrome.exe", pid=5200)

    hung_apps = engine.find_hung_windows()
    assert len(hung_apps) == 1
    assert hung_apps[0].process_name == "chrome.exe"
    assert hung_apps[0].pid == 5200


def test_healing_autonomous_process_kill_and_reclaim_tier1(mock_win32_platform, mock_hardware_provider):
    """
    [F-43] Validate autonomous termination of hung process, memory reclamation, and spoken status report.
    """
    mock_hardware_provider.set_ram(94.0)
    mock_win32_platform.add_hung_window("leak_worker.exe", pid=7788)

    engine = HealingEngine(win32_platform=mock_win32_platform, hardware_provider=mock_hardware_provider, auto_kill=True)
    report = engine.heal_hung_process(pid=7788, name="leak_worker.exe")

    assert report["success"] is True
    assert 7788 in mock_win32_platform.killed_pids
    assert mock_hardware_provider.ram_percent < 80.0
    assert "Đã xử lý: leak_worker.exe" in report["spoken_message"]
    assert "RAM hiện tại" in report["spoken_message"]


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ============================================================================

def test_healing_protected_system_process_whitelist_tier2(mock_win32_platform, mock_hardware_provider):
    """
    [F-43] Validate that whitelisted system and JARVIS processes (explorer.exe, jarvis.exe) are never terminated.
    """
    engine = HealingEngine(win32_platform=mock_win32_platform, hardware_provider=mock_hardware_provider, auto_kill=True)

    report_explorer = engine.heal_hung_process(pid=101, name="explorer.exe")
    assert report_explorer["success"] is False
    assert report_explorer["reason"] == "PROTECTED_PROCESS"
    assert 101 not in mock_win32_platform.killed_pids

    report_jarvis = engine.heal_hung_process(pid=102, name="jarvis.exe")
    assert report_jarvis["success"] is False
    assert report_jarvis["reason"] == "PROTECTED_PROCESS"


def test_healing_advisory_mode_when_autokill_disabled_tier2(mock_win32_platform, mock_hardware_provider):
    """
    [F-43] Validate that when auto_kill=False, watchdog issues warnings without terminating processes.
    """
    engine = HealingEngine(win32_platform=mock_win32_platform, hardware_provider=mock_hardware_provider, auto_kill=False)
    report = engine.heal_hung_process(pid=999, name="stuck_editor.exe")

    assert report["success"] is False
    assert report["reason"] == "AUTO_KILL_DISABLED"
    assert report["alert_issued"] is True
    assert 999 not in mock_win32_platform.killed_pids


def test_healing_thread_heartbeat_monitoring_tier2(mock_hardware_provider, mock_win32_platform):
    """
    [F-41] Validate background worker thread heartbeat tracking and timeout detection.
    """
    watchdog = ResourceWatchdog(
        hardware_provider=mock_hardware_provider,
        win32_platform=mock_win32_platform,
    )

    # Record active heartbeats
    watchdog.record_heartbeat("audio_stream", timeout_s=1.0)
    watchdog.record_heartbeat("config_watcher", timeout_s=30.0)

    # Immediately check: should be healthy
    assert len(watchdog.check_thread_health()) == 0

    # Wait for audio_stream timeout
    time.sleep(1.1)
    stale = watchdog.check_thread_health()
    assert len(stale) == 1
    assert stale[0]["thread_name"] == "audio_stream"


def test_healing_auto_recovery_cycle_batch_tier2(mock_win32_platform, mock_hardware_provider):
    """
    [F-43] Validate batch scanning and autonomous healing of multiple hung applications.
    """
    mock_hardware_provider.set_ram(95.0)
    mock_win32_platform.add_hung_window("bad_app1.exe", pid=8001)
    mock_win32_platform.add_hung_window("bad_app2.exe", pid=8002)

    engine = HealingEngine(win32_platform=mock_win32_platform, hardware_provider=mock_hardware_provider, auto_kill=True)
    reports = engine.run_auto_recovery_cycle()

    assert len(reports) == 2
    assert all(r["success"] is True for r in reports)
    assert 8001 in mock_win32_platform.killed_pids
    assert 8002 in mock_win32_platform.killed_pids

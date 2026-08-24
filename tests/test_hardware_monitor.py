"""
tests/test_hardware_monitor.py
==============================
Comprehensive Test Suite for Hardware Telemetry, S.M.A.R.T. Disk Health, and Threshold Voice Alerts.
Covering:
  - F-20: Hardware Telemetry Collector (CPU, GPU, RAM, VRAM metrics via Win32 ctypes/CIM/nvidia-smi/psutil)
  - F-21: S.M.A.R.T. Disk Health Prober (Drive health status, wear life, bad sectors, partitions)
  - F-22: Hardware Voice Alerts & Query (Threshold alerts & "tình trạng hệ thống" speech formatting in VI/EN)
"""

import time
from typing import Any, Dict, List, Optional
import pytest

from jarvis.hardware.monitor import (
    DiskSmartMetrics,
    DiskSmartStatus,
    HardwareMetrics,
    HardwareMonitor,
)
from jarvis.hardware.reporter import HardwareReporter


# ============================================================================
# TIER 1: FEATURE COVERAGE HAPPY PATHS
# ============================================================================

def test_hardware_telemetry_cpu_gpu_ram_collection_tier1(mock_hardware_provider):
    """
    [F-20] Validate telemetry collection for CPU/GPU temperatures, fan speeds, and RAM/VRAM usage.
    """
    monitor = HardwareMonitor(provider=mock_hardware_provider)
    metrics = monitor.get_metrics()

    assert metrics.cpu_percent == 18.5
    assert metrics.cpu_temp_c == 48.0
    assert metrics.gpu_percent == 25.0
    assert metrics.gpu_temp_c == 52.0
    assert metrics.ram_percent == 37.5
    assert metrics.vram_used_gb == 3.0
    assert metrics.smart_status == "PASSED"


def test_hardware_smart_disk_health_prober_tier1(mock_hardware_provider):
    """
    [F-21] Validate S.M.A.R.T. disk prober queries disk health status.
    """
    monitor = HardwareMonitor(provider=mock_hardware_provider)
    metrics = monitor.get_metrics()
    assert metrics.smart_status == "PASSED"

    # Set warning condition
    mock_hardware_provider.set_smart("C:", "WARNING", reallocated_sectors=55)
    metrics_warn = monitor.get_metrics()
    assert metrics_warn.smart_status == "WARNING"
    assert metrics_warn.disks["C:"].reallocated_sectors == 55


def test_hardware_voice_query_tinh_trang_he_thong_tier1(mock_hardware_provider):
    """
    [F-22] Validate hardware status query 'tình trạng hệ thống?' formats concise Vietnamese voice summary.
    """
    monitor = HardwareMonitor(provider=mock_hardware_provider)
    summary = monitor.get_voice_summary(lang="vi")

    assert "tình trạng hệ thống" in summary.lower()
    assert "cpu" in summary.lower()
    assert "ram" in summary.lower()
    assert "ổ đĩa" in summary.lower()


def test_hardware_threshold_alert_trigger_tier1(mock_hardware_provider):
    """
    [F-22] Validate alert event dispatched when CPU temperature exceeds 85°C.
    """
    monitor = HardwareMonitor(provider=mock_hardware_provider, cpu_temp_threshold=85.0)
    mock_hardware_provider.set_cpu(percent=75.0, temp_c=92.0)

    alerts = monitor.check_thresholds()
    assert len(alerts) >= 1
    assert alerts[0]["component"] == "cpu"
    assert "92.0" in alerts[0]["message"]


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ============================================================================

def test_hardware_missing_gpu_sensor_graceful_handling_tier2(mock_hardware_provider):
    """
    [F-20] Validate that systems lacking dedicated GPU return None without throwing exceptions.
    """
    mock_hardware_provider.set_gpu(util_percent=0.0, temp_c=None, vram_used_gb=0.0)
    monitor = HardwareMonitor(provider=mock_hardware_provider)
    metrics = monitor.get_metrics()

    assert metrics.gpu_temp_c is None
    summary = monitor.get_voice_summary()
    assert isinstance(summary, str)
    assert "tình trạng hệ thống" in summary.lower()


def test_hardware_alert_debounce_cooldown_tier2(mock_hardware_provider):
    """
    [F-22] Validate alert debounce cooldown prevents voice spam when temperature fluctuates around threshold.
    """
    monitor = HardwareMonitor(provider=mock_hardware_provider, cpu_temp_threshold=85.0, alert_cooldown_s=5.0)
    mock_hardware_provider.set_cpu(percent=80.0, temp_c=89.0)

    # 1st check -> Alert triggered
    alerts1 = monitor.check_thresholds()
    assert len(alerts1) == 1

    # Immediate 2nd check within cooldown -> Debounced
    alerts2 = monitor.check_thresholds()
    assert len(alerts2) == 0


def test_hardware_english_voice_summary_tier2(mock_hardware_provider):
    """
    [F-22] Validate English voice summary format.
    """
    monitor = HardwareMonitor(provider=mock_hardware_provider)
    summary_en = monitor.get_voice_summary(lang="en")

    assert "system status" in summary_en.lower()
    assert "cpu usage" in summary_en.lower()
    assert "ram usage" in summary_en.lower()


def test_hardware_reporter_component_queries_tier2(mock_hardware_provider):
    """
    [F-22] Validate HardwareReporter component-specific natural language queries.
    """
    monitor = HardwareMonitor(provider=mock_hardware_provider)
    reporter = HardwareReporter(monitor=monitor)

    cpu_ans = reporter.process_voice_query("nhiệt độ CPU thế nào?")
    assert "cpu" in cpu_ans.lower()
    assert "độ c" in cpu_ans.lower()

    ram_ans = reporter.process_voice_query("bộ nhớ RAM còn bao nhiêu?")
    assert "ram" in ram_ans.lower()
    assert "%" in ram_ans or "phần trăm" in ram_ans

    markdown_rep = reporter.format_markdown_report()
    assert "# 🖥️ JARVIS Hardware Diagnostics Report" in markdown_rep
    assert "CPU Usage" in markdown_rep
    assert "RAM Usage" in markdown_rep


def test_hardware_live_zero_dependency_probing_tier2():
    """
    [F-20, F-21] Validate live zero-dependency probing runs without throwing exceptions on host OS.
    """
    live_monitor = HardwareMonitor(provider=None)
    metrics = live_monitor.get_metrics()

    assert isinstance(metrics.cpu_percent, (int, float))
    assert isinstance(metrics.ram_percent, (int, float))
    assert isinstance(metrics.smart_status, str)
    assert len(metrics.disks) >= 1
    assert isinstance(metrics.to_dict(), dict)

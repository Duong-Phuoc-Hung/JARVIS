"""
jarvis/hardware
===============
Hardware Telemetry, S.M.A.R.T. Prober, and Voice Diagnostic Alerting Package.
Features:
  - F-20: Multi-source Hardware Telemetry (CPU, GPU, RAM, VRAM, fan speeds).
  - F-21: S.M.A.R.T. Disk Health Prober and Volume Diagnostics.
  - F-22: Vocal Threshold Alerts & Natural Language Query Engine.
"""
from __future__ import annotations

from jarvis.hardware.monitor import (
    DiskSmartMetrics,
    DiskSmartStatus,
    HardwareMetrics,
    HardwareMonitor,
)
from jarvis.hardware.reporter import HardwareReporter

__all__ = [
    "DiskSmartMetrics",
    "DiskSmartStatus",
    "HardwareMetrics",
    "HardwareMonitor",
    "HardwareReporter",
]

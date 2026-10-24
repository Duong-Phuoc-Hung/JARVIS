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

from jarvis.hardware.eco_governor import (
    AdaptiveEcoGovernor,
    EcoLevel,
    GovernancePolicy,
)
from jarvis.hardware.monitor import (
    DiskSmartMetrics,
    DiskSmartStatus,
    HardwareMetrics,
    HardwareMonitor,
)
from jarvis.hardware.polyglot_runtime import (
    ExecutionTelemetry,
    PolyglotInferenceEngine,
)
from jarvis.hardware.reporter import HardwareReporter
from jarvis.hardware.universal_hal import (
    AcceleratorBackend,
    CPUArchitecture,
    DeviceProfile,
    HardwareTier,
    ISACapabilities,
    PowerProfile,
    UniversalHardwareAbstractionLayer,
    get_universal_hal,
)

__all__ = [
    "AdaptiveEcoGovernor",
    "AcceleratorBackend",
    "CPUArchitecture",
    "DeviceProfile",
    "DiskSmartMetrics",
    "DiskSmartStatus",
    "EcoLevel",
    "ExecutionTelemetry",
    "GovernancePolicy",
    "HardwareMetrics",
    "HardwareMonitor",
    "HardwareReporter",
    "HardwareTier",
    "ISACapabilities",
    "PolyglotInferenceEngine",
    "PowerProfile",
    "UniversalHardwareAbstractionLayer",
    "get_universal_hal",
]

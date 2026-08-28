"""
jarvis/healing
==============
Self-healing and Process Watchdog Package for JARVIS.
Features:
  - F-41: Resource & Process Watchdog (RAM > 90%, CPU saturation, thread heartbeats).
  - F-42: Unresponsive App Detector via Win32 IsHungAppWindow.
  - F-43: Autonomous Safe Termination, OS Whitelist Protection, Vocal Status Reporting.
"""
from __future__ import annotations

from jarvis.healing.terminator import (
    PROTECTED_PROCESS_WHITELIST,
    AutonomousTerminator,
    HealingEngine,
    HealingMode,
    HealingReport,
)
from jarvis.healing.watchdog import (
    HungProcessInfo,
    ResourceWatchdog,
    UnresponsiveAppDetector,
)

__all__ = [
    "HungProcessInfo",
    "ResourceWatchdog",
    "UnresponsiveAppDetector",
    "AutonomousTerminator",
    "HealingEngine",
    "HealingMode",
    "HealingReport",
    "PROTECTED_PROCESS_WHITELIST",
]

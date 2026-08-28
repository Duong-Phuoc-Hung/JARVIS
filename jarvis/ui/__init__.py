"""
jarvis/ui/__init__.py
=====================
JARVIS User Interface Subsystem: System Tray Controller and Real-Time Dashboard.
"""
from __future__ import annotations

from jarvis.ui.dashboard import DashboardMetricsServer, DashboardServer
from jarvis.ui.tray import SystemTrayController, TrayStatus

__all__ = [
    "SystemTrayController",
    "TrayStatus",
    "DashboardServer",
    "DashboardMetricsServer",
]

"""
jarvis/proactive
================
Proactive Intelligence subsystem for JARVIS Personal AI (R6).
Coordinates Smart Reminders, Hardware Health Telemetry, Focus Mode (Pomodoro),
Daily Morning Briefings, and Inactivity Check-ins.
"""

from jarvis.proactive.briefing_scheduler import DailyBriefingScheduler
from jarvis.proactive.engine import ProactiveConfig, ProactiveEngine
from jarvis.proactive.health_monitor import HealthAlert, SystemHealthMonitor
from jarvis.proactive.inactivity import InactivityMonitor
from jarvis.proactive.pomodoro import PomodoroState, PomodoroStatus, PomodoroTimer
from jarvis.proactive.reminders import ReminderScheduler, ScheduledReminder

__all__ = [
    "ReminderScheduler",
    "ScheduledReminder",
    "SystemHealthMonitor",
    "HealthAlert",
    "PomodoroTimer",
    "PomodoroState",
    "PomodoroStatus",
    "DailyBriefingScheduler",
    "InactivityMonitor",
    "ProactiveEngine",
    "ProactiveConfig",
]

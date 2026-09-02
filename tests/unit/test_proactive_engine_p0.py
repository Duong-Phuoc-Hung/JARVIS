"""
tests/unit/test_proactive_engine_p0.py
======================================
Comprehensive Unit Test Suite for ProactiveEngine Worker & Subsystems (v4.6.0 P0-B).
Covers:
  1. Worker Module Imports & Re-exports
  2. Engine Lifecycle & Thread-Safety (start/stop/is_running)
  3. Reminder Scheduling, Execution, Priority, and Cancellation
  4. ActionDispatcher Integration ('proactive_reminder', 'proactive_pomodoro_start', 'proactive_pomodoro_stop')
  5. System Health Watchdog (RAM > 90%, CPU > 95%, Normal Suppression, Cooldown, EventBus alerts)
  6. Pomodoro Focus Timer (WORK -> BREAK state machine, DND suppression & critical bypass)
  7. Inactivity Watchdog & Daily Briefing Scheduler
  8. Master ProactiveEngine Synchronous Tick Simulation
"""
from __future__ import annotations

import datetime
import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.workers import (
    DailyBriefingScheduler,
    HealthAlert,
    InactivityMonitor,
    PomodoroState,
    PomodoroStatus,
    PomodoroTimer,
    ProactiveConfig,
    ProactiveEngine,
    ReminderScheduler,
    ScheduledReminder,
    SystemHealthMonitor,
)
from jarvis.workers.proactive import ProactiveEngine as WorkerProactiveEngine


class MockTelemetryProvider:
    """Configurable mock telemetry provider for deterministic hardware health tests."""

    def __init__(
        self,
        cpu_percent: float = 20.0,
        ram_percent: float = 40.0,
        cpu_temp_c: float | None = 45.0,
        disk_free_gb: float = 100.0,
        disk_drive: str = "C:",
        battery_percent: float | None = 90.0,
        battery_plugged: bool = True,
    ) -> None:
        self.cpu_percent = cpu_percent
        self.ram_percent = ram_percent
        self.cpu_temp_c = cpu_temp_c
        self.disk_free_gb = disk_free_gb
        self.disk_drive = disk_drive
        self.battery_percent = battery_percent
        self.battery_plugged = battery_plugged


# ============================================================================
# 1. IMPORTS & RE-EXPORTS
# ============================================================================

def test_proactive_worker_imports_and_reexports() -> None:
    """Verify ProactiveEngine and all sub-modules can be imported cleanly from jarvis.workers."""
    assert ProactiveEngine is WorkerProactiveEngine
    assert issubclass(ProactiveEngine, object)
    assert ReminderScheduler is not None
    assert ScheduledReminder is not None
    assert SystemHealthMonitor is not None
    assert HealthAlert is not None
    assert PomodoroTimer is not None
    assert PomodoroState is not None
    assert PomodoroStatus is not None
    assert DailyBriefingScheduler is not None
    assert InactivityMonitor is not None
    assert ProactiveConfig is not None


# ============================================================================
# 2. LIFECYCLE & THREAD SAFETY
# ============================================================================

def test_proactive_engine_lifecycle_start_stop() -> None:
    """Verify ProactiveEngine starts and stops sub-engines in a clean thread-safe lifecycle."""
    tts_mock = MagicMock()
    overlay_mock = MagicMock()
    engine = ProactiveEngine(
        config={"enabled": True},
        tts_callback=tts_mock,
        overlay_callback=overlay_mock,
    )

    assert engine.is_running() is False
    assert engine.reminders.is_running() is False
    assert engine.health_monitor.is_running() is False

    engine.start()
    assert engine.is_running() is True
    assert engine.reminders.is_running() is True
    assert engine.health_monitor.is_running() is True
    assert engine.briefing_scheduler.is_running() is True
    assert engine.inactivity.is_running() is True

    # Calling start() again when running is a no-op
    engine.start()
    assert engine.is_running() is True

    engine.stop()
    assert engine.is_running() is False
    assert engine.reminders.is_running() is False
    assert engine.health_monitor.is_running() is False

    # Calling stop() again when stopped is a no-op
    engine.stop()
    assert engine.is_running() is False


def test_proactive_engine_concurrent_lifecycle() -> None:
    """Verify concurrent start() and stop() calls from multiple threads do not deadlock."""
    engine = ProactiveEngine(config={"enabled": True})
    errors: list[Exception] = []

    def worker_start_stop() -> None:
        try:
            for _ in range(5):
                engine.start()
                time.sleep(0.005)
                engine.stop()
                time.sleep(0.005)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker_start_stop) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert len(errors) == 0
    engine.stop()
    assert engine.is_running() is False


# ============================================================================
# 3. REMINDER SCHEDULER TESTS
# ============================================================================

def test_reminder_scheduling_and_tick_execution() -> None:
    """Verify reminders are prioritized by timestamp, triggered upon expiry, and invoke callbacks."""
    tts_mock = MagicMock()
    overlay_mock = MagicMock()
    scheduler = ReminderScheduler(
        tts_callback=tts_mock,
        overlay_callback=overlay_mock,
        enabled=True,
    )
    base_t = 1000.0

    r1 = scheduler.add_scheduled_reminder("Uống 500ml nước", trigger_timestamp=base_t + 10.0)
    r2 = scheduler.add_scheduled_reminder("Tham gia họp nhóm", trigger_timestamp=base_t + 30.0)

    pending = scheduler.get_pending_reminders()
    assert len(pending) == 2
    assert pending[0]["reminder_id"] == r1
    assert pending[1]["reminder_id"] == r2

    # Tick before any reminder is due
    due_none = scheduler.tick(now=base_t + 5.0)
    assert len(due_none) == 0
    assert not tts_mock.called

    # Tick when r1 is due
    due_r1 = scheduler.tick(now=base_t + 15.0)
    assert len(due_r1) == 1
    assert due_r1[0].reminder_id == r1
    assert due_r1[0].completed is True
    tts_mock.assert_called_with("Thưa Ngài, đây là lời nhắc: Uống 500ml nước")
    overlay_mock.assert_called_with("⏰ Lời nhắc", "Uống 500ml nước")

    # Remaining pending is only r2
    assert len(scheduler.get_pending_reminders()) == 1

    # Tick when r2 is due
    due_r2 = scheduler.tick(now=base_t + 35.0)
    assert len(due_r2) == 1
    assert due_r2[0].reminder_id == r2
    assert len(scheduler.get_pending_reminders()) == 0


def test_reminder_cancellation() -> None:
    """Verify pending reminders can be cancelled by ID."""
    scheduler = ReminderScheduler(enabled=True)
    base_t = 1000.0

    r_id = scheduler.add_scheduled_reminder("Tập thể dục", trigger_timestamp=base_t + 60.0)
    assert len(scheduler.get_pending_reminders()) == 1

    cancelled = scheduler.cancel_reminder(r_id)
    assert cancelled is True
    assert len(scheduler.get_pending_reminders()) == 0

    # Cancelling non-existent or already cancelled reminder returns False
    assert scheduler.cancel_reminder("invalid-id") is False


# ============================================================================
# 4. ACTION DISPATCHER & APP INTEGRATION
# ============================================================================

def test_action_dispatcher_registration_and_execution() -> None:
    """Verify ProactiveEngine registers actions with ActionDispatcher and responds to dispatch."""
    dispatcher = ActionDispatcher()
    engine = ProactiveEngine(dispatcher=dispatcher, config={"enabled": True})

    # Verify actions are registered
    actions = dispatcher.list_actions()
    assert "proactive_reminder" in actions
    assert "proactive_pomodoro_start" in actions
    assert "proactive_pomodoro_stop" in actions

    # Dispatch proactive_reminder
    res_reminder = dispatcher.dispatch_action(
        "proactive_reminder",
        {"message": "Đọc sách 15 phút", "delay_seconds": 120.0},
    )
    assert res_reminder.success
    assert res_reminder.data["status"] == "success"
    assert "reminder_id" in res_reminder.data
    assert "120" in res_reminder.data["message"]

    pending = engine.get_pending_reminders()
    assert len(pending) == 1
    assert pending[0]["text"] == "Đọc sách 15 phút"

    # Dispatch proactive_pomodoro_start
    res_pomo_start = dispatcher.dispatch_action(
        "proactive_pomodoro_start",
        {"work_minutes": 30.0, "break_minutes": 5.0},
    )
    assert res_pomo_start.success
    assert res_pomo_start.data["status"] == "success"
    assert engine.get_pomodoro_status()["state"] == PomodoroState.WORK.value

    # Dispatch proactive_pomodoro_stop
    res_pomo_stop = dispatcher.dispatch_action("proactive_pomodoro_stop", {})
    assert res_pomo_stop.success
    assert res_pomo_stop.data["status"] == "success"
    assert engine.get_pomodoro_status()["state"] == PomodoroState.IDLE.value


# ============================================================================
# 5. HARDWARE ALERT WATCHDOG & EVENTBUS
# ============================================================================

def test_hardware_alert_ram_over_90_percent() -> None:
    """Verify SystemHealthMonitor alerts when RAM exceeds threshold (RAM > 90%)."""
    provider = MockTelemetryProvider(cpu_percent=30.0, ram_percent=94.5)
    tts_mock = MagicMock()
    event_bus = EventBus()
    received_events: list[dict[str, Any]] = []
    event_bus.subscribe("hardware.alert", lambda **payload: received_events.append(payload))

    engine = ProactiveEngine(
        telemetry_provider=provider,
        tts_callback=tts_mock,
        event_bus=event_bus,
        config={
            "ram_threshold": 90.0,
            "cpu_threshold": 95.0,
            "health_cooldown_s": 600.0,
        },
    )

    alerts = engine.health_monitor.check_telemetry(now=1000.0)
    assert len(alerts) == 1
    assert alerts[0].alert_type == "ram"
    assert alerts[0].level == "CRITICAL"
    assert alerts[0].value == 94.5
    assert "RAM" in alerts[0].message

    # Verify TTS vocal warning
    assert tts_mock.called

    # Verify EventBus received hardware.alert
    assert len(received_events) == 1
    assert received_events[0]["component"] == "ram"
    assert received_events[0]["value"] == 94.5


def test_hardware_alert_cpu_over_95_percent() -> None:
    """Verify SystemHealthMonitor alerts when CPU exceeds threshold (CPU > 95%)."""
    provider = MockTelemetryProvider(cpu_percent=97.8, ram_percent=60.0)
    tts_mock = MagicMock()
    event_bus = EventBus()
    received_events: list[dict[str, Any]] = []
    event_bus.subscribe("hardware.alert", lambda **payload: received_events.append(payload))

    engine = ProactiveEngine(
        telemetry_provider=provider,
        tts_callback=tts_mock,
        event_bus=event_bus,
        config={
            "ram_threshold": 90.0,
            "cpu_threshold": 95.0,
        },
    )

    alerts = engine.health_monitor.check_telemetry(now=1000.0)
    assert len(alerts) == 1
    assert alerts[0].alert_type == "cpu"
    assert alerts[0].level == "CRITICAL"
    assert alerts[0].value == 97.8
    assert "CPU" in alerts[0].message
    assert len(received_events) == 1


def test_hardware_alert_normal_metrics_suppressed() -> None:
    """Verify normal telemetry metrics (RAM 45%, CPU 25%) trigger no alerts."""
    provider = MockTelemetryProvider(cpu_percent=25.0, ram_percent=45.0, cpu_temp_c=50.0)
    tts_mock = MagicMock()
    event_bus = EventBus()
    received_events: list[dict[str, Any]] = []
    event_bus.subscribe("hardware.alert", lambda **payload: received_events.append(payload))

    engine = ProactiveEngine(
        telemetry_provider=provider,
        tts_callback=tts_mock,
        event_bus=event_bus,
        config={"ram_threshold": 90.0, "cpu_threshold": 95.0},
    )

    alerts = engine.health_monitor.check_telemetry(now=1000.0)
    assert len(alerts) == 0
    assert not tts_mock.called
    assert len(received_events) == 0


def test_hardware_alert_cooldown_debouncing() -> None:
    """Verify cooldown timer prevents alert spamming within the cooldown window."""
    provider = MockTelemetryProvider(cpu_percent=98.0, ram_percent=50.0)
    tts_mock = MagicMock()
    engine = ProactiveEngine(
        telemetry_provider=provider,
        tts_callback=tts_mock,
        config={"cpu_threshold": 95.0, "health_cooldown_s": 600.0},
    )

    # First breach at t=1000.0 triggers alert
    alerts1 = engine.health_monitor.check_telemetry(now=1000.0)
    assert len(alerts1) == 1
    assert tts_mock.call_count == 1

    # Second check at t=1050.0 within 600s cooldown is suppressed
    alerts2 = engine.health_monitor.check_telemetry(now=1050.0)
    assert len(alerts2) == 0
    assert tts_mock.call_count == 1

    # Third check at t=1700.0 (> 600s later) fires alert again
    alerts3 = engine.health_monitor.check_telemetry(now=1700.0)
    assert len(alerts3) == 1
    assert tts_mock.call_count == 2


# ============================================================================
# 6. POMODORO FOCUS TIMER TESTS
# ============================================================================

def test_pomodoro_state_machine_and_dnd() -> None:
    """Verify Pomodoro transitions WORK -> BREAK -> COMPLETED and enforces DND suppression."""
    tts_mock = MagicMock()
    timer = PomodoroTimer(tts_callback=tts_mock, enabled=True)
    base_t = 1000.0

    with patch("time.time", return_value=base_t):
        timer.start(work_minutes=25, break_minutes=5, cycles=1)

    assert timer.get_status().state == PomodoroState.WORK
    assert timer.is_suppressing_notifications() is True

    # Non-critical notifications are suppressed; critical hardware alerts bypass DND
    assert timer.should_suppress_notification(is_critical=False) is True
    assert timer.should_suppress_notification(is_critical=True) is False

    # Transition to BREAK after 25 minutes (1500s)
    event_break = timer.tick(now=base_t + 1501.0)
    assert event_break == "WORK_FINISHED"
    assert timer.get_status().state == PomodoroState.BREAK
    assert timer.is_suppressing_notifications() is False
    assert timer.should_suppress_notification(is_critical=False) is False

    # Transition to COMPLETED after 5 minutes break (300s)
    event_complete = timer.tick(now=base_t + 1802.0)
    assert event_complete == "COMPLETED"
    assert timer.get_status().state == PomodoroState.COMPLETED


def test_pomodoro_pause_and_resume() -> None:
    """Verify Pomodoro pause and resume preserve remaining time."""
    timer = PomodoroTimer(enabled=True)
    base_t = 1000.0

    with patch("time.time", return_value=base_t):
        timer.start(work_minutes=25, break_minutes=5, cycles=1)

    # 10 minutes pass, 15 minutes remain
    with patch("time.time", return_value=base_t + 600.0):
        paused = timer.pause()
        assert paused is True
        assert timer.get_status().state == PomodoroState.PAUSED
        assert timer.get_status().time_remaining_seconds == pytest.approx(900.0, abs=2.0)

    # Resume at t = 1600.0 (1000s of pause elapsed)
    with patch("time.time", return_value=base_t + 1600.0):
        resumed = timer.resume()
        assert resumed is True
        assert timer.get_status().state == PomodoroState.WORK
        assert timer.get_status().time_remaining_seconds == pytest.approx(900.0, abs=2.0)


# ============================================================================
# 7. INACTIVITY & BRIEFING WATCHDOGS
# ============================================================================

def test_daily_briefing_and_inactivity_monitors() -> None:
    """Verify DailyBriefingScheduler trigger and InactivityMonitor idle detection."""
    tts_briefing = MagicMock()
    briefing = DailyBriefingScheduler(
        briefing_provider=lambda **kwargs: {"spoken_summary": "Chào buổi sáng thưa Ngài."},
        tts_callback=tts_briefing,
        enabled=True,
    )
    res = briefing.trigger_now()
    assert "Chào buổi sáng" in res["spoken_summary"]
    tts_briefing.assert_called_once()

    tts_inactivity = MagicMock()
    inactivity = InactivityMonitor(
        tts_callback=tts_inactivity,
        inactivity_threshold_seconds=3600.0,
        enabled=True,
    )
    base_t = 1000.0
    inactivity.record_activity(now=base_t)

    # Within threshold (1800s idle)
    assert inactivity.check_inactivity(now=base_t + 1800.0) is False
    assert not tts_inactivity.called

    # Past threshold (3605s idle)
    assert inactivity.check_inactivity(now=base_t + 3605.0) is True
    tts_inactivity.assert_called_once()


# ============================================================================
# 8. MASTER UNIFIED SYNCHRONOUS TICK
# ============================================================================

def test_proactive_engine_unified_tick() -> None:
    """Verify engine.tick() executes a coordinated step across all sub-services."""
    provider = MockTelemetryProvider(cpu_percent=96.0, ram_percent=40.0)
    engine = ProactiveEngine(
        telemetry_provider=provider,
        config={"cpu_threshold": 95.0, "enabled": True},
    )
    base_t = 1000.0
    engine.reminders.add_scheduled_reminder("Uống trà", trigger_timestamp=base_t + 10.0)

    # Tick at base_t + 15.0: reminder due and CPU alert triggered
    report = engine.tick(now=base_t + 15.0)

    assert "reminders_executed" in report
    assert len(report["reminders_executed"]) == 1
    assert report["reminders_executed"][0]["text"] == "Uống trà"

    assert "health_alerts" in report
    assert len(report["health_alerts"]) == 1
    assert report["health_alerts"][0]["alert_type"] == "cpu"

"""
tests/unit/test_proactive_engine.py
===================================
Comprehensive Unit Test Suite for Proactive Intelligence Subsystem (R6).
Covers:
  1. ReminderScheduler:
     - Priority queue ordering (earliest reminder pops first)
     - Timing expiry via tick(now) and real/synthetic clocks
     - Cancellation (valid vs invalid IDs, already completed)
     - Custom callback execution and exception safety
     - Natural language relative time parsing (Vietnamese & English)
     - TTS and overlay notification dispatches
     - Thread lifecycle (start, stop, is_running)

  2. SystemHealthMonitor:
     - CPU utilization threshold (> 90%)
     - RAM utilization threshold (> 85%)
     - Disk free threshold (< 10 GB)
     - CPU temperature threshold (> 85°C)
     - Battery low threshold (< 20% and discharging)
     - Normal metrics suppression
     - Cooldown debouncing (prevents spamming within cooldown window)
     - Hysteresis recovery logic
     - Custom telemetry provider injection & alert dispatching
     - Thread lifecycle

  3. PomodoroTimer:
     - State machine transitions: WORK -> BREAK -> WORK -> COMPLETED
     - Notification suppression (DND during WORK phase, allowed for critical alerts)
     - Pause and resume logic with remaining time preservation
     - Stop and reset behavior
     - Status query serialization
     - Vocal announcements upon phase changes
     - Thread lifecycle

  4. DailyBriefingScheduler:
     - Scheduled time evaluation (e.g. 08:00 AM)
     - Single execution per calendar date guarantee
     - On-demand trigger_now() with WebIntelligenceHub integration & fallback
     - TTS and overlay output formatting
     - Target time updating
     - Thread lifecycle

  5. InactivityMonitor:
     - 2-hour (> 7200s) inactivity threshold trigger
     - record_activity() reset
     - get_idle_seconds() precision
     - Cooldown period after greeting (1 hour / 3600s)
     - TTS check-in phrase and overlay dispatching
     - Thread lifecycle

  6. ProactiveEngine Master Coordinator:
     - Master lifecycle (start, stop, is_running)
     - Per-feature configuration toggles & master toggle
     - Nested and flat YAML/JSON configuration parsing
     - Delegated methods (reminders, pomodoro, health, briefing, inactivity)
     - Unified deterministic tick() execution
"""
from __future__ import annotations

import datetime
import threading
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch
import pytest

from jarvis.proactive.briefing_scheduler import DailyBriefingScheduler
from jarvis.proactive.engine import ProactiveConfig, ProactiveEngine
from jarvis.proactive.health_monitor import HealthAlert, SystemHealthMonitor
from jarvis.proactive.inactivity import InactivityMonitor
from jarvis.proactive.pomodoro import PomodoroState, PomodoroStatus, PomodoroTimer
from jarvis.proactive.reminders import ReminderScheduler, ScheduledReminder


# ============================================================================
# 1. REMINDER SCHEDULER TESTS
# ============================================================================

def test_reminder_scheduler_add_and_pending_ordering():
    """Verify reminders are stored in priority order by trigger timestamp."""
    scheduler = ReminderScheduler(enabled=True)
    base_t = 1000.0

    r3 = scheduler.add_scheduled_reminder("Reminder 3 (in 30s)", trigger_timestamp=base_t + 30.0)
    r1 = scheduler.add_scheduled_reminder("Reminder 1 (in 10s)", trigger_timestamp=base_t + 10.0)
    r2 = scheduler.add_scheduled_reminder("Reminder 2 (in 20s)", trigger_timestamp=base_t + 20.0)

    pending = scheduler.get_pending_reminders()
    assert len(pending) == 3
    assert [p["reminder_id"] for p in pending] == [r1, r2, r3]
    assert pending[0]["text"] == "Reminder 1 (in 10s)"


def test_reminder_scheduler_tick_due_reminders():
    """Verify tick executes reminders whose trigger timestamp is <= now."""
    tts_mock = MagicMock()
    overlay_mock = MagicMock()
    cb_mock = MagicMock()

    scheduler = ReminderScheduler(
        tts_callback=tts_mock,
        overlay_callback=overlay_mock,
        enabled=True,
    )
    base_t = 1000.0

    r1 = scheduler.add_scheduled_reminder("Feed cat", trigger_timestamp=base_t + 10.0, callback=cb_mock)
    r2 = scheduler.add_scheduled_reminder("Drink water", trigger_timestamp=base_t + 20.0)
    r3 = scheduler.add_scheduled_reminder("Join meeting", trigger_timestamp=base_t + 30.0)

    # Tick at base_t + 5s -> none due
    due_0 = scheduler.tick(now=base_t + 5.0)
    assert len(due_0) == 0
    assert len(scheduler.get_pending_reminders()) == 3

    # Tick at base_t + 15s -> r1 due
    due_1 = scheduler.tick(now=base_t + 15.0)
    assert len(due_1) == 1
    assert due_1[0].reminder_id == r1
    assert due_1[0].completed is True
    cb_mock.assert_called_once()
    tts_mock.assert_called_with("Thưa Ngài, đây là lời nhắc: Feed cat")
    overlay_mock.assert_called_with("⏰ Lời nhắc", "Feed cat")

    # Tick at base_t + 35s -> r2 and r3 due
    due_2 = scheduler.tick(now=base_t + 35.0)
    assert len(due_2) == 2
    assert [r.reminder_id for r in due_2] == [r2, r3]
    assert len(scheduler.get_pending_reminders()) == 0


def test_reminder_scheduler_cancellation():
    """Verify cancelling a reminder prevents its execution."""
    tts_mock = MagicMock()
    scheduler = ReminderScheduler(tts_callback=tts_mock, enabled=True)
    base_t = 1000.0

    r1 = scheduler.add_scheduled_reminder("Dentist", trigger_timestamp=base_t + 10.0)
    r2 = scheduler.add_scheduled_reminder("Gym", trigger_timestamp=base_t + 20.0)

    # Cancel r1
    assert scheduler.cancel_reminder(r1) is True
    # Re-cancelling returns False
    assert scheduler.cancel_reminder(r1) is False
    # Cancelling non-existent ID returns False
    assert scheduler.cancel_reminder("non_existent") is False

    # Tick past r1 and r2
    due = scheduler.tick(now=base_t + 25.0)
    assert len(due) == 1
    assert due[0].reminder_id == r2
    assert tts_mock.call_count == 1
    assert tts_mock.call_args[0][0] == "Thưa Ngài, đây là lời nhắc: Gym"


def test_reminder_scheduler_relative_add():
    """Verify add_reminder calculates delay correctly."""
    scheduler = ReminderScheduler(enabled=True)
    with patch("time.time", return_value=5000.0):
        rid = scheduler.add_reminder("Check oven", delay_seconds=120.0)
        reminder = scheduler.get_reminder(rid)
        assert reminder is not None
        assert reminder["trigger_timestamp"] == 5120.0
        assert reminder["text"] == "Check oven"


def test_reminder_scheduler_callback_exception_safety():
    """Verify errors in user callback do not crash the scheduler."""
    def buggy_callback(r):
        raise RuntimeError("Callback failed!")

    tts_mock = MagicMock()
    scheduler = ReminderScheduler(tts_callback=tts_mock, enabled=True)
    rid = scheduler.add_scheduled_reminder("Buggy task", trigger_timestamp=100.0, callback=buggy_callback)

    due = scheduler.tick(now=150.0)
    assert len(due) == 1
    assert due[0].completed is True
    # TTS is still vocalized despite callback error
    tts_mock.assert_called_once()


def test_reminder_scheduler_relative_time_parser():
    """Verify Vietnamese and English relative time parsing patterns."""
    # Vietnamese
    parsed_vi_1 = ReminderScheduler.parse_relative_time("nhắc tôi sau 5 phút kiểm tra email")
    assert parsed_vi_1 is not None
    assert parsed_vi_1[0] == "kiểm tra email"
    assert parsed_vi_1[1] == 300.0

    parsed_vi_2 = ReminderScheduler.parse_relative_time("nhắc sau 10 giây")
    assert parsed_vi_2 is not None
    assert parsed_vi_2[1] == 10.0

    parsed_vi_3 = ReminderScheduler.parse_relative_time("nhắc tôi sau 2 giờ họp team")
    assert parsed_vi_3 is not None
    assert parsed_vi_3[0] == "họp team"
    assert parsed_vi_3[1] == 7200.0

    # English
    parsed_en_1 = ReminderScheduler.parse_relative_time("remind me in 10 minutes to take medicine")
    assert parsed_en_1 is not None
    assert parsed_en_1[0] == "take medicine"
    assert parsed_en_1[1] == 600.0

    parsed_en_2 = ReminderScheduler.parse_relative_time("remind in 45 seconds")
    assert parsed_en_2 is not None
    assert parsed_en_2[1] == 45.0

    # Unrelated
    assert ReminderScheduler.parse_relative_time("thời tiết hôm nay thế nào") is None


def test_reminder_scheduler_thread_lifecycle():
    """Verify background worker starts and stops safely."""
    scheduler = ReminderScheduler(check_interval_seconds=0.02, enabled=True)
    assert scheduler.is_running() is False
    scheduler.start()
    assert scheduler.is_running() is True
    time.sleep(0.05)
    scheduler.stop()
    assert scheduler.is_running() is False


# ============================================================================
# 2. SYSTEM HEALTH MONITOR TESTS
# ============================================================================

class MockTelemetryProvider:
    """Mock telemetry data source for testing health checks."""
    def __init__(
        self,
        cpu: float = 30.0,
        ram: float = 40.0,
        disk_free_gb: float = 100.0,
        cpu_temp: float = 50.0,
        battery: float = 80.0,
        battery_plugged: bool = True,
        disk_drive: str = "C:",
    ) -> None:
        self.cpu_percent = cpu
        self.ram_percent = ram
        self.disk_free_gb = disk_free_gb
        self.cpu_temp_c = cpu_temp
        self.battery_percent = battery
        self.battery_plugged = battery_plugged
        self.disk_drive = disk_drive


def test_health_monitor_normal_metrics_no_alerts():
    """Verify normal telemetry values trigger no alerts."""
    provider = MockTelemetryProvider(cpu=45.0, ram=60.0, disk_free_gb=50.0, cpu_temp=60.0, battery=75.0, battery_plugged=True)
    tts_mock = MagicMock()
    monitor = SystemHealthMonitor(telemetry_provider=provider, tts_callback=tts_mock, enabled=True)

    alerts = monitor.check_telemetry(now=1000.0)
    assert len(alerts) == 0
    tts_mock.assert_not_called()


def test_health_monitor_cpu_threshold_breach():
    """Verify CPU > 90.0% triggers alert and vocal warning."""
    provider = MockTelemetryProvider(cpu=94.5)
    tts_mock = MagicMock()
    overlay_mock = MagicMock()
    monitor = SystemHealthMonitor(
        telemetry_provider=provider,
        tts_callback=tts_mock,
        overlay_callback=overlay_mock,
        cpu_threshold=90.0,
        enabled=True,
    )

    alerts = monitor.check_telemetry(now=1000.0)
    assert len(alerts) == 1
    assert alerts[0].alert_type == "cpu"
    assert alerts[0].level == "CRITICAL"
    assert alerts[0].value == 94.5
    assert "CPU đang hoạt động quá tải ở mức 94.5%" in alerts[0].message
    tts_mock.assert_called_once_with(alerts[0].message)
    overlay_mock.assert_called_once()


def test_health_monitor_ram_threshold_breach():
    """Verify RAM > 85.0% triggers alert."""
    provider = MockTelemetryProvider(ram=88.2)
    tts_mock = MagicMock()
    monitor = SystemHealthMonitor(
        telemetry_provider=provider,
        tts_callback=tts_mock,
        ram_threshold=85.0,
        enabled=True,
    )

    alerts = monitor.check_telemetry(now=1000.0)
    assert len(alerts) == 1
    assert alerts[0].alert_type == "ram"
    assert "Bộ nhớ RAM đang sử dụng 88.2%" in alerts[0].message


def test_health_monitor_disk_free_threshold_breach():
    """Verify Disk Free < 10.0 GB triggers warning."""
    provider = MockTelemetryProvider(disk_free_gb=6.4, disk_drive="C:")
    tts_mock = MagicMock()
    monitor = SystemHealthMonitor(
        telemetry_provider=provider,
        tts_callback=tts_mock,
        disk_min_free_gb=10.0,
        enabled=True,
    )

    alerts = monitor.check_telemetry(now=1000.0)
    assert len(alerts) == 1
    assert alerts[0].alert_type == "disk"
    assert "Dung lượng ổ đĩa C: chỉ còn 6.4 GB" in alerts[0].message


def test_health_monitor_cpu_temperature_breach():
    """Verify CPU Temp > 85.0°C triggers alert."""
    provider = MockTelemetryProvider(cpu_temp=89.0)
    tts_mock = MagicMock()
    monitor = SystemHealthMonitor(
        telemetry_provider=provider,
        tts_callback=tts_mock,
        temp_threshold_c=85.0,
        enabled=True,
    )

    alerts = monitor.check_telemetry(now=1000.0)
    assert len(alerts) == 1
    assert alerts[0].alert_type == "cpu_temp"
    assert "Nhiệt độ CPU đạt 89.0°C" in alerts[0].message


def test_health_monitor_battery_low_unplugged():
    """Verify Battery < 20% when unplugged triggers warning, but not when plugged in."""
    # Unplugged & low -> alert
    provider = MockTelemetryProvider(battery=15.0, battery_plugged=False)
    tts_mock = MagicMock()
    monitor = SystemHealthMonitor(
        telemetry_provider=provider,
        tts_callback=tts_mock,
        battery_min_percent=20.0,
        enabled=True,
    )

    alerts = monitor.check_telemetry(now=1000.0)
    assert len(alerts) == 1
    assert alerts[0].alert_type == "battery"
    assert "pin thiết bị còn 15%" in alerts[0].message

    # Reset cooldowns & plug in -> no alert even if 15%
    monitor.reset_cooldowns()
    provider.battery_plugged = True
    alerts_plugged = monitor.check_telemetry(now=1001.0)
    assert len(alerts_plugged) == 0


def test_health_monitor_cooldown_debouncing():
    """Verify alerts of same type are debounced within cooldown_seconds."""
    provider = MockTelemetryProvider(cpu=95.0)
    tts_mock = MagicMock()
    monitor = SystemHealthMonitor(
        telemetry_provider=provider,
        tts_callback=tts_mock,
        cooldown_seconds=60.0,
        enabled=True,
    )

    # First check at t=1000s -> triggers
    alerts_1 = monitor.check_telemetry(now=1000.0)
    assert len(alerts_1) == 1

    # Second check at t=1030s (30s later < 60s cooldown) -> suppressed
    alerts_2 = monitor.check_telemetry(now=1030.0)
    assert len(alerts_2) == 0

    # Third check at t=1065s (65s later > 60s cooldown) -> triggers again
    alerts_3 = monitor.check_telemetry(now=1065.0)
    assert len(alerts_3) == 1


def test_health_monitor_hysteresis():
    """Verify alert state resets only when metric drops below threshold - hysteresis."""
    provider = MockTelemetryProvider(cpu=92.0)
    monitor = SystemHealthMonitor(
        telemetry_provider=provider,
        cpu_threshold=90.0,
        hysteresis_delta=5.0,
        cooldown_seconds=10.0,
        enabled=True,
    )

    # 1. Breach at 92.0%
    monitor.check_telemetry(now=1000.0)
    assert monitor._active_alert_states["cpu"] is True

    # 2. Drops to 88.0% (below 90, but still above 90-5=85%) -> state remains True
    provider.cpu_percent = 88.0
    monitor.check_telemetry(now=1020.0)
    assert monitor._active_alert_states["cpu"] is True

    # 3. Drops to 84.0% (below 85%) -> state resets to False
    provider.cpu_percent = 84.0
    monitor.check_telemetry(now=1040.0)
    assert monitor._active_alert_states["cpu"] is False


def test_health_monitor_thread_lifecycle():
    """Verify background telemetry polling loop starts and stops."""
    monitor = SystemHealthMonitor(check_interval_seconds=0.02, enabled=True)
    assert monitor.is_running() is False
    monitor.start()
    assert monitor.is_running() is True
    time.sleep(0.05)
    monitor.stop()
    assert monitor.is_running() is False


# ============================================================================
# 3. POMODORO FOCUS MODE TESTS
# ============================================================================

def test_pomodoro_start_and_status():
    """Verify starting Pomodoro initializes WORK state and suppression."""
    tts_mock = MagicMock()
    overlay_mock = MagicMock()
    pomodoro = PomodoroTimer(
        tts_callback=tts_mock,
        overlay_callback=overlay_mock,
        enabled=True,
    )

    msg = pomodoro.start(work_minutes=25, break_minutes=5, cycles=2)
    assert "Bắt đầu phiên tập trung 25 phút" in msg
    tts_mock.assert_called_with("Bắt đầu phiên tập trung 25 phút")
    overlay_mock.assert_called_with("🎯 Chế độ tập trung", "Bắt đầu phiên tập trung 25 phút")

    status = pomodoro.get_status()
    assert status.state == PomodoroState.WORK
    assert status.current_cycle == 1
    assert status.total_cycles == 2
    assert status.work_minutes == 25.0
    assert status.break_minutes == 5.0
    assert pomodoro.is_suppressing_notifications() is True
    assert pomodoro.should_suppress_notification(is_critical=False) is True
    assert pomodoro.should_suppress_notification(is_critical=True) is False

    pomodoro.stop()


def test_pomodoro_full_cycle_transitions():
    """Verify state transitions: WORK -> BREAK -> WORK (Cycle 2) -> COMPLETED."""
    tts_mock = MagicMock()
    pomodoro = PomodoroTimer(tts_callback=tts_mock, enabled=True)
    base_t = 1000.0

    with patch("time.time", return_value=base_t):
        pomodoro.start(work_minutes=25, break_minutes=5, cycles=2)

    # 1. During Work Phase (e.g. 10m in) -> Still WORK
    event = pomodoro.tick(now=base_t + 600.0)
    assert event is None
    assert pomodoro.get_status().state == PomodoroState.WORK
    assert pomodoro.is_suppressing_notifications() is True

    # 2. Work Phase Completes (25m = 1500s) -> Transitions to BREAK
    event_1 = pomodoro.tick(now=base_t + 1501.0)
    assert event_1 == "WORK_FINISHED"
    assert pomodoro.get_status().state == PomodoroState.BREAK
    assert pomodoro.is_suppressing_notifications() is False
    tts_mock.assert_called_with("Đã hết 25 phút, Ngài hãy nghỉ ngơi 5 phút")

    # 3. Break Phase Completes (5m = 300s -> total 1801s) -> Transitions to WORK Cycle 2
    event_2 = pomodoro.tick(now=base_t + 1802.0)
    assert event_2 == "BREAK_FINISHED"
    assert pomodoro.get_status().state == PomodoroState.WORK
    assert pomodoro.get_status().current_cycle == 2
    assert pomodoro.is_suppressing_notifications() is True
    tts_mock.assert_called_with("Thời gian nghỉ kết thúc. Bắt đầu phiên tập trung tiếp theo 25 phút.")

    # 4. Work Cycle 2 Completes (another 25m = 1500s -> total 3302s) -> Transitions to BREAK
    event_3 = pomodoro.tick(now=base_t + 3303.0)
    assert event_3 == "WORK_FINISHED"
    assert pomodoro.get_status().state == PomodoroState.BREAK

    # 5. Break Cycle 2 Completes (another 5m = 300s -> total 3603s) -> Transitions to COMPLETED
    event_4 = pomodoro.tick(now=base_t + 3604.0)
    assert event_4 == "COMPLETED"
    assert pomodoro.get_status().state == PomodoroState.COMPLETED
    assert pomodoro.is_suppressing_notifications() is False
    tts_mock.assert_called_with("Đã hoàn thành toàn bộ chu kỳ tập trung. Chúc mừng Ngài.")


def test_pomodoro_pause_resume_stop():
    """Verify pause preserves remaining time and resume restores state."""
    pomodoro = PomodoroTimer(enabled=True)
    base_t = 1000.0

    with patch("time.time", return_value=base_t):
        pomodoro.start(work_minutes=25, break_minutes=5)

    # 10 minutes elapsed (600s), 15m remaining (900s)
    with patch("time.time", return_value=base_t + 600.0):
        assert pomodoro.pause() is True
        assert pomodoro.get_status().state == PomodoroState.PAUSED
        assert round(pomodoro.get_status().time_remaining_seconds) == 900
        # Notification suppression is lifted when paused
        assert pomodoro.is_suppressing_notifications() is False

    # User stays paused for 30 minutes (1800s)
    with patch("time.time", return_value=base_t + 2400.0):
        assert pomodoro.resume() is True
        assert pomodoro.get_status().state == PomodoroState.WORK
        # Remaining time should STILL be 900s (15m)
        assert round(pomodoro.get_status().time_remaining_seconds) == 900
        assert pomodoro.is_suppressing_notifications() is True

    # Stop resets to IDLE
    assert pomodoro.stop() is True
    assert pomodoro.get_status().state == PomodoroState.IDLE
    assert pomodoro.is_suppressing_notifications() is False


# ============================================================================
# 4. DAILY BRIEFING SCHEDULER TESTS
# ============================================================================

def test_daily_briefing_scheduler_time_trigger():
    """Verify scheduler triggers when target time (08:00) is reached for the day."""
    mock_hub = MagicMock()
    mock_hub.generate_morning_briefing.return_value = {
        "spoken_summary": "Chào buổi sáng thưa Ngài. Hôm nay trời đẹp.",
        "overlay_bullets": ["🌤️ Hà Nội: 28°C", "💰 BTC: $65,000"],
    }
    tts_mock = MagicMock()
    overlay_mock = MagicMock()

    scheduler = DailyBriefingScheduler(
        web_hub=mock_hub,
        tts_callback=tts_mock,
        overlay_callback=overlay_mock,
        target_time="08:00",
        enabled=True,
    )

    # 1. 07:45 AM -> Not due
    dt_before = datetime.datetime(2026, 8, 24, 7, 45, 0)
    assert scheduler.check_schedule(dt_before) is False
    res_before = scheduler.tick(current_dt=dt_before)
    assert res_before is None
    tts_mock.assert_not_called()

    # 2. 08:00 AM -> Due and triggers
    dt_due = datetime.datetime(2026, 8, 24, 8, 0, 0)
    assert scheduler.check_schedule(dt_due) is True
    res_due = scheduler.tick(current_dt=dt_due)
    assert res_due is not None
    assert "spoken_summary" in res_due
    tts_mock.assert_called_once_with("Chào buổi sáng thưa Ngài. Hôm nay trời đẹp.")
    overlay_mock.assert_called_once()

    # 3. 08:05 AM on the same date -> Already ran today, does not duplicate
    dt_after = datetime.datetime(2026, 8, 24, 8, 5, 0)
    assert scheduler.check_schedule(dt_after) is False
    assert scheduler.tick(current_dt=dt_after) is None

    # 4. Next day at 08:00 AM -> Due again
    dt_next_day = datetime.datetime(2026, 8, 25, 8, 0, 0)
    assert scheduler.check_schedule(dt_next_day) is True


def test_daily_briefing_scheduler_on_demand_trigger():
    """Verify trigger_now generates briefing immediately."""
    def custom_briefing_provider(city=None):
        return {
            "spoken_summary": f"Bản tin theo yêu cầu cho {city or 'mặc định'}.",
            "overlay_bullets": ["Test bullet"],
        }

    tts_mock = MagicMock()
    scheduler = DailyBriefingScheduler(
        briefing_provider=custom_briefing_provider,
        tts_callback=tts_mock,
        enabled=True,
    )

    result = scheduler.trigger_now(city="Đà Nẵng")
    assert "Đà Nẵng" in result["spoken_summary"]
    tts_mock.assert_called_once_with("Bản tin theo yêu cầu cho Đà Nẵng.")


def test_daily_briefing_scheduler_fallback_when_offline():
    """Verify graceful fallback speech when briefing provider raises exception."""
    mock_hub = MagicMock()
    mock_hub.generate_morning_briefing.side_effect = ConnectionError("No internet")

    tts_mock = MagicMock()
    scheduler = DailyBriefingScheduler(
        web_hub=mock_hub,
        tts_callback=tts_mock,
        enabled=True,
    )

    result = scheduler.trigger_now()
    assert "error" in result
    assert "gặp sự cố" in result["spoken_summary"]
    tts_mock.assert_called_once()


# ============================================================================
# 5. INACTIVITY MONITOR TESTS
# ============================================================================

def test_inactivity_monitor_trigger_after_2_hours():
    """Verify greeting triggers when idle > 7200s (2 hours)."""
    tts_mock = MagicMock()
    overlay_mock = MagicMock()
    monitor = InactivityMonitor(
        tts_callback=tts_mock,
        overlay_callback=overlay_mock,
        inactivity_threshold_seconds=7200.0,
        cooldown_seconds=3600.0,
        greeting_phrase="Thưa Ngài, Ngài có cần hỗ trợ gì không?",
        enabled=True,
    )
    base_t = 10000.0

    monitor.record_activity(now=base_t)
    assert monitor.get_idle_seconds(now=base_t + 100.0) == 100.0

    # 1 hour idle -> No trigger
    assert monitor.check_inactivity(now=base_t + 3600.0) is False
    tts_mock.assert_not_called()

    # 2 hours + 1 second idle -> Triggers check-in
    assert monitor.check_inactivity(now=base_t + 7201.0) is True
    tts_mock.assert_called_once_with("Thưa Ngài, Ngài có cần hỗ trợ gì không?")
    overlay_mock.assert_called_once_with("👋 Trợ lý JARVIS", "Thưa Ngài, Ngài có cần hỗ trợ gì không?")


def test_inactivity_monitor_activity_reset():
    """Verify record_activity resets idle counter."""
    tts_mock = MagicMock()
    monitor = InactivityMonitor(
        tts_callback=tts_mock,
        inactivity_threshold_seconds=7200.0,
        enabled=True,
    )
    base_t = 10000.0
    monitor.record_activity(now=base_t)

    # 1.5 hours later, user speaks / clicks
    monitor.record_activity(now=base_t + 5400.0)

    # 1 hour after that (total 2.5h from base, but only 1h since reset) -> No trigger
    assert monitor.check_inactivity(now=base_t + 9000.0) is False
    tts_mock.assert_not_called()


def test_inactivity_monitor_cooldown():
    """Verify greeting does not repeat continuously once triggered."""
    tts_mock = MagicMock()
    monitor = InactivityMonitor(
        tts_callback=tts_mock,
        inactivity_threshold_seconds=7200.0,
        cooldown_seconds=3600.0,
        enabled=True,
    )
    base_t = 10000.0
    monitor.record_activity(now=base_t)

    # Triggers at 7201s
    assert monitor.check_inactivity(now=base_t + 7201.0) is True
    assert tts_mock.call_count == 1

    # Check 10s later (still idle > 7200s, but within 3600s cooldown) -> Suppressed
    assert monitor.check_inactivity(now=base_t + 7211.0) is False
    assert tts_mock.call_count == 1

    # Check 1 hour after first greeting (now=base_t + 7201 + 3601 = base_t + 10802s) -> Triggers again
    assert monitor.check_inactivity(now=base_t + 10803.0) is True
    assert tts_mock.call_count == 2


# ============================================================================
# 6. PROACTIVE ENGINE MASTER COORDINATOR TESTS
# ============================================================================

def test_proactive_engine_config_parsing():
    """Verify ProactiveConfig parses flat and nested configuration dictionaries."""
    nested_cfg = {
        "proactive": {
            "enabled": True,
            "reminders": {"enabled": True, "check_interval_s": 1.0},
            "health_monitor": {"enabled": True, "cpu_threshold": 95.0, "cooldown_s": 90.0},
            "focus_mode": {"enabled": False, "work_duration_m": 30, "break_duration_m": 10},
            "daily_briefing": {"enabled": True, "time": "07:30", "city": "TP. Hồ Chí Minh"},
            "inactivity_greeting": {"enabled": True, "timeout_seconds": 3600},
        }
    }

    config = ProactiveConfig.from_dict(nested_cfg)
    assert config.enabled is True
    assert config.reminders_enabled is True
    assert config.reminders_interval_s == 1.0
    assert config.cpu_threshold == 95.0
    assert config.health_cooldown_s == 90.0
    assert config.pomodoro_enabled is False
    assert config.pomodoro_work_m == 30.0
    assert config.daily_briefing_time == "07:30"
    assert config.daily_briefing_city == "TP. Hồ Chí Minh"
    assert config.inactivity_timeout_s == 3600.0


def test_proactive_engine_initialization_and_master_lifecycle():
    """Verify master engine lifecycle starts and stops all sub-services."""
    tts_mock = MagicMock()
    overlay_mock = MagicMock()

    engine = ProactiveEngine(
        config={"enabled": True},
        tts_callback=tts_mock,
        overlay_callback=overlay_mock,
    )

    assert engine.is_running() is False
    engine.start()
    assert engine.is_running() is True
    assert engine.reminders.is_running() is True
    assert engine.health_monitor.is_running() is True
    assert engine.briefing_scheduler.is_running() is True
    assert engine.inactivity.is_running() is True

    engine.stop()
    assert engine.is_running() is False
    assert engine.reminders.is_running() is False
    assert engine.health_monitor.is_running() is False
    assert engine.briefing_scheduler.is_running() is False
    assert engine.inactivity.is_running() is False


def test_proactive_engine_feature_toggles():
    """Verify individual sub-features can be selectively disabled."""
    engine = ProactiveEngine(
        config={
            "enabled": True,
            "reminders_enabled": False,
            "health_monitor_enabled": True,
            "pomodoro_enabled": False,
            "daily_briefing_enabled": False,
            "inactivity_greeting_enabled": True,
        }
    )

    assert engine.reminders.enabled is False
    assert engine.health_monitor.enabled is True
    assert engine.pomodoro.enabled is False
    assert engine.briefing_scheduler.enabled is False
    assert engine.inactivity.enabled is True

    engine.start()
    assert engine.reminders.is_running() is False
    assert engine.health_monitor.is_running() is True
    assert engine.briefing_scheduler.is_running() is False
    assert engine.inactivity.is_running() is True
    engine.stop()


def test_proactive_engine_master_toggle_disabled():
    """Verify when master enabled=False, starting the engine does not start sub-workers."""
    engine = ProactiveEngine(config={"enabled": False})
    engine.start()
    assert engine.is_running() is False
    assert engine.reminders.is_running() is False


def test_proactive_engine_delegated_apis():
    """Verify delegated helper methods on ProactiveEngine."""
    tts_mock = MagicMock()
    provider = MockTelemetryProvider(cpu=95.0)

    engine = ProactiveEngine(
        config={"enabled": True},
        tts_callback=tts_mock,
        telemetry_provider=provider,
    )

    # 1. Reminders delegation
    rid = engine.add_reminder("Test reminder", delay_seconds=60.0)
    assert isinstance(rid, str)
    pending = engine.get_pending_reminders()
    assert len(pending) == 1
    assert engine.cancel_reminder(rid) is True
    assert len(engine.get_pending_reminders()) == 0

    # 2. Pomodoro delegation
    msg = engine.start_pomodoro(work_minutes=25, break_minutes=5)
    assert "25 phút" in msg
    assert engine.is_suppressing_notifications() is True
    status = engine.get_pomodoro_status()
    assert status["state"] == "WORK"
    assert engine.pause_pomodoro() is True
    assert engine.resume_pomodoro() is True
    assert engine.stop_pomodoro() is True
    assert engine.is_suppressing_notifications() is False

    # 3. Health check delegation
    alerts = engine.check_health_now()
    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "cpu"

    # 4. Inactivity delegation
    engine.record_user_activity()
    assert engine.inactivity.get_idle_seconds() < 1.0


def test_proactive_engine_unified_tick():
    """Verify synchronous tick step across all sub-engines."""
    provider = MockTelemetryProvider(ram=92.0)
    tts_mock = MagicMock()

    engine = ProactiveEngine(
        config={"enabled": True},
        tts_callback=tts_mock,
        telemetry_provider=provider,
    )
    base_t = 1000.0

    # Schedule reminder due at base_t + 10s
    engine.reminders.add_scheduled_reminder("Take a break", trigger_timestamp=base_t + 10.0)

    # Synchronous tick at base_t + 15s
    tick_res = engine.tick(
        now=base_t + 15.0,
        current_dt=datetime.datetime(2026, 8, 24, 12, 0, 0),
    )

    assert len(tick_res["reminders_executed"]) == 1
    assert tick_res["reminders_executed"][0]["text"] == "Take a break"
    assert len(tick_res["health_alerts"]) == 1
    assert tick_res["health_alerts"][0]["alert_type"] == "ram"


# ============================================================================
# 7. ADVANCED EDGE CASES, CONCURRENCY & INTEGRATION TESTS
# ============================================================================

def test_reminder_scheduler_clear():
    """Verify clear empties all queues and lookup tables."""
    scheduler = ReminderScheduler(enabled=True)
    scheduler.add_scheduled_reminder("Task 1", 100.0)
    scheduler.add_scheduled_reminder("Task 2", 200.0)
    assert len(scheduler.get_pending_reminders()) == 2
    scheduler.clear()
    assert len(scheduler.get_pending_reminders()) == 0
    assert scheduler.get_reminder("any") is None


def test_reminder_scheduler_concurrent_adds():
    """Verify thread-safe concurrent scheduling of reminders."""
    scheduler = ReminderScheduler(enabled=True)
    num_threads = 10
    reminders_per_thread = 20

    def worker(thread_idx: int):
        for i in range(reminders_per_thread):
            scheduler.add_scheduled_reminder(
                text=f"Thread-{thread_idx} Task-{i}",
                trigger_timestamp=1000.0 + (thread_idx * 10) + i,
            )

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    pending = scheduler.get_pending_reminders()
    assert len(pending) == num_threads * reminders_per_thread
    # Ensure ordered by trigger_timestamp
    timestamps = [p["trigger_timestamp"] for p in pending]
    assert timestamps == sorted(timestamps)


def test_health_monitor_multiple_simultaneous_breaches():
    """Verify all breached thresholds are reported when multiple metrics fail at once."""
    provider = MockTelemetryProvider(
        cpu=96.0,
        ram=90.0,
        disk_free_gb=4.5,
        cpu_temp=92.0,
        battery=10.0,
        battery_plugged=False,
    )
    monitor = SystemHealthMonitor(telemetry_provider=provider, enabled=True)
    alerts = monitor.check_telemetry(now=1000.0)

    alert_types = {a.alert_type for a in alerts}
    assert alert_types == {"cpu", "ram", "disk", "cpu_temp", "battery"}
    assert len(alerts) == 5


def test_health_monitor_hardware_monitor_duck_typing():
    """Verify SystemHealthMonitor works with HardwareMonitor mock instance."""
    mock_hw = MagicMock()
    mock_metrics = MagicMock()
    mock_metrics.cpu_percent = 95.0
    mock_metrics.ram_percent = 70.0
    mock_metrics.cpu_temp_c = 75.0
    mock_metrics.disks = {
        "C:": MagicMock(free_bytes=50 * (1024 ** 3)),
    }
    mock_hw.get_metrics.return_value = mock_metrics

    monitor = SystemHealthMonitor(hardware_monitor=mock_hw, enabled=True)
    alerts = monitor.check_telemetry(now=1000.0)
    assert len(alerts) == 1
    assert alerts[0].alert_type == "cpu"


def test_pomodoro_edge_cases():
    """Verify edge cases in PomodoroTimer: double pause, double resume, idle stop."""
    pomodoro = PomodoroTimer(enabled=True)
    # Pause when idle -> False
    assert pomodoro.pause() is False
    # Resume when idle -> False
    assert pomodoro.resume() is False
    # Stop when idle -> False
    assert pomodoro.stop() is False

    # Disabled start
    pomodoro.enabled = False
    res = pomodoro.start()
    assert "vô hiệu hóa" in res


def test_daily_briefing_set_target_time_and_reset():
    """Verify dynamically updating target time and resetting daily flag."""
    scheduler = DailyBriefingScheduler(target_time="08:00", enabled=True)
    assert scheduler._target_hour == 8
    assert scheduler._target_minute == 0

    scheduler.set_target_time("06:30")
    assert scheduler._target_hour == 6
    assert scheduler._target_minute == 30

    # Test daily flag reset
    scheduler._last_briefing_date = "2026-08-24"
    dt = datetime.datetime(2026, 8, 24, 6, 35, 0)
    assert scheduler.check_schedule(dt) is False
    scheduler.reset_daily_flag()
    assert scheduler.check_schedule(dt) is True


def test_inactivity_monitor_reset():
    """Verify reset() restores last activity and greeting times."""
    monitor = InactivityMonitor(enabled=True)
    monitor._last_activity_time = 0.0
    monitor._last_greeting_time = 100.0
    monitor.reset()
    assert monitor._last_greeting_time == 0.0
    assert monitor.get_idle_seconds() < 1.0


def test_proactive_engine_app_context_auto_wiring():
    """Verify ProactiveEngine automatically wires callbacks from JarvisApp-like context."""
    mock_app = MagicMock()
    mock_app.tts_manager = MagicMock()
    mock_app.overlay = MagicMock()
    mock_app.web_hub = MagicMock()
    mock_app.hardware_monitor = MagicMock()

    engine = ProactiveEngine(app_context=mock_app, config={"enabled": True})
    assert engine.web_hub is mock_app.web_hub
    assert engine.hardware_monitor is mock_app.hardware_monitor

    # Test auto-wired TTS callback invocation
    engine._handle_tts_dispatch("Hello from proactive")
    mock_app.tts_manager.speak.assert_called_once_with("Hello from proactive", wait=False)

    # Test auto-wired Overlay callback invocation
    engine.overlay_callback("Title", "Body")
    mock_app.overlay.show_response.assert_called_once_with("Title", "Body")


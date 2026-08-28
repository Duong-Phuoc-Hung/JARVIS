"""
tests/unit/test_notification_hub.py
======================================
Unit tests for NotificationHub (mock mode).
"""
from __future__ import annotations

import pytest

from jarvis.workers.notification_hub import Channel, Notification, NotificationHub, Priority


@pytest.fixture
def hub():
    return NotificationHub(is_mock=True)


class TestNotify:
    def test_notify_returns_notification(self, hub):
        notif = hub.notify("Test message", "Test Title")
        assert isinstance(notif, Notification)

    def test_notify_success_mock(self, hub):
        notif = hub.notify("Hello JARVIS", channels=["toast"])
        assert notif.success is True

    def test_notify_all_channels(self, hub):
        notif = hub.notify("Broadcast!", channels=["all"])
        assert notif.success is True

    def test_notify_logged_to_history(self, hub):
        hub.notify("Msg 1")
        hub.notify("Msg 2")
        assert hub.count == 2

    def test_get_history_returns_list(self, hub):
        hub.notify("Test")
        history = hub.get_history()
        assert isinstance(history, list)
        assert len(history) >= 1
        assert "message" in history[0]

    def test_high_priority_notification(self, hub):
        notif = hub.notify("URGENT!", priority=Priority.URGENT)
        assert notif.priority == Priority.URGENT


class TestScheduling:
    def test_schedule_returns_scheduled_notif(self, hub):
        sn = hub.schedule("Họp lúc 3h", at="15:00", title="Reminder")
        assert sn is not None
        assert sn.trigger_time == "15:00"

    def test_schedule_listed(self, hub):
        hub.schedule("Test", at="09:00")
        schedules = hub.list_schedules()
        assert len(schedules) >= 1

    def test_cancel_schedule(self, hub):
        sn = hub.schedule("Cancel me", at="23:59")
        result = hub.cancel_schedule(sn.notif_id)
        assert result is True
        # Should not appear in active list
        active = [s for s in hub.list_schedules() if s["id"] == sn.notif_id]
        assert active == []

    def test_cancel_nonexistent_returns_false(self, hub):
        result = hub.cancel_schedule("nonexistent_id")
        assert result is False

    def test_parse_time_hhmm(self, hub):
        import datetime
        now = datetime.datetime.now()
        t = hub._parse_trigger_time("15:30", now)
        assert t is not None
        assert t.hour == 15
        assert t.minute == 30


class TestAlertRules:
    def test_add_rule_registers(self, hub):
        hub.add_rule("CPU > 90%", "high_cpu", check_fn=lambda: False)
        assert len(hub._rules) == 1

    def test_remove_rule(self, hub):
        hub.add_rule("test_cond", "test_rule", check_fn=lambda: False)
        result = hub.remove_rule("test_rule")
        assert result is True

    def test_rule_with_true_fires(self, hub):
        fired = []
        def check():
            fired.append(True)
            return True
        hub.add_rule("Always fires", "always", check_fn=check)
        hub._check_rules()
        assert len(fired) >= 1

    def test_rule_with_false_does_not_fire(self, hub):
        hub.notify_count_before = hub.count
        hub.add_rule("Never fires", "never", check_fn=lambda: False, message="Should not send")
        hub._check_rules()
        # count stays the same
        assert hub.count == hub.notify_count_before


class TestLifecycle:
    def test_start_stop(self, hub):
        hub.start()
        assert hub._running is True
        hub.stop()
        assert hub._running is False

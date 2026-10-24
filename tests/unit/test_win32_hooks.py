"""
tests/unit/test_win32_hooks.py
==============================
Unit test suite for Event-Driven Win32 Proactive Co-Pilot (EWPCP).
Validates zero-polling OS event interception, process filtering,
cooldown debouncing, and callback lifecycle in Argon Frontier 10.0.
"""
import re
import time
from typing import Any

import pytest

from jarvis.proactive.win32_hooks import (
    DEFAULT_PROACTIVE_RULES,
    ProactiveRule,
    ProactiveSystemEvent,
    Win32EventHookCoPilot,
)


class TestWin32EventHookCoPilot:
    """Comprehensive test harness for Win32EventHookCoPilot."""

    def test_win32_hooks_initialization_and_default_rules(self) -> None:
        """Verifies default rule registration and initial state."""
        copilot = Win32EventHookCoPilot()
        assert len(copilot.rules) >= 4

        rule_ids = [r.rule_id for r in copilot.rules]
        assert "terminal_build_failed" in rule_ids
        assert "terminal_build_succeeded" in rule_ids
        assert "browser_download_complete" in rule_ids
        assert "battery_critical" in rule_ids

    def test_win32_hooks_rule_matching_and_process_filter(self) -> None:
        """Verifies regex pattern matching against window titles with process name isolation."""
        copilot = Win32EventHookCoPilot()

        matched_events: list[tuple[ProactiveSystemEvent, ProactiveRule]] = []

        def on_event(ev: ProactiveSystemEvent, r: ProactiveRule) -> None:
            matched_events.append((ev, r))

        copilot.event_callback = on_event

        # 1. Event from terminal with compilation error -> SHOULD TRIGGER
        ev1 = copilot.inject_simulated_event(
            event_id=0x800C,
            event_name="EVENT_OBJECT_NAMECHANGE",
            hwnd=12345,
            window_title="Administrator: Windows PowerShell - npm run build: Failed with 2 errors",
            process_name="WindowsTerminal.exe",
        )

        assert len(matched_events) == 1
        assert matched_events[0][1].rule_id == "terminal_build_failed"
        assert matched_events[0][1].suggested_action == "open_build_log"

        # 2. Event with 'error' in title but from non-matching process (e.g. notepad.exe) -> SHOULD NOT TRIGGER
        ev2 = copilot.inject_simulated_event(
            event_id=0x800C,
            event_name="EVENT_OBJECT_NAMECHANGE",
            hwnd=54321,
            window_title="error_notes.txt - Notepad",
            process_name="notepad.exe",
        )

        # Matched count remains 1
        assert len(matched_events) == 1

    def test_win32_hooks_cooldown_throttling(self) -> None:
        """Verifies debounce cooldown prevents duplicate alerts during burst title updates."""
        rule = ProactiveRule(
            rule_id="test_quick_alert",
            name_pattern=re.compile(r"burst_event", re.IGNORECASE),
            process_filter=None,
            cooldown_s=10.0,
            suggested_action="test_action",
            voice_notification_template="Thông báo kiểm thử",
        )
        copilot = Win32EventHookCoPilot(rules=[rule])

        triggered_rules: list[str] = []
        copilot.event_callback = lambda ev, r: triggered_rules.append(r.rule_id)

        # Event 1: First occurrence -> Triggers
        copilot.inject_simulated_event(1, "TEST", 100, "burst_event initial", "test.exe")
        assert len(triggered_rules) == 1

        # Event 2: Immediate rapid update (same rule) -> Throttled by cooldown
        copilot.inject_simulated_event(2, "TEST", 100, "burst_event update 2", "test.exe")
        assert len(triggered_rules) == 1

        # Simulate time passage beyond cooldown
        rule.last_triggered_s -= 15.0

        # Event 3: After cooldown elapsed -> Triggers again
        copilot.inject_simulated_event(3, "TEST", 100, "burst_event update 3", "test.exe")
        assert len(triggered_rules) == 2

    def test_win32_hooks_browser_download_rule(self) -> None:
        """Verifies browser download completion detection."""
        copilot = Win32EventHookCoPilot()
        notifications: list[str] = []
        copilot.event_callback = lambda ev, r: notifications.append(r.suggested_action)

        copilot.inject_simulated_event(
            event_id=0x800C,
            event_name="EVENT_OBJECT_NAMECHANGE",
            hwnd=9999,
            window_title="Downloading release.zip - 100% Download complete - Google Chrome",
            process_name="chrome.exe",
        )

        assert len(notifications) == 1
        assert notifications[0] == "open_downloads_folder"

    def test_win32_hooks_lifecycle_start_stop(self) -> None:
        """Verifies safe startup, thread lifecycle, and shutdown without leaks."""
        copilot = Win32EventHookCoPilot()
        assert copilot.is_running is False

        ok = copilot.start()
        assert ok is True
        assert copilot.is_running is True

        copilot.stop()
        assert copilot.is_running is False

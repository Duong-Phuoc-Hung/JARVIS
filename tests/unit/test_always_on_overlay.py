"""
tests/unit/test_always_on_overlay.py
====================================
Comprehensive unit test suite for Always-On Intelligent Overlay HUD (R8 / Milestone 6).
Covers:
  - Overlay state machine transitions (IDLE, LISTENING, THINKING, RESPONSE, HIDDEN).
  - Sidebar mode docking, 380px expand, and 40px ribbon collapse mechanics.
  - Floating Arc Reactor icon minimize and restore toggles.
  - 5-Turn conversation history queue (up to 5 turns tracking, FIFO eviction, formatting).
  - Interactive quick action buttons and custom callback dispatchers.
  - Persistent memory facts preview updates (top 3 facts).
  - Real-time hardware status bar telemetry updates (CPU %, RAM %, Battery %, AC charging).
  - 11-Bar audio waveform spectrum analyzer updates (RMS float & list-based levels).
  - Headless resilience, thread-safety, and concurrent multithreaded operations.
"""
from __future__ import annotations

import concurrent.futures
import ctypes
import time
from ctypes import wintypes
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from jarvis.ui.overlay import (
    BREATHING_GRADIENT,
    COLORS,
    FONT_FAMILY,
    AlwaysOnOverlay,
    JarvisOverlay,
    OverlayMode,
    OverlayState,
    TurnRecord,
    _safe_probe_battery,
    _safe_probe_cpu_ram,
    _valid_battery_percent,
)


class _MirrorSystemPowerStatus(ctypes.Structure):
    """
    Layout-identical mirror of the SYSTEM_POWER_STATUS struct defined inside
    _safe_probe_battery(), used to poke values into the real struct instance
    via the pointer a mocked GetSystemPowerStatus receives.
    """
    _fields_ = [
        ("ACLineStatus", wintypes.BYTE),
        ("BatteryFlag", wintypes.BYTE),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", wintypes.BYTE),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


def _make_gsps_side_effect(battery_life_percent: int, ac_line_status: int = 0, battery_flag: int = 0):
    """Builds a GetSystemPowerStatus side_effect that fills in the struct behind the pointer it receives."""
    def _side_effect(sps_ptr):
        real = ctypes.cast(sps_ptr, ctypes.POINTER(_MirrorSystemPowerStatus)).contents
        real.ACLineStatus = ac_line_status
        real.BatteryFlag = battery_flag
        real.BatteryLifePercent = battery_life_percent
        real.SystemStatusFlag = 0
        return 1
    return _side_effect


def test_overlay_constants_and_dataclasses():
    """Verify state enums, mode enums, TurnRecord dataclass, and color palettes."""
    assert OverlayState.IDLE.value == "idle"
    assert OverlayState.LISTENING.value == "listening"
    assert OverlayState.THINKING.value == "thinking"
    assert OverlayState.RESPONSE.value == "response"
    assert OverlayState.HIDDEN.value == "hidden"

    assert OverlayMode.SIDEBAR.value == "sidebar"
    assert OverlayMode.POPUP.value == "popup"
    assert OverlayMode.ARC_REACTOR.value == "arc_reactor"

    # TurnRecord verification
    record = TurnRecord(
        user_text="Thời tiết hôm nay",
        jarvis_text="Hà Nội 28°C",
        action="weather_query",
    )
    d = record.to_dict()
    assert d["user_text"] == "Thời tiết hôm nay"
    assert d["jarvis_text"] == "Hà Nội 28°C"
    assert d["action"] == "weather_query"
    assert isinstance(d["timestamp"], float)

    # Color palette
    assert "bg" in COLORS
    assert "border" in COLORS
    assert "bar_cyan" in COLORS
    assert "arc_core" in COLORS
    assert len(BREATHING_GRADIENT) == 10
    assert JarvisOverlay is AlwaysOnOverlay


def test_overlay_state_machine_full_lifecycle():
    """Verify complete state transitions in AlwaysOnOverlay."""
    overlay = AlwaysOnOverlay(headless=True, auto_hide_s=5.0)
    overlay.start()
    assert overlay.state == OverlayState.IDLE
    assert overlay.is_visible is False
    assert overlay.is_headless is True

    # 1. LISTENING
    overlay.show_listening("🎤 Tôi đang lắng nghe...")
    assert overlay.state == OverlayState.LISTENING
    assert overlay.is_visible is True
    assert "lắng nghe" in overlay.user_text
    assert overlay.status_text == "Đang lắng nghe giọng nói"

    # 2. THINKING
    overlay.show_thinking("kiểm tra tình trạng hệ thống")
    assert overlay.state == OverlayState.THINKING
    assert overlay.is_visible is True
    assert overlay.user_text == "kiểm tra tình trạng hệ thống"
    assert "Đang xử lý" in overlay.jarvis_text
    assert "suy nghĩ" in overlay.status_text

    # 3. RESPONSE
    overlay.show_response(
        transcript="kiểm tra tình trạng hệ thống",
        response="Hệ thống hoạt động tối ưu. CPU 15%, RAM 40%.",
        hint="💡 Double clap để hỏi tiếp",
    )
    assert overlay.state == OverlayState.RESPONSE
    assert overlay.is_visible is True
    assert overlay.jarvis_text == "Hệ thống hoạt động tối ưu. CPU 15%, RAM 40%."
    assert overlay.hint_text == "💡 Double clap để hỏi tiếp"
    assert overlay.status_text == "Hoàn thành"

    # 4. HIDDEN
    overlay.hide()
    assert overlay.state == OverlayState.HIDDEN
    assert overlay.is_visible is False
    assert overlay.hint_text == ""
    assert overlay.status_text == "Sẵn sàng"

    overlay.destroy()


def test_sidebar_mode_docking_and_ribbon_collapse():
    """Verify Sidebar mode docking, 380px expand, and 40px ribbon collapse."""
    overlay = AlwaysOnOverlay(headless=True, sidebar_mode=True, sidebar_width=380, collapsed_width=40)
    overlay.start()

    assert overlay.is_sidebar_mode is True
    assert overlay.mode == OverlayMode.SIDEBAR
    assert overlay.is_collapsed is False

    # Collapse to 40px ribbon
    overlay.collapse_sidebar()
    assert overlay.is_collapsed is True

    # Expand back to 380px
    overlay.expand_sidebar()
    assert overlay.is_collapsed is False

    # Toggle collapse
    overlay.toggle_collapse()
    assert overlay.is_collapsed is True
    overlay.toggle_collapse()
    assert overlay.is_collapsed is False

    # Toggle sidebar mode to popup and back
    overlay.toggle_sidebar()
    assert overlay.mode == OverlayMode.POPUP
    assert overlay.is_sidebar_mode is False

    overlay.toggle_sidebar()
    assert overlay.mode == OverlayMode.SIDEBAR
    assert overlay.is_sidebar_mode is True

    overlay.dock_to_right()
    assert overlay.is_sidebar_mode is True

    overlay.destroy()


def test_floating_arc_reactor_minimize_mode():
    """Verify minimize to floating Arc Reactor badge and restore."""
    overlay = AlwaysOnOverlay(headless=True)
    overlay.start()

    assert overlay.is_minimized is False

    # Minimize to Arc Reactor
    overlay.minimize_to_arc_reactor()
    assert overlay.is_minimized is True

    # Restore from Arc Reactor
    overlay.restore_from_arc_reactor()
    assert overlay.is_minimized is False

    # Toggle minimize
    overlay.toggle_minimize()
    assert overlay.is_minimized is True
    overlay.toggle_minimize()
    assert overlay.is_minimized is False

    overlay.destroy()


def test_conversation_history_queue_5_turns_limit():
    """Verify 5-turn history FIFO behavior and formatting."""
    overlay = AlwaysOnOverlay(headless=True)
    overlay.start()

    assert len(overlay.get_history()) == 0

    # Add 3 turns
    overlay.add_turn("Câu hỏi 1", "Trả lời 1")
    overlay.add_turn("Câu hỏi 2", "Trả lời 2")
    overlay.add_turn("Câu hỏi 3", "Trả lời 3")

    history = overlay.get_history()
    assert len(history) == 3
    assert history[0]["user_text"] == "Câu hỏi 1"
    assert history[2]["user_text"] == "Câu hỏi 3"

    # Add 4 more turns (total 7 added -> only last 5 retained)
    overlay.add_turn("Câu hỏi 4", "Trả lời 4")
    overlay.add_turn("Câu hỏi 5", "Trả lời 5")
    overlay.add_turn("Câu hỏi 6", "Trả lời 6")
    overlay.add_turn("Câu hỏi 7", "Trả lời 7")

    history = overlay.get_history()
    assert len(history) == 5
    assert history[0]["user_text"] == "Câu hỏi 3"
    assert history[-1]["user_text"] == "Câu hỏi 7"

    # Clear history
    overlay.clear_history()
    assert len(overlay.get_history()) == 0

    # Verify show_response automatically logs a turn
    overlay.show_response("thời tiết", "25 độ C")
    assert len(overlay.get_history()) == 1
    assert overlay.get_history()[0]["user_text"] == "thời tiết"
    assert overlay.get_history()[0]["jarvis_text"] == "25 độ C"

    overlay.destroy()


def test_quick_action_buttons_and_callbacks():
    """Verify quick action button dispatching and custom callback registration."""
    action_events: List[str] = []
    overlay = AlwaysOnOverlay(
        headless=True,
        on_action=lambda key: action_events.append(f"on_action:{key}"),
    )
    overlay.start()

    # Built-in quick actions
    res1 = overlay.trigger_quick_action("briefing_morning")
    assert res1 == "briefing_triggered"
    assert overlay.state == OverlayState.RESPONSE
    assert "Briefing Sáng" in overlay.user_text

    res2 = overlay.trigger_quick_action("system_status")
    assert res2 == "status_triggered"

    res3 = overlay.trigger_quick_action("focus_mode")
    assert res3 == "focus_triggered"

    # Register custom action callback
    custom_called = []
    overlay.register_action_callback("clean_ram", lambda: custom_called.append("ram_cleaned"))
    overlay.trigger_quick_action("clean_ram")
    assert custom_called == ["ram_cleaned"]

    # Fallback to on_action handler
    overlay.trigger_quick_action("custom_unknown_action")
    assert "on_action:custom_unknown_action" in action_events

    overlay.destroy()


def test_memory_facts_preview_updates():
    """Verify top 3 persistent memory facts preview widget."""
    overlay = AlwaysOnOverlay(headless=True)
    overlay.start()

    # Default facts
    default_facts = overlay.memory_facts
    assert len(default_facts) == 3
    assert "Hưng" in default_facts[0]

    # Update with new facts (more than 3 -> truncated to 3)
    new_facts = [
        "Chủ nhân: Hưng",
        "Dự án: JARVIS Personal AI",
        "Sở thích: Lập trình Python & AI",
        "Thành phố: Hà Nội",
    ]
    overlay.set_memory_facts(new_facts)
    updated = overlay.memory_facts
    assert len(updated) == 3
    assert updated[0] == "Chủ nhân: Hưng"
    assert updated[1] == "Dự án: JARVIS Personal AI"
    assert updated[2] == "Sở thích: Lập trình Python & AI"

    overlay.destroy()


def test_status_bar_telemetry_updates():
    """Verify real-time hardware telemetry updates (CPU, RAM, Battery)."""
    overlay = AlwaysOnOverlay(headless=True)
    overlay.start()

    summary = overlay.update_telemetry(
        cpu_percent=42.5,
        ram_percent=68.0,
        battery_percent=88,
        is_charging=True,
    )
    assert summary["cpu_percent"] == 42.5
    assert summary["ram_percent"] == 68.0
    assert summary["battery_percent"] == 88
    assert summary["is_charging"] is True

    assert overlay.cpu_percent == 42.5
    assert overlay.ram_percent == 68.0
    assert overlay.battery_percent == 88
    assert overlay.is_charging is True

    # Probe system metrics execution
    probed = overlay.probe_system_metrics()
    assert isinstance(probed, dict)
    assert "cpu_percent" in probed
    assert "ram_percent" in probed

    overlay.destroy()


def test_waveform_spectrum_analyzer_audio_level_updates():
    """Verify 11-bar waveform spectrum analyzer level updates and calculations."""
    overlay = AlwaysOnOverlay(headless=True)
    overlay.start()

    assert len(overlay.waveform_bars) == 11

    # 1. Update with scalar RMS amplitude (0.8)
    overlay.update_audio_level(0.8)
    bars = overlay.waveform_bars
    assert len(bars) == 11
    # Center bar should be highest due to bell-curve envelope
    assert bars[5] >= bars[0]
    assert all(0.0 <= b <= 1.0 for b in bars)

    # 2. Update with direct bar list
    custom_bars = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 0.5]
    overlay.update_audio_level(custom_bars)
    bars2 = overlay.waveform_bars
    assert bars2 == custom_bars

    overlay.destroy()


def test_safe_probe_functions():
    """Verify helper probe functions for battery and CPU/RAM."""
    cpu, ram = _safe_probe_cpu_ram()
    assert isinstance(cpu, (int, float))
    assert isinstance(ram, (int, float))
    assert 0.0 <= cpu <= 100.0
    assert 0.0 <= ram <= 100.0

    bat, charging = _safe_probe_battery()
    if bat is not None:
        assert 0 <= bat <= 100
    assert isinstance(charging, bool)


def test_safe_probe_battery_valid_percentage():
    """A valid 0..100 psutil reading passes through unchanged."""
    fake_batt = MagicMock(percent=42, power_plugged=True)
    with patch("ctypes.windll.kernel32.GetSystemPowerStatus", return_value=0), \
         patch("psutil.sensors_battery", return_value=fake_batt):
        bat, charging = _safe_probe_battery()
    assert bat == 42
    assert charging is True


def test_safe_probe_battery_invalid_sentinel_returns_none():
    """
    Regression test: on headless runners with no real battery, psutil can
    report a sentinel percentage (e.g. -1) instead of a real value.
    _safe_probe_battery() must reject it and return None, not the raw sentinel.
    """
    fake_batt = MagicMock(percent=-1, power_plugged=False)
    with patch("ctypes.windll.kernel32.GetSystemPowerStatus", return_value=0), \
         patch("psutil.sensors_battery", return_value=fake_batt):
        bat, charging = _safe_probe_battery()
    assert bat is None
    # Charging status is still preserved even though percent was invalid.
    assert charging is False


def test_safe_probe_battery_no_battery_present():
    """When psutil reports no battery at all, returns (None, False)."""
    with patch("ctypes.windll.kernel32.GetSystemPowerStatus", return_value=0), \
         patch("psutil.sensors_battery", return_value=None):
        bat, charging = _safe_probe_battery()
    assert bat is None
    assert charging is False


# ---------------------------------------------------------------------------
# _valid_battery_percent: pure validation logic, version-independent.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        (42, 42),        # ordinary valid reading
        (0, 0),          # lower boundary, valid
        (100, 100),      # upper boundary, valid
        (-1, None),      # Python < 3.12 signed-byte reading of Win32's 0xFF "unknown" sentinel
        (255, None),     # Python >= 3.12 unsigned-byte reading of the same 0xFF sentinel
        (101, None),     # any other out-of-range value must also be rejected
    ],
)
def test_valid_battery_percent(raw, expected):
    """Verify the 0..100 validation contract directly, independent of ctypes/Python version."""
    assert _valid_battery_percent(raw) == expected


# ---------------------------------------------------------------------------
# _safe_probe_battery(): Windows GetSystemPowerStatus path.
# ---------------------------------------------------------------------------

def test_safe_probe_battery_windows_api_valid_percentage():
    """A valid BatteryLifePercent from GetSystemPowerStatus passes through unchanged."""
    with patch(
        "ctypes.windll.kernel32.GetSystemPowerStatus",
        side_effect=_make_gsps_side_effect(battery_life_percent=42, ac_line_status=1),
    ):
        bat, charging = _safe_probe_battery()
    assert bat == 42
    assert charging is True


def test_safe_probe_battery_windows_api_unsigned_sentinel_255():
    """
    Regression test for the real Win32 "unknown battery" sentinel: BatteryLifePercent=0xFF (255).
    On Python >= 3.12, ctypes.wintypes.BYTE reads this as unsigned 255.
    Must be rejected as None, not returned as a bogus 255% reading.
    """
    with patch(
        "ctypes.windll.kernel32.GetSystemPowerStatus",
        side_effect=_make_gsps_side_effect(battery_life_percent=255, ac_line_status=0, battery_flag=8),
    ):
        bat, charging = _safe_probe_battery()
    assert bat is None
    # Charging state is still derived from ACLineStatus/BatteryFlag independently of pct validity.
    assert charging is True


def test_safe_probe_battery_windows_api_signed_sentinel_negative_one():
    """
    Regression test for the same 0xFF sentinel as read on Python < 3.12, where
    ctypes.wintypes.BYTE was signed c_byte and exposed it as -1 instead of 255.
    _valid_battery_percent() must reject -1 just as it rejects 255, so the
    contract holds regardless of Python version.
    """
    assert _valid_battery_percent(-1) is None


def test_overlay_single_arg_show_response():
    """Verify show_response with 1 argument (response only)."""
    overlay = AlwaysOnOverlay(headless=True)
    overlay.show_thinking("hôm nay là thứ mấy")
    overlay.show_response("Hôm nay là Thứ Hai, thưa Ngài.")
    assert overlay.state == OverlayState.RESPONSE
    assert overlay.jarvis_text == "Hôm nay là Thứ Hai, thưa Ngài."
    assert overlay.user_text == "hôm nay là thứ mấy"
    overlay.destroy()


def test_overlay_long_text_truncation():
    """Verify long text responses are gracefully truncated with ellipsis."""
    overlay = AlwaysOnOverlay(headless=True)
    long_resp = "A" * 300
    overlay.show_response("query", long_resp)
    assert len(overlay.jarvis_text) <= 240
    assert overlay.jarvis_text.endswith("...")
    overlay.destroy()


def test_overlay_on_close_callback_invoked():
    """Verify on_close callback is invoked when overlay is hidden."""
    closed = []
    overlay = AlwaysOnOverlay(headless=True, on_close=lambda: closed.append(True))
    overlay.show_listening()
    assert len(closed) == 0
    overlay.hide()
    assert len(closed) == 1
    overlay.destroy()


def test_overlay_multithreaded_stress_concurrency():
    """Stress test: 12 concurrent worker threads mutating overlay state simultaneously."""
    overlay = AlwaysOnOverlay(headless=True)
    overlay.start()
    errors: List[Exception] = []

    def _worker(worker_id: int):
        try:
            for i in range(15):
                overlay.show_listening(f"Worker {worker_id} Prompt {i}")
                overlay.update_audio_level(float(i % 10) / 10.0)
                overlay.show_thinking(f"Worker {worker_id} Query {i}")
                overlay.update_telemetry(cpu_percent=10.0 + i, ram_percent=30.0 + i)
                overlay.show_response(f"Worker {worker_id} Query {i}", f"Response {worker_id}-{i}")
                overlay.add_turn(f"W{worker_id}-U{i}", f"W{worker_id}-J{i}")
                if i % 3 == 0:
                    overlay.toggle_collapse()
                if i % 5 == 0:
                    overlay.hide()
        except Exception as e:
            errors.append(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        futures = [executor.submit(_worker, w) for w in range(12)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert len(errors) == 0
    overlay.destroy()

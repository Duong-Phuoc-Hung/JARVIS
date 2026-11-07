"""
tests/unit/test_mini_hud.py
===========================
Unit test suite for MiniAmbientHUD and HUDState.
Verifies thread lifecycle, headless execution safety, and state transitions.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from jarvis.ui.mini_hud import HUDState, MiniAmbientHUD


def test_mini_hud_headless_lifecycle():
    hud = MiniAmbientHUD(headless=True)
    assert hud.state == HUDState.IDLE
    assert "Sẵn sàng" in hud.status_text

    hud.start()
    assert hud._running is True

    # State transitions
    hud.set_state(HUDState.LISTENING)
    assert hud.state == HUDState.LISTENING
    assert "lắng nghe" in hud.status_text

    hud.set_state(HUDState.THINKING)
    assert hud.state == HUDState.THINKING
    assert "suy nghĩ" in hud.status_text

    hud.set_state(HUDState.SPEAKING)
    assert hud.state == HUDState.SPEAKING
    assert "phản hồi" in hud.status_text

    hud.set_state(HUDState.ALERT, text="Nhiệt độ CPU cao")
    assert hud.state == HUDState.ALERT
    assert hud.status_text == "Nhiệt độ CPU cao"

    hud.stop()
    assert hud._running is False


def test_mini_hud_callbacks():
    click_cb = MagicMock()
    briefing_cb = MagicMock()

    hud = MiniAmbientHUD(
        on_click_callback=click_cb,
        on_briefing_callback=briefing_cb,
        headless=True,
    )

    hud._drag_data["moved"] = 0
    hud._on_mouse_up(None)
    click_cb.assert_called_once()


def test_mini_hud_compact_toggle():
    hud = MiniAmbientHUD(headless=True)
    assert hud.is_compact is False

    hud.toggle_compact()
    assert hud.is_compact is True

    hud.toggle_compact()
    assert hud.is_compact is False


def test_mini_hud_audio_energy():
    hud = MiniAmbientHUD(headless=True)
    hud.feed_audio_energy(0.75)
    assert abs(hud._live_audio_level - 0.75) < 1e-4

    # Clamping tests
    hud.feed_audio_energy(-0.5)
    assert hud._live_audio_level == 0.0

    hud.feed_audio_energy(1.5)
    assert hud._live_audio_level == 1.0

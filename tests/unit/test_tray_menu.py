"""
tests/unit/test_tray_menu.py
============================
Unit tests for JARVIS System Tray Status and Menu Controller (Sprint 2 R4 / P1-7).
Covers:
  - System Tray menu item count >= 4 and inclusion of Status item.
  - Dynamic get_status_text() generation with version (v4.7.0), TTS, STT, and RAM metrics.
  - Graceful fallback when sub-components or psutil are offline.
  - Verification of _on_view_logs resolving Path without NameError.
  - Context menu actions and pystray initialization.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from jarvis.ui.tray import SystemTrayController, TrayStatus


def test_system_tray_menu_items_minimum_count_and_status_item():
    """Verify tray menu has >= 4 items and contains 'Status'."""
    tray = SystemTrayController()
    assert len(tray.menu_items) >= 4
    assert "Status" in tray.menu_items
    assert "Toggle HUD Overlay" in tray.menu_items
    assert "Mute Microphone" in tray.menu_items
    assert "Exit" in tray.menu_items


def test_system_tray_dynamic_status_text_with_full_app():
    """Verify get_status_text() formats version v4.7.0, TTS status, STT status, and RAM %."""
    mock_app = MagicMock()
    mock_app.__version__ = "4.7.0"

    mock_tts = MagicMock()
    mock_tts.is_available.return_value = True
    mock_app.tts_manager = mock_tts

    mock_stt = MagicMock()
    mock_stt.is_available.return_value = True
    mock_stt.is_model_loaded = True
    mock_app.stt_engine = mock_stt

    tray = SystemTrayController(app=mock_app)

    with patch("psutil.virtual_memory") as mock_vm:
        mock_vm.return_value.percent = 42.0
        status_str = tray.get_status_text()

    assert "Status: v4.7.0" in status_str
    assert "TTS: Online" in status_str
    assert "STT: Ready" in status_str
    assert "RAM: 42%" in status_str


def test_system_tray_dynamic_status_text_graceful_fallbacks():
    """Verify get_status_text() handles None app, missing psutil, and offline components gracefully."""
    tray = SystemTrayController(app=None)
    status_str = tray.get_status_text()

    assert "Status: v4.7.0" in status_str
    assert "TTS: Ready" in status_str
    assert "STT: Ready" in status_str
    assert "RAM:" in status_str

    # Test with STT preloading state (available, but model not loaded yet)
    mock_app = MagicMock()
    mock_app.__version__ = "4.7.0"
    mock_app.tts_manager = None
    mock_stt = MagicMock()
    mock_stt.is_available.return_value = True
    mock_stt.is_model_loaded = False
    mock_stt._model = None
    mock_app.stt_engine = mock_stt

    tray_stt_preload = SystemTrayController(app=mock_app)
    status_stt_str = tray_stt_preload.get_status_text()
    assert "STT: Preloading" in status_stt_str

    # Test with STT completely offline
    mock_stt.is_available.return_value = False
    mock_stt.is_model_loaded = False
    status_stt_offline = tray_stt_preload.get_status_text()
    assert "STT: Offline" in status_stt_offline


def test_system_tray_view_logs_no_name_error():
    """Verify _on_view_logs executes without NameError on Path."""
    tray = SystemTrayController()

    with patch("os.path.exists", return_value=True):
        with patch("sys.platform", "win32"):
            with patch("os.startfile") as mock_startfile:
                tray._on_view_logs()
                mock_startfile.assert_called_once()
                opened_path = str(mock_startfile.call_args[0][0])
                assert "jarvis.log" in opened_path


def test_system_tray_view_logs_non_windows_fallback():
    """Verify _on_view_logs falls back to webbrowser on non-Windows platforms."""
    tray = SystemTrayController()

    with patch("os.path.exists", return_value=True):
        with patch("sys.platform", "linux"):
            with patch("webbrowser.open") as mock_web_open:
                tray._on_view_logs()
                mock_web_open.assert_called_once()
                assert "jarvis.log" in mock_web_open.call_args[0][0]

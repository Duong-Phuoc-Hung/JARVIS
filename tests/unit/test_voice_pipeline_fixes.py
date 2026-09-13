"""
tests/unit/test_voice_pipeline_fixes.py
======================================
Seam-level regression tests for Voice Pipeline Audit Backlog:
  - H-01: 16kHz default recording sample rate for Whisper alignment.
  - H-02: Synchronized microphone input device between AudioEngine and record_audio.
  - H-03: Acoustic echo suppression and settling guard preventing self-audio contamination.
  - H-04: Ctrl+Shift+L PTT hotkey calling _start_voice_interaction without AttributeError.
  - H-08: Master volume and brightness fail-closed semantics when hardware returns None.
"""
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from jarvis.core.app import JarvisApp


@pytest.fixture
def mock_app():
    """Builds a lightweight JarvisApp instance with headless audio and mocks."""
    with patch("jarvis.core.app.ConfigManager"), \
         patch("jarvis.core.app.ActionDispatcher"), \
         patch("jarvis.core.app.EventBus"):
        app = JarvisApp.__new__(JarvisApp)
        app.config = {
            "audio.sample_rate": 16000,
            "stt.timeout_s": 0.3,
        }
        app.headless = False
        app.audio_engine = MagicMock()
        app.audio_engine._active_device_index = 3
        app.tts_manager = MagicMock()
        app.tts_manager.is_playing = False
        app.proactive_engine = MagicMock()
        app.overlay = MagicMock()
        app.tray_controller = MagicMock()
        app.stt_engine = MagicMock()
        app._voice_lock = MagicMock()
        app._voice_lock.__enter__.return_value = True
        app._voice_lock.__exit__.return_value = False
        app._is_voice_interacting = False
        app.computer_controller = MagicMock()
        app._mic_muted = False
        return app


def test_h01_record_audio_default_16khz(mock_app):
    """H-01: record_audio defaults to 16000 Hz if not overridden."""
    with patch("sounddevice.InputStream") as mock_stream:
        mock_instance = MagicMock()
        mock_instance.read.return_value = (np.zeros((100, 1), dtype=np.float32), False)
        mock_stream.return_value.__enter__.return_value = mock_instance

        arr = mock_app.record_audio(duration_s=0.3)
        assert isinstance(arr, np.ndarray)
        mock_stream.assert_called_once()
        _, kwargs = mock_stream.call_args
        assert kwargs.get("samplerate") == 16000


def test_h02_record_audio_uses_audio_engine_device(mock_app):
    """H-02: record_audio syncs with audio_engine active device index."""
    mock_app.audio_engine._active_device_index = 5
    with patch("sounddevice.InputStream") as mock_stream:
        mock_instance = MagicMock()
        mock_instance.read.return_value = (np.zeros((100, 1), dtype=np.float32), False)
        mock_stream.return_value.__enter__.return_value = mock_instance

        mock_app.record_audio(duration_s=0.3)
        mock_stream.assert_called_once()
        _, kwargs = mock_stream.call_args
        assert kwargs.get("device") == 5


def test_h03_record_audio_waits_for_active_tts(mock_app):
    """H-03: record_audio waits if TTS is actively playing to prevent self-capture."""
    class MockTTS:
        def __init__(self):
            self._states = [True, True, False]
        @property
        def is_playing(self):
            return self._states.pop(0) if self._states else False

    mock_app.tts_manager = MockTTS()

    with patch("sounddevice.InputStream") as mock_stream, patch("jarvis.core.app.time.sleep") as mock_sleep:
        mock_instance = MagicMock()
        mock_instance.read.return_value = (np.zeros((100, 1), dtype=np.float32), False)
        mock_stream.return_value.__enter__.return_value = mock_instance

        mock_app.record_audio(duration_s=0.3)
        assert mock_sleep.called


def test_h04_hotkey_registration_has_valid_target():
    """H-04: Ctrl+Shift+L callback delegates to _start_voice_interaction."""
    app = JarvisApp.__new__(JarvisApp)
    app.hotkey_manager = MagicMock()
    app._start_voice_interaction = MagicMock()
    app.overlay = MagicMock()
    app.wake_word_detector = MagicMock()
    app.tts_manager = MagicMock()

    app._register_default_hotkeys()
    
    registered = {}
    for call in app.hotkey_manager.register.call_args_list:
        args, _ = call
        registered[args[0]] = args[1]

    assert "Ctrl+Shift+L" in registered
    ptt_cb = registered["Ctrl+Shift+L"]

    with patch("threading.Thread") as mock_thread:
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance
        ptt_cb()
        mock_thread.assert_called_once()
        _, kwargs = mock_thread.call_args
        assert kwargs.get("target") == app._start_voice_interaction
        assert kwargs.get("kwargs", {}).get("trigger_name") == "HOTKEY_PTT"


def test_h08_volume_fail_closed_on_none(mock_app):
    """H-08: Volume control reports fail-closed when hardware returns None."""
    mock_app.computer_controller.set_volume.return_value = None
    res = mock_app._handle_system_volume(level=80)
    assert res["status"] == "failed"
    assert res["success"] is False
    assert res["error"] == "VOLUME_SET_FAILED"

    mock_app.computer_controller.change_volume.return_value = None
    res2 = mock_app._handle_system_volume(delta=10)
    assert res2["status"] == "failed"
    assert res2["success"] is False
    assert res2["error"] == "VOLUME_CHANGE_FAILED"


def test_h08_brightness_fail_closed_on_none(mock_app):
    """H-08: Screen brightness reports fail-closed when hardware returns None."""
    mock_app.computer_controller.set_brightness.return_value = None
    res = mock_app._handle_system_brightness(level=70)
    assert res["status"] == "failed"
    assert res["success"] is False
    assert res["error"] == "BRIGHTNESS_SET_FAILED"

    mock_app.computer_controller.change_brightness.return_value = None
    res2 = mock_app._handle_system_brightness(delta=-10)
    assert res2["status"] == "failed"
    assert res2["success"] is False
    assert res2["error"] == "BRIGHTNESS_CHANGE_FAILED"

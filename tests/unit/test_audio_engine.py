"""
tests/unit/test_audio_engine.py
===============================
Unit tests for Audio Streaming Engine and Microphone Auto-Prober (jarvis.audio.engine).
"""
import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

from jarvis.audio.engine import (
    AudioDeviceInfo,
    AudioEngine,
    AudioEngineConfig,
    AudioEngineMode,
    MicrophoneProbeManager,
)
from jarvis.core.dispatcher import EventBus



def test_microphone_probe_loudest_device(mock_sounddevice):
    """Verify MicrophoneProbeManager selects loudest working device."""
    probe_mgr = MicrophoneProbeManager(mock_sounddevice["devices"])
    idx = probe_mgr.select_best_device(mock_sounddevice)
    assert idx == 1  # "USB Microphone" has peak 0.035


def test_microphone_probe_override(mock_sounddevice):
    """Verify device override by integer and string substring."""
    probe_mgr = MicrophoneProbeManager(mock_sounddevice["devices"])
    assert probe_mgr.select_best_device(mock_sounddevice, override="Virtual Audio") == 2
    assert probe_mgr.select_best_device(mock_sounddevice, override="0") == 0


def test_microphone_probe_all_silent_fallback(mock_sounddevice):
    """Verify fallback to index 0 when all devices report silent."""
    probe_mgr = MicrophoneProbeManager(mock_sounddevice["devices"])
    probe_mgr.probe_device_rms = lambda idx, sd: 0.0001
    assert probe_mgr.select_best_device(mock_sounddevice) == 0


def test_audio_engine_mock_mode_lifecycle():
    """Verify AudioEngine lifecycle operations in mock mode."""
    bus = EventBus()
    events = []
    bus.subscribe("audio.stream_started", lambda **p: events.append("started"))
    bus.subscribe("audio.stream_stopped", lambda **p: events.append("stopped"))

    engine = AudioEngine(mode=AudioEngineMode.MOCK, event_bus=bus)
    assert engine.is_running is False

    engine.start_stream()
    assert engine.is_running is True
    assert "started" in events

    engine.pause_stream()
    engine.resume_stream()

    engine.stop_stream()
    assert engine.is_running is False
    assert "stopped" in events


def test_audio_engine_feed_audio():
    """Verify feed_audio delivers blocks to registered callbacks and EventBus."""
    bus = EventBus()
    bus_blocks = []
    bus.subscribe("audio.block", lambda block, rms, **kwargs: bus_blocks.append(rms))

    callback_blocks = []
    engine = AudioEngine(
        sample_rate=44100,
        block_ms=40,
        mode=AudioEngineMode.MOCK,
        event_bus=bus,
        on_audio_block=lambda blk: callback_blocks.append(blk),
    )
    engine.start_stream()

    # Feed 2 blocks worth of synthetic audio (3528 samples)
    test_audio = np.full(3528, 0.25, dtype=np.float32)
    engine.feed_audio(test_audio)

    engine.stop_stream()
    assert len(callback_blocks) == 2
    assert len(bus_blocks) == 2
    assert np.allclose(callback_blocks[0], 0.25)


def test_audio_engine_feed_virtual_audio():
    """Verify feed_virtual_audio delivers blocks identically to feed_audio."""
    callback_blocks = []
    engine = AudioEngine(
        sample_rate=44100,
        block_ms=40,
        mode=AudioEngineMode.MOCK,
        on_audio_block=lambda blk: callback_blocks.append(blk),
    )
    engine.start_stream()

    test_audio = np.full(3528, 0.77, dtype=np.float32)
    engine.feed_virtual_audio(test_audio)

    engine.stop_stream()
    assert len(callback_blocks) == 2
    assert np.allclose(callback_blocks[0], 0.77)


def test_wasapi_fallback_triggered_on_pa_error(monkeypatch):
    """
    Mock sd.InputStream to raise Exception("PaError -9999") on first call,
    then succeed on second call.
    Assert _stream_worker called InputStream twice and the second call included
    extra_settings with exclusive=True, samplerate=16000, channels=1.
    """
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("jarvis.audio.engine.SOUNDDEVICE_AVAILABLE", True)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("jarvis.audio.engine.time.sleep", lambda s: None)

    import sounddevice as sd
    if not hasattr(sd, "WasapiSettings"):
        class MockWasapiSettings:
            def __init__(self, exclusive=False, **kwargs):
                self.exclusive = exclusive
        monkeypatch.setattr(sd, "WasapiSettings", MockWasapiSettings, raising=False)

    bus = EventBus()
    engine = AudioEngine(
        mode=AudioEngineMode.LIVE,
        input_device=1,
        use_wasapi_exclusive=True,
        event_bus=bus,
    )
    engine._active_device_index = 1

    mock_stream = MagicMock()
    def _on_enter(*args, **kwargs):
        engine._stop_event.set()  # Stop worker loop immediately upon successful open
        return mock_stream
    mock_stream.__enter__.side_effect = _on_enter
    mock_stream.read.return_value = (np.zeros((engine.block_size, 1), dtype=np.float32), False)

    call_history = []
    def mock_input_stream(*args, **kwargs):
        call_history.append((args, kwargs))
        if len(call_history) == 1:
            raise Exception("PaError -9999")
        return mock_stream

    monkeypatch.setattr("sounddevice.InputStream", mock_input_stream)
    monkeypatch.setattr("jarvis.audio.engine.sd.InputStream", mock_input_stream)

    engine._stream_worker()

    assert len(call_history) == 2, f"Expected exactly 2 InputStream calls, got {len(call_history)}"

    # First call: standard PortAudio
    first_kwargs = call_history[0][1]
    assert "extra_settings" not in first_kwargs or first_kwargs["extra_settings"] is None

    # Second call: WASAPI Exclusive fallback
    second_kwargs = call_history[1][1]
    assert "extra_settings" in second_kwargs
    extra = second_kwargs["extra_settings"]
    assert extra is not None
    is_exclusive = getattr(extra, "exclusive", False) or (
        hasattr(extra, "_streaminfo") and (extra._streaminfo.flags & 1) != 0
    )
    assert is_exclusive is True, "WASAPI extra_settings must have exclusive=True"
    assert second_kwargs.get("samplerate") == 16000, "WASAPI fallback must request 16kHz native rate"
    assert second_kwargs.get("channels") == 1, "WASAPI fallback must request 1 channel"


def test_wasapi_fallback_both_fail_enters_mock(monkeypatch):
    """
    Mock sd.InputStream to always raise Exception("PaError -9999").
    Assert engine enters AudioEngineMode.MOCK after retries.
    Assert no True/success return is fabricated and truthful error event published.
    """
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("jarvis.audio.engine.SOUNDDEVICE_AVAILABLE", True)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("jarvis.audio.engine.time.sleep", lambda s: None)

    import sounddevice as sd
    if not hasattr(sd, "WasapiSettings"):
        class MockWasapiSettings:
            def __init__(self, exclusive=False, **kwargs):
                self.exclusive = exclusive
        monkeypatch.setattr(sd, "WasapiSettings", MockWasapiSettings, raising=False)

    bus = EventBus()
    events = []
    bus.subscribe("audio.device_unavailable", lambda **p: events.append(p))

    engine = AudioEngine(
        mode=AudioEngineMode.LIVE,
        input_device=1,
        use_wasapi_exclusive=True,
        event_bus=bus,
    )
    engine._active_device_index = 1

    call_history = []
    def mock_input_stream(*args, **kwargs):
        call_history.append((args, kwargs))
        raise Exception("PaError -9999")

    monkeypatch.setattr("sounddevice.InputStream", mock_input_stream)
    monkeypatch.setattr("jarvis.audio.engine.sd.InputStream", mock_input_stream)

    engine._stream_worker()

    assert engine.mode == AudioEngineMode.MOCK, "Engine must degrade to MOCK mode when both PortAudio and WASAPI fail"
    assert len(call_history) >= 2, "Must attempt both standard and WASAPI capture"
    wasapi_attempted = any(
        "extra_settings" in kwargs and kwargs["extra_settings"] is not None
        for _, kwargs in call_history
    )
    assert wasapi_attempted is True, "WASAPI exclusive fallback must have been attempted"
    assert len(events) >= 1, "Must publish audio.device_unavailable event on EventBus"
    assert events[0].get("reason") == "wasapi_exclusive_failed"


def test_wasapi_skipped_on_non_windows(monkeypatch):
    """
    With sys.platform patched to 'linux', assert that -9999 failure does NOT
    trigger WASAPI retry — goes straight to reconnect/mock logic.
    """
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("jarvis.audio.engine.SOUNDDEVICE_AVAILABLE", True)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("jarvis.audio.engine.time.sleep", lambda s: None)

    bus = EventBus()
    engine = AudioEngine(
        mode=AudioEngineMode.LIVE,
        input_device=1,
        use_wasapi_exclusive=True,
        event_bus=bus,
    )
    engine._active_device_index = 1

    call_history = []
    def mock_input_stream(*args, **kwargs):
        call_history.append((args, kwargs))
        raise Exception("PaError -9999")

    monkeypatch.setattr("sounddevice.InputStream", mock_input_stream)
    monkeypatch.setattr("jarvis.audio.engine.sd.InputStream", mock_input_stream)

    engine._stream_worker()

    assert engine.mode == AudioEngineMode.MOCK
    for _, kwargs in call_history:
        assert "extra_settings" not in kwargs or kwargs["extra_settings"] is None, (
            "WASAPI retry must NOT be attempted on non-Windows platforms"
        )
    assert len(call_history) == 3, f"Expected 3 standard attempts, got {len(call_history)}"


def test_wasapi_exclusive_disabled_config(monkeypatch):
    """
    Set use_wasapi_exclusive=False in config.
    Assert WASAPI retry is never attempted even when PortAudio fails on Windows.
    """
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("jarvis.audio.engine.SOUNDDEVICE_AVAILABLE", True)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("jarvis.audio.engine.time.sleep", lambda s: None)

    bus = EventBus()
    config = AudioEngineConfig(use_wasapi_exclusive=False)
    engine = AudioEngine(
        mode=AudioEngineMode.LIVE,
        input_device=1,
        config=config,
        event_bus=bus,
    )
    engine._active_device_index = 1

    call_history = []
    def mock_input_stream(*args, **kwargs):
        call_history.append((args, kwargs))
        raise Exception("PaError -9999")

    monkeypatch.setattr("sounddevice.InputStream", mock_input_stream)
    monkeypatch.setattr("jarvis.audio.engine.sd.InputStream", mock_input_stream)

    engine._stream_worker()

    assert engine.mode == AudioEngineMode.MOCK
    for _, kwargs in call_history:
        assert "extra_settings" not in kwargs or kwargs["extra_settings"] is None, (
            "WASAPI retry must NOT be attempted when use_wasapi_exclusive=False"
        )
    assert len(call_history) == 3, f"Expected 3 standard attempts, got {len(call_history)}"


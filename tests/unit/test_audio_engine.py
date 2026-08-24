"""
tests/unit/test_audio_engine.py
===============================
Unit tests for Audio Streaming Engine and Microphone Auto-Prober (jarvis.audio.engine).
"""
import numpy as np
import pytest

from jarvis.audio.engine import (
    AudioDeviceInfo,
    AudioEngine,
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


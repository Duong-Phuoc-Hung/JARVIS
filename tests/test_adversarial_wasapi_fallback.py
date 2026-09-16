"""
tests/test_adversarial_wasapi_fallback.py
=========================================
Adversarial challenge and stress test suite for Milestone H-10
(WASAPI exclusive mode capture fallback in jarvis/audio/engine.py).

Challenges verified:
1. Exception handling resilience:
   - PaError -9999 (PortAudioError)
   - OSError (hardware detached / access denied)
   - Generic Exception & RuntimeError
   - Non-Windows platform gating (Linux / Darwin)
   - Configuration toggle (use_wasapi_exclusive=False)
2. WasapiSettings instantiation and stream open failures:
   - WasapiSettings raising TypeError or RuntimeError during instantiation
   - WasapiSettings attribute missing (None) on stripped sounddevice builds
   - InputStream raising exception during WASAPI exclusive open
   - Double-failure retry exhaustion leading cleanly to fail-closed MOCK mode
   - Verification that event 'audio.device_unavailable' is emitted with reason='wasapi_exclusive_failed'
   - Clean shutdown without hanging or deadlocks
3. Device index variations:
   - device as int (0, valid index, invalid index)
   - device as numeric str ("0", "1") and name substring ("Bluetooth", "AirPods")
   - device as None (default device auto-probe, empty device list)
   - Missing explicit device triggers MicrophoneDeviceUnavailableError -> MOCK mode
"""
import sys
import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import sounddevice as sd

from jarvis.audio.engine import (
    AudioDeviceInfo,
    AudioEngine,
    AudioEngineConfig,
    AudioEngineMode,
    MicrophoneDeviceUnavailableError,
    MicrophoneProbeManager,
)
from jarvis.core.dispatcher import EventBus


# ============================================================================
# Fixtures & Helpers
# ============================================================================

class DummyWasapiSettings:
    def __init__(self, exclusive=False, **kwargs):
        self.exclusive = exclusive


def setup_monkeypatched_env(monkeypatch, platform="win32"):
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr("jarvis.audio.engine.SOUNDDEVICE_AVAILABLE", True)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("jarvis.audio.engine.time.sleep", lambda s: None)
    if not hasattr(sd, "WasapiSettings"):
        monkeypatch.setattr(sd, "WasapiSettings", DummyWasapiSettings, raising=False)


# ============================================================================
# Challenge 1: Exception Handling Resilience
# ============================================================================

@pytest.mark.parametrize(
    "exception_to_raise",
    [
        sd.PortAudioError("PaError -9999: paDeviceUnavailable", -9999)
        if hasattr(sd, "PortAudioError")
        else Exception("PaError -9999"),
        OSError("Windows audio endpoint detached: Access Denied"),
        RuntimeError("General sounddevice runtime failure"),
        ValueError("Unsupported sample rate in PortAudio"),
        Exception("Arbitrary unexpected exception"),
    ],
    ids=["PortAudioError_-9999", "OSError", "RuntimeError", "ValueError", "GenericException"],
)
def test_adversarial_exception_resilience_triggers_wasapi(monkeypatch, exception_to_raise):
    """
    Challenge 1: Verify that ANY exception in standard PortAudio open
    (PaError -9999, OSError, generic Exception) successfully triggers the
    WASAPI exclusive fallback on Windows.
    """
    setup_monkeypatched_env(monkeypatch, platform="win32")

    bus = EventBus()
    engine = AudioEngine(
        mode=AudioEngineMode.LIVE,
        input_device=1,
        use_wasapi_exclusive=True,
        event_bus=bus,
    )
    engine._active_device_index = 1

    mock_stream = MagicMock()
    mock_stream.__enter__.side_effect = lambda *args, **kwargs: (
        engine._stop_event.set() or mock_stream
    )
    mock_stream.read.return_value = (np.zeros((engine.block_size, 1), dtype=np.float32), False)

    call_history = []

    def mock_input_stream(*args, **kwargs):
        call_history.append((args, kwargs))
        if len(call_history) == 1:
            raise exception_to_raise
        return mock_stream

    monkeypatch.setattr("sounddevice.InputStream", mock_input_stream)
    monkeypatch.setattr("jarvis.audio.engine.sd.InputStream", mock_input_stream)

    engine._stream_worker()

    assert len(call_history) == 2, (
        f"Expected exactly 2 attempts (PortAudio then WASAPI), got {len(call_history)}"
    )
    # Check that the second attempt is WASAPI exclusive at 16kHz mono
    second_kwargs = call_history[1][1]
    assert "extra_settings" in second_kwargs
    assert second_kwargs.get("samplerate") == 16000
    assert second_kwargs.get("channels") == 1


@pytest.mark.parametrize("target_platform", ["linux", "darwin"])
def test_adversarial_exception_resilience_non_windows_never_triggers_wasapi(
    monkeypatch, target_platform
):
    """
    Challenge 1 (Platform Gating): On non-Windows platforms (Linux, macOS),
    exceptions must NEVER trigger WASAPI exclusive fallback.
    """
    setup_monkeypatched_env(monkeypatch, platform=target_platform)

    bus = EventBus()
    engine = AudioEngine(
        mode=AudioEngineMode.LIVE,
        input_device=2,
        use_wasapi_exclusive=True,
        event_bus=bus,
    )
    engine._active_device_index = 2

    call_history = []

    def mock_input_stream(*args, **kwargs):
        call_history.append((args, kwargs))
        raise sd.PortAudioError("PaError -9999", -9999) if hasattr(sd, "PortAudioError") else Exception("PaError -9999")

    monkeypatch.setattr("sounddevice.InputStream", mock_input_stream)
    monkeypatch.setattr("jarvis.audio.engine.sd.InputStream", mock_input_stream)

    engine._stream_worker()

    assert engine.mode == AudioEngineMode.MOCK
    assert len(call_history) == 3
    for _, kwargs in call_history:
        assert "extra_settings" not in kwargs or kwargs["extra_settings"] is None


# ============================================================================
# Challenge 2: WasapiSettings & Fallback Failure Resilience
# ============================================================================

def test_adversarial_wasapi_settings_constructor_raises_exception(monkeypatch):
    """
    Challenge 2: If WasapiSettings constructor itself raises an exception
    (e.g. COM initialization failure, MemoryError, TypeError), the engine must
    cleanly catch it, log truthfully, retry up to limit, and degrade to MOCK
    without crashing or hanging.
    """
    setup_monkeypatched_env(monkeypatch, platform="win32")

    def faulty_wasapi_settings(*args, **kwargs):
        raise RuntimeError("CoInitialize failed for WASAPI exclusive endpoint")

    monkeypatch.setattr("sounddevice.WasapiSettings", faulty_wasapi_settings, raising=False)
    monkeypatch.setattr("jarvis.audio.engine.sd.WasapiSettings", faulty_wasapi_settings, raising=False)

    bus = EventBus()
    events = []
    bus.subscribe("audio.device_unavailable", lambda **p: events.append(p))
    error_events = []
    bus.subscribe("audio.error", lambda **p: error_events.append(p))

    engine = AudioEngine(
        mode=AudioEngineMode.LIVE,
        input_device=1,
        use_wasapi_exclusive=True,
        event_bus=bus,
    )
    engine._active_device_index = 1

    def mock_input_stream(*args, **kwargs):
        raise Exception("PaError -9999")

    monkeypatch.setattr("sounddevice.InputStream", mock_input_stream)
    monkeypatch.setattr("jarvis.audio.engine.sd.InputStream", mock_input_stream)

    # Must complete without unhandled exception or deadlock
    engine._stream_worker()

    assert engine.mode == AudioEngineMode.MOCK
    assert len(events) >= 1
    assert events[0]["reason"] == "wasapi_exclusive_failed"
    assert "CoInitialize failed" in events[0]["error"]
    assert len(error_events) >= 3


def test_adversarial_wasapi_settings_attribute_is_none(monkeypatch):
    """
    Challenge 2: If sd.WasapiSettings is None or absent, extra_settings remains None,
    and the stream open attempts 16kHz mono fallback without crashing.
    """
    setup_monkeypatched_env(monkeypatch, platform="win32")
    monkeypatch.setattr("jarvis.audio.engine.sd.WasapiSettings", None, raising=False)
    if hasattr(sd, "WasapiSettings"):
        monkeypatch.delattr("sounddevice.WasapiSettings", raising=False)

    bus = EventBus()
    engine = AudioEngine(
        mode=AudioEngineMode.LIVE,
        input_device=1,
        use_wasapi_exclusive=True,
        event_bus=bus,
    )
    engine._active_device_index = 1

    mock_stream = MagicMock()
    mock_stream.__enter__.side_effect = lambda *args, **kwargs: (
        engine._stop_event.set() or mock_stream
    )

    call_history = []

    def mock_input_stream(*args, **kwargs):
        call_history.append((args, kwargs))
        if len(call_history) == 1:
            raise Exception("PaError -9999")
        return mock_stream

    monkeypatch.setattr("sounddevice.InputStream", mock_input_stream)
    monkeypatch.setattr("jarvis.audio.engine.sd.InputStream", mock_input_stream)

    engine._stream_worker()

    assert len(call_history) == 2
    # Second attempt succeeded even with WasapiSettings None
    assert call_history[1][1]["extra_settings"] is None
    assert call_history[1][1]["samplerate"] == 16000


def test_adversarial_wasapi_stream_open_raises_pa_error(monkeypatch):
    """
    Challenge 2: When both PortAudio and WASAPI exclusive InputStream opens fail
    with PaError -9999, the engine executes 3 double-attempts (total 6 calls),
    emits truthful audio.device_unavailable event, and stays in MOCK mode.
    """
    setup_monkeypatched_env(monkeypatch, platform="win32")

    bus = EventBus()
    events = []
    bus.subscribe("audio.device_unavailable", lambda **p: events.append(p))

    engine = AudioEngine(
        mode=AudioEngineMode.LIVE,
        input_device=32,
        use_wasapi_exclusive=True,
        event_bus=bus,
    )
    engine._active_device_index = 32

    call_history = []

    def mock_input_stream(*args, **kwargs):
        call_history.append((args, kwargs))
        if "extra_settings" in kwargs and kwargs["extra_settings"] is not None:
            raise Exception("WASAPI Exclusive Access Denied (Error -9999)")
        raise Exception("PortAudio Shared Stream Unavailable (-9999)")

    monkeypatch.setattr("sounddevice.InputStream", mock_input_stream)
    monkeypatch.setattr("jarvis.audio.engine.sd.InputStream", mock_input_stream)

    engine._stream_worker()

    assert engine.mode == AudioEngineMode.MOCK
    assert len(call_history) == 6, f"Expected 3 standard + 3 WASAPI calls = 6, got {len(call_history)}"
    assert len(events) == 1
    assert events[0]["device_index"] == 32
    assert events[0]["reason"] == "wasapi_exclusive_failed"
    assert "WASAPI Exclusive Access Denied" in events[0]["error"]


def test_adversarial_stop_event_interrupts_worker_cleanly(monkeypatch):
    """
    Challenge 2 (Deadlock / Hang Prevention): If stop_stream() is signaled while
    the worker is in its retry loop, the worker must exit immediately without hanging.
    """
    setup_monkeypatched_env(monkeypatch, platform="win32")

    engine = AudioEngine(
        mode=AudioEngineMode.LIVE,
        input_device=1,
        use_wasapi_exclusive=True,
    )
    engine._active_device_index = 1

    call_count = 0

    def mock_input_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Signal stop after first failed attempt
        engine._stop_event.set()
        raise Exception("PaError -9999")

    monkeypatch.setattr("sounddevice.InputStream", mock_input_stream)
    monkeypatch.setattr("jarvis.audio.engine.sd.InputStream", mock_input_stream)

    start_t = time.monotonic()
    engine._stream_worker()
    duration = time.monotonic() - start_t

    assert duration < 1.0, "Worker must abort promptly upon _stop_event"


# ============================================================================
# Challenge 3: Device Index Variations (int, str, None)
# ============================================================================

@pytest.mark.parametrize(
    "device_input,expected_resolved_idx",
    [
        (0, 0),
        (1, 1),
        (32, 32),
        ("0", 0),
        ("1", 1),
        ("32", 32),
        ("Bluetooth", 32),
        ("airpods", 48),
    ],
    ids=["int_0", "int_1", "int_32", "str_0", "str_1", "str_32", "str_name_bt", "str_name_airpods"],
)
def test_adversarial_device_index_variation_resolution(device_input, expected_resolved_idx):
    """
    Challenge 3: Verify that integer indices, string numeric indices, and
    name substrings are correctly resolved to physical device index integers.
    """
    devices = [
        {"name": "Realtek Speakers", "max_input_channels": 0, "max_output_channels": 2, "index": 0},
        {"name": "USB Audio Microphone", "max_input_channels": 1, "max_output_channels": 0, "index": 1},
        {"name": "Bluetooth HFP LY-Z5202", "max_input_channels": 1, "max_output_channels": 1, "index": 32},
        {"name": "AirPods Pro Hands-Free", "max_input_channels": 1, "max_output_channels": 1, "index": 48},
    ]

    resolved = MicrophoneProbeManager.resolve_explicit_device(device_input, devices)
    assert resolved == expected_resolved_idx


def test_adversarial_device_index_none_auto_probes():
    """
    Challenge 3: When device is None, select_best_device probes available devices
    and returns the best available device index without failing.
    """
    devices = [
        {"name": "Default Mic", "max_input_channels": 1, "max_output_channels": 0, "index": 0},
        {"name": "High Signal Mic", "max_input_channels": 1, "max_output_channels": 0, "index": 3},
    ]
    probe_mgr = MicrophoneProbeManager(devices)
    # Mock probe RMS
    probe_mgr.probe_device_rms = lambda idx, sd_mod=None: 0.05 if idx == 3 else 0.005

    mock_sd = {"devices": devices, "default": {"device": [None, None]}}
    selected = probe_mgr.select_best_device(sd_module=mock_sd, override=None)
    assert selected == 3


def test_adversarial_device_index_empty_str_acts_like_none():
    """
    Challenge 3: Empty string or whitespace string device must defer to auto-probing
    rather than treating '' as a missing named device.
    """
    devices = [
        {"name": "Default Mic", "max_input_channels": 1, "max_output_channels": 0, "index": 0},
    ]
    probe_mgr = MicrophoneProbeManager(devices)
    probe_mgr.probe_device_rms = lambda idx, sd_mod=None: 0.02

    mock_sd = {"devices": devices, "default": {"device": [0, None]}}
    assert probe_mgr.select_best_device(sd_module=mock_sd, override="") == 0
    assert probe_mgr.select_best_device(sd_module=mock_sd, override="   ") == 0


def test_adversarial_device_index_nonexistent_fails_closed(monkeypatch):
    """
    Challenge 3: Explicit nonexistent device index or string raises
    MicrophoneDeviceUnavailableError and causes AudioEngine to enter MOCK mode
    fail-closed without substituting another microphone.
    """
    devices = [
        {"name": "Realtek Audio", "max_input_channels": 1, "max_output_channels": 0, "index": 1},
    ]
    mock_sd = {
        "devices": devices,
        "query_devices": lambda: devices,
    }
    monkeypatch.setattr("jarvis.audio.engine.sd", mock_sd)
    monkeypatch.setattr("jarvis.audio.engine.SOUNDDEVICE_AVAILABLE", True)

    bus = EventBus()
    events = []
    bus.subscribe("audio.device_unavailable", lambda **p: events.append(p))

    engine = AudioEngine(
        mode=AudioEngineMode.LIVE,
        input_device="NonExistentMicrophoneDevice",
        event_bus=bus,
    )
    # Mock probe manager devices
    engine.probe_manager.devices = devices
    engine.probe_devices = lambda: [AudioDeviceInfo(index=1, name="Realtek Audio", max_input_channels=1)]

    engine.start_stream()

    assert engine.mode == AudioEngineMode.MOCK, "Explicit missing device must force MOCK mode"
    assert engine._active_device_index is None
    assert len(events) == 1
    assert events[0]["requested_device"] == "NonExistentMicrophoneDevice"

    engine.stop_stream()


def test_adversarial_stream_worker_with_device_none(monkeypatch):
    """
    Challenge 3: If _active_device_index is None in _stream_worker (e.g. system default),
    ensure both PortAudio and WASAPI fallback pass device=None without crashing,
    and degrade to MOCK if both fail.
    """
    setup_monkeypatched_env(monkeypatch, platform="win32")

    bus = EventBus()
    engine = AudioEngine(
        mode=AudioEngineMode.LIVE,
        input_device=None,
        use_wasapi_exclusive=True,
        event_bus=bus,
    )
    engine._active_device_index = None

    call_devices = []

    def mock_input_stream(*args, **kwargs):
        call_devices.append(kwargs.get("device"))
        raise Exception("PaError -9999 on default device")

    monkeypatch.setattr("sounddevice.InputStream", mock_input_stream)
    monkeypatch.setattr("jarvis.audio.engine.sd.InputStream", mock_input_stream)

    engine._stream_worker()

    assert engine.mode == AudioEngineMode.MOCK
    assert all(dev is None for dev in call_devices)
    assert len(call_devices) == 6  # 3 standard + 3 WASAPI attempts


def test_adversarial_mid_stream_runtime_disconnect_reconnects_and_degrades_to_mock(monkeypatch):
    """
    Stress test: While actively streaming via WASAPI, the device is disconnected
    causing stream.read() to raise PortAudioError. The engine must attempt
    reconnection, exhaust retries, cleanly transition to MOCK, and emit
    audio.device_unavailable.
    """
    setup_monkeypatched_env(monkeypatch, platform="win32")

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

    first_stream_active = True

    class FlakyStream:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

        def read(self, size):
            nonlocal first_stream_active
            if first_stream_active:
                first_stream_active = False
                raise sd.PortAudioError("Device disconnected during streaming (-9999)", -9999) if hasattr(sd, "PortAudioError") else Exception("Device disconnected")
            return (np.zeros((size, 1), dtype=np.float32), False)

    stream_attempts = []

    def mock_input_stream(*args, **kwargs):
        stream_attempts.append(kwargs)
        if len(stream_attempts) == 1:
            # First attempt: standard PortAudio fails immediately
            raise Exception("PaError -9999")
        elif len(stream_attempts) == 2:
            # Second attempt: WASAPI opens, but then disconnects in stream.read()
            return FlakyStream(**kwargs)
        else:
            # Subsequent reconnection attempts all fail
            raise Exception("PaError -9999 (device still missing)")

    monkeypatch.setattr("sounddevice.InputStream", mock_input_stream)
    monkeypatch.setattr("jarvis.audio.engine.sd.InputStream", mock_input_stream)

    engine._stream_worker()

    assert engine.mode == AudioEngineMode.MOCK
    assert len(events) >= 1
    assert events[0]["reason"] == "wasapi_exclusive_failed"


def test_adversarial_wasapi_block_size_and_dispatch(monkeypatch):
    """
    Verify that when WASAPI fallback succeeds at 16kHz, the blocksize dispatched
    matches 16kHz (e.g. 16000 * 0.040 = 640 samples) instead of 44.1kHz (1764 samples).
    """
    setup_monkeypatched_env(monkeypatch, platform="win32")

    dispatched_blocks = []
    engine = AudioEngine(
        sample_rate=44100,
        block_ms=40,
        mode=AudioEngineMode.LIVE,
        input_device=1,
        use_wasapi_exclusive=True,
        on_audio_block=lambda blk: dispatched_blocks.append(blk),
    )
    engine._active_device_index = 1

    mock_stream = MagicMock()
    mock_stream.__enter__.return_value = mock_stream

    read_calls = 0

    def mock_read(size):
        nonlocal read_calls
        read_calls += 1
        if read_calls >= 2:
            engine._stop_event.set()
        # Verify that _stream_worker requested 640 samples (16000 * 0.040)
        assert size == 640, f"Expected wasapi blk_size=640 at 16kHz, got {size}"
        data = np.full((size, 1), 0.42, dtype=np.float32)
        return (data, False)

    mock_stream.read.side_effect = mock_read

    call_count = 0

    def mock_input_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("PaError -9999")
        return mock_stream

    monkeypatch.setattr("sounddevice.InputStream", mock_input_stream)
    monkeypatch.setattr("jarvis.audio.engine.sd.InputStream", mock_input_stream)

    engine._stream_worker()

    assert len(dispatched_blocks) >= 1
    assert len(dispatched_blocks[0]) == 640
    assert np.allclose(dispatched_blocks[0], 0.42)


def test_adversarial_dynamic_config_reload_disables_wasapi(monkeypatch):
    """
    Verify that hot-reloading configuration with audio.use_wasapi_exclusive=False
    immediately disables WASAPI fallback for subsequent stream reconnection.
    """
    setup_monkeypatched_env(monkeypatch, platform="win32")

    config_dict = {"audio.use_wasapi_exclusive": True}

    class MockConfigManager:
        def get(self, key, default=None):
            return config_dict.get(key, default)

    cfg_mgr = MockConfigManager()
    engine = AudioEngine(
        mode=AudioEngineMode.LIVE,
        input_device=1,
        config_manager=cfg_mgr,
    )
    assert engine.use_wasapi_exclusive is True
    assert engine.config.use_wasapi_exclusive is True

    # Now mutate config and reload
    config_dict["audio.use_wasapi_exclusive"] = False
    engine._load_from_config()

    assert engine.use_wasapi_exclusive is False
    assert engine.config.use_wasapi_exclusive is False

    engine._active_device_index = 1
    call_history = []

    def mock_input_stream(*args, **kwargs):
        call_history.append((args, kwargs))
        raise Exception("PaError -9999")

    monkeypatch.setattr("sounddevice.InputStream", mock_input_stream)
    monkeypatch.setattr("jarvis.audio.engine.sd.InputStream", mock_input_stream)

    engine._stream_worker()

    # With WASAPI disabled via config reload, no WASAPI extra_settings should be attempted
    for _, kwargs in call_history:
        assert "extra_settings" not in kwargs or kwargs["extra_settings"] is None
    assert len(call_history) == 3


def test_adversarial_real_sounddevice_wasapi_settings_contract():
    """
    Test against real sounddevice module in this Windows environment:
    WasapiSettings(exclusive=True) must be instantiable and configure
    underlying PaWasapiStreamInfo flags = 1 (paWinWasapiExclusive).
    """
    if sys.platform != "win32":
        pytest.skip("Windows only test")
    if not hasattr(sd, "WasapiSettings"):
        pytest.skip("WasapiSettings not present in sounddevice build")

    settings = sd.WasapiSettings(exclusive=True)
    assert settings is not None
    assert hasattr(settings, "_streaminfo")
    # paWinWasapiExclusive = 1
    assert (settings._streaminfo.flags & 1) == 1


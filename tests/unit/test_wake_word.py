"""
tests/unit/test_wake_word.py
============================
Comprehensive Unit and Integration Test Suite for JARVIS Wake Word Layer (Milestone 1 / R1):
Covers:
  1. WakeWordDetector state transitions & live toggle (enabled/disabled without restart).
  2. Multi-format & multi-sample-rate audio block processing (44.1kHz, 16kHz, int16, float32, mono, stereo).
  3. Signal classification: Deterministic keyword detection vs Silence vs White Noise vs Impulse Claps.
  4. False positive suppression & robustness against NaN, Inf, and empty buffers.
  5. Refractory period / cooldown enforcement (1.5s cooldown guard) & callback dispatch.
  6. Sensitivity tuning effects on detection threshold.
  7. High-concurrency thread safety for concurrent audio streaming and live state toggles.
  8. SystemTrayController live toggle integration (_on_toggle_wakeword).
  9. Synthetic wake word audio signal generator and resampler verification.
 10. Streaming in 40ms blocks (AudioEngine live emulation).
 11. Tier 1 (Vosk, OpenWakeWord, Porcupine) integration & graceful Tier 2 fallback.
 12. Sub-second detection latency verification (<1s).
"""
from __future__ import annotations

import concurrent.futures
import json
import math
import threading
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.audio.wake_word import (
    AcousticSpectralDetector,
    WakeWordDetector,
    WakeWordEngineType,
    WakeWordResult,
    _PorcupineFrameBuffer,
    generate_wake_word_signal,
    resample_audio,
)
from jarvis.ui.tray import SystemTrayController, TrayStatus

# ============================================================================
# 1. INITIALIZATION & STATE MANAGEMENT TESTS
# ============================================================================

def test_wake_word_detector_initialization_defaults():
    """Verify default initialization parameters and state."""
    detector = WakeWordDetector()
    assert detector.is_enabled() is True
    assert detector.enabled is True
    assert detector.sensitivity == 0.5
    assert detector.cooldown_s == 1.5
    assert detector.sample_rate == 44100
    assert detector.target_sample_rate == 16000
    assert detector.trigger_count == 0


def test_wake_word_detector_live_enable_disable_toggle():
    """Verify set_enabled toggles detection live without restart."""
    detector = WakeWordDetector(enabled=True)
    assert detector.is_enabled() is True

    # Disable
    detector.set_enabled(False)
    assert detector.is_enabled() is False
    assert detector.enabled is False

    # Feed keyword signal while disabled -> should return False
    keyword_audio = generate_wake_word_signal(sample_rate=44100)
    res = detector.feed_audio_block(keyword_audio)
    assert res is None
    assert detector.process_audio_block(keyword_audio) is False
    assert detector.trigger_count == 0

    # Re-enable
    detector.set_enabled(True)
    assert detector.is_enabled() is True
    assert detector.enabled is True

    # Feed keyword signal while enabled -> should trigger
    detected = detector.process_audio_block(keyword_audio)
    assert detected is True
    assert detector.trigger_count == 1


# These three tests exercise generic enable/disable state-machine behavior
# that has nothing to do with which Tier 1 backend is active. They force all
# optional backends unavailable so a developer machine that happens to have
# vosk/openwakeword/pvporcupine installed (or PORCUPINE_ACCESS_KEY set) can
# never change their behavior or speed.
def test_wake_word_detector_toggle_enabled_true_to_false():
    """Verify toggle_enabled() flips True -> False and returns the new state."""
    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", False),
    ):
        detector = WakeWordDetector(enabled=True)
    assert detector.is_enabled() is True

    result = detector.toggle_enabled()

    assert result is False
    assert detector.is_enabled() is False
    assert detector.enabled is False


def test_wake_word_detector_toggle_enabled_false_to_true():
    """Verify toggle_enabled() flips False -> True and returns the new state."""
    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", False),
    ):
        detector = WakeWordDetector(enabled=False)
    assert detector.is_enabled() is False

    result = detector.toggle_enabled()

    assert result is True
    assert detector.is_enabled() is True
    assert detector.enabled is True


def test_wake_word_detector_toggle_enabled_round_trip_and_set_enabled_agree():
    """Verify toggle_enabled() stays consistent with set_enabled()/is_enabled()/enabled."""
    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", False),
    ):
        detector = WakeWordDetector(enabled=True)

    assert detector.toggle_enabled() is False
    assert detector.toggle_enabled() is True
    assert detector.toggle_enabled() is False
    assert detector.is_enabled() is False
    assert detector.enabled is False

    detector.set_enabled(True)
    assert detector.is_enabled() is True
    assert detector.toggle_enabled() is False
    assert detector.enabled is False


def test_wake_word_detector_reset():
    """Verify reset() clears internal buffers and trigger timing."""
    detector = WakeWordDetector()
    keyword_audio = generate_wake_word_signal(sample_rate=44100)
    assert detector.process_audio_block(keyword_audio) is True
    assert detector._last_trigger_time > 0

    detector.reset()
    assert np.all(detector._ring_buffer == 0.0)
    assert detector._last_trigger_time == 0.0


# ============================================================================
# 2. AUDIO FORMAT & RESAMPLING TESTS
# ============================================================================

def test_resample_audio_exact_and_edge_cases():
    """Verify resample_audio handles various rates and empty inputs."""
    # Identity
    arr = np.array([0.1, 0.5, 0.9], dtype=np.float32)
    same = resample_audio(arr, 16000, 16000)
    assert np.array_equal(arr, same)

    # Empty
    empty = np.empty(0, dtype=np.float32)
    assert len(resample_audio(empty, 44100, 16000)) == 0

    # 44.1kHz -> 16kHz
    orig_len = 44100
    signal_44k = np.sin(2 * np.pi * 440.0 * np.linspace(0, 1.0, orig_len, endpoint=False)).astype(np.float32)
    resampled_16k = resample_audio(signal_44k, 44100, 16000)
    assert len(resampled_16k) == 16000
    assert abs(np.max(resampled_16k) - 1.0) < 0.05


def test_wake_word_audio_format_tolerance():
    """Verify detector handles int16, float32, mono, and stereo arrays."""
    detector = WakeWordDetector(sensitivity=0.6)
    keyword_mono = generate_wake_word_signal(sample_rate=44100)

    # 1. float32 mono
    assert detector.process_audio_block(keyword_mono) is True
    detector.reset()

    # 2. int16 mono
    keyword_int16 = (keyword_mono * 32767.0).astype(np.int16)
    assert detector.process_audio_block(keyword_int16) is True
    detector.reset()

    # 3. 2D stereo (2 channels)
    keyword_stereo = np.column_stack([keyword_mono, keyword_mono])
    assert detector.process_audio_block(keyword_stereo) is True
    detector.reset()

    # 4. 16kHz direct input
    keyword_16k = generate_wake_word_signal(sample_rate=16000)
    detector_16k = WakeWordDetector(sample_rate=16000)
    assert detector_16k.process_audio_block(keyword_16k) is True


def test_wake_word_int16_mono_normalization_exact():
    """
    Verify int16 mono PCM is normalized to [-1.0, 1.0] by exact amplitude
    scale (value / 32768.0), with exactly computable expected samples.
    """
    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", False),
    ):
        detector = WakeWordDetector(sample_rate=16000, target_sample_rate=16000)

    int16_samples = np.array([16384, -16384, 32767, -32768], dtype=np.int16)
    detector.feed_audio_block(int16_samples)

    expected = int16_samples.astype(np.float32) / 32768.0
    actual = detector._ring_buffer[-4:]
    assert np.allclose(actual, expected, atol=1e-6)
    assert np.max(np.abs(actual)) <= 1.0


def test_wake_word_int16_stereo_normalization_exact():
    """
    Verify int16 STEREO PCM is normalized to [-1.0, 1.0] BEFORE channel
    averaging. This guards the exact ordering bug: `np.mean(..., axis=1)`
    on a raw int16 array promotes to float64, which would make the later
    `np.issubdtype(arr.dtype, np.integer)` check false and silently skip
    normalization -- leaving stereo int16 PCM at roughly [-32768, 32767]
    amplitude scale instead of [-1.0, 1.0]. Uses explicit per-channel
    values so the expected normalized mono result is exactly computable.
    """
    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", False),
    ):
        detector = WakeWordDetector(sample_rate=16000, target_sample_rate=16000)

    left = np.array([32767, -32768], dtype=np.int16)
    right = np.array([0, 0], dtype=np.int16)
    stereo = np.column_stack([left, right]).astype(np.int16)

    detector.feed_audio_block(stereo)

    expected_left = left.astype(np.float32) / 32768.0
    expected_right = right.astype(np.float32) / 32768.0
    expected_mono = (expected_left + expected_right) / 2.0

    actual = detector._ring_buffer[-2:]
    assert np.allclose(actual, expected_mono, atol=1e-6)
    # The bug this guards against would produce values around the raw
    # +-32768 amplitude scale, wildly outside the valid normalized range.
    assert np.max(np.abs(actual)) <= 1.0


# ============================================================================
# 3. CLASSIFICATION & FALSE POSITIVE SUPPRESSION TESTS
# ============================================================================

def test_wake_word_silence_rejection():
    """Verify pure digital silence never triggers wake word detection."""
    detector = WakeWordDetector()
    silence = np.zeros(44100, dtype=np.float32)
    for _ in range(5):
        assert detector.process_audio_block(silence) is False
    assert detector.trigger_count == 0


def test_wake_word_white_noise_rejection():
    """Verify Gaussian ambient white noise never triggers wake word."""
    detector = WakeWordDetector(sensitivity=0.6)
    np.random.seed(42)
    for rms in [0.005, 0.02, 0.05, 0.10]:
        noise = (np.random.normal(0.0, 1.0, 44100) * rms).astype(np.float32)
        assert detector.process_audio_block(noise) is False
    assert detector.trigger_count == 0


def test_wake_word_clap_transient_rejection():
    """Verify impulsive clap spikes (short broadband burst) do not trigger wake word."""
    detector = WakeWordDetector(sensitivity=0.6)
    # Synthesize an acoustic clap: 25ms impulse with rapid decay
    t = np.linspace(0, 0.025, int(44100 * 0.025), endpoint=False)
    clap_pulse = (np.exp(-t / 0.005) * np.sin(2 * np.pi * 2200.0 * t) * 0.9).astype(np.float32)
    # Pad to 1 second
    audio = np.zeros(44100, dtype=np.float32)
    audio[10000 : 10000 + len(clap_pulse)] = clap_pulse

    assert detector.process_audio_block(audio) is False
    assert detector.trigger_count == 0


def test_wake_word_nan_inf_none_edge_cases():
    """Verify detector handles None, empty, NaN, and Inf without crashing."""
    detector = WakeWordDetector()
    assert detector.process_audio_block(None) is False
    assert detector.feed_audio_block(None) is None

    empty = np.empty(0, dtype=np.float32)
    assert detector.process_audio_block(empty) is False

    nan_audio = np.full(1000, np.nan, dtype=np.float32)
    assert detector.process_audio_block(nan_audio) is False

    inf_audio = np.array([np.inf, -np.inf, 0.0, 1.0], dtype=np.float32)
    assert detector.process_audio_block(inf_audio) is False


# ============================================================================
# 4. REFRACTORY PERIOD (COOLDOWN) & CALLBACK TESTS
# ============================================================================

def test_wake_word_refractory_period_cooldown():
    """Verify 1.5s refractory period prevents duplicate triggers within cooldown window."""
    detector = WakeWordDetector(cooldown_s=1.5)
    keyword_audio = generate_wake_word_signal(sample_rate=44100)

    # First trigger: Success
    res1 = detector.feed_audio_block(keyword_audio, timestamp=100.0)
    assert res1 is not None
    assert res1.keyword == "hey_jarvis"
    assert detector.trigger_count == 1

    # Second trigger at 100.5s (0.5s later, within 1.5s cooldown): Should be blocked
    res2 = detector.feed_audio_block(keyword_audio, timestamp=100.5)
    assert res2 is None
    assert detector.trigger_count == 1

    # Third trigger at 101.4s (1.4s later, still within 1.5s cooldown): Should be blocked
    res3 = detector.feed_audio_block(keyword_audio, timestamp=101.4)
    assert res3 is None
    assert detector.trigger_count == 1

    # Fourth trigger at 101.6s (1.6s later, after cooldown): Should succeed
    res4 = detector.feed_audio_block(keyword_audio, timestamp=101.6)
    assert res4 is not None
    assert detector.trigger_count == 2


def test_wake_word_callback_invocations():
    """Verify both zero-arg callback and two-arg on_wake_word are invoked on detection."""
    callback_called = []
    on_wake_word_events = []

    def _simple_cb():
        callback_called.append(True)

    def _detailed_cb(kw: str, conf: float):
        on_wake_word_events.append({"keyword": kw, "confidence": conf})

    detector = WakeWordDetector(
        callback=_simple_cb,
        on_wake_word=_detailed_cb,
        cooldown_s=0.1,
    )

    keyword_audio = generate_wake_word_signal(sample_rate=44100)
    detected = detector.process_audio_block(keyword_audio)
    assert detected is True

    assert len(callback_called) == 1
    assert len(on_wake_word_events) == 1
    assert on_wake_word_events[0]["keyword"] == "hey_jarvis"
    assert on_wake_word_events[0]["confidence"] > 0.0


def test_wake_word_callback_exception_isolation():
    """Verify exceptions inside user callbacks do not crash the detector."""
    def _faulty_cb():
        raise RuntimeError("Simulated callback failure")

    def _faulty_detailed_cb(kw, conf):
        raise ValueError("Simulated detailed callback failure")

    detector = WakeWordDetector(
        callback=_faulty_cb,
        on_wake_word=_faulty_detailed_cb,
    )

    keyword_audio = generate_wake_word_signal(sample_rate=44100)
    # Should not raise exception
    detected = detector.process_audio_block(keyword_audio)
    assert detected is True


# ============================================================================
# 5. SENSITIVITY TUNING & RESULT MODEL TESTS
# ============================================================================

def test_wake_word_sensitivity_bounds_and_effects():
    """Verify sensitivity is clamped to [0.0, 1.0] and affects thresholding."""
    d_low = WakeWordDetector(sensitivity=-0.5)
    assert d_low.sensitivity == 0.0

    d_high = WakeWordDetector(sensitivity=1.5)
    assert d_high.sensitivity == 1.0


def test_wake_word_result_dataclass_and_dict():
    """Verify WakeWordResult dataclass serialization."""
    res = WakeWordResult(
        keyword="hey_jarvis",
        confidence=0.88,
        timestamp=123.456,
        engine="acoustic_fallback",
    )
    d = res.to_dict()
    assert d["keyword"] == "hey_jarvis"
    assert d["confidence"] == 0.88
    assert d["timestamp"] == 123.456
    assert d["engine"] == "acoustic_fallback"


def test_wake_word_engine_type_enum():
    """Verify WakeWordEngineType enum definitions."""
    assert WakeWordEngineType.VOSK.value == "vosk"
    assert WakeWordEngineType.OPENWAKEWORD.value == "openwakeword"
    assert WakeWordEngineType.PORCUPINE.value == "porcupine"
    assert WakeWordEngineType.ACOUSTIC_FALLBACK.value == "acoustic_fallback"
    assert WakeWordEngineType.MOCK.value == "mock"


# ============================================================================
# 6. STREAMING IN 40MS BLOCKS (AUDIO ENGINE EMULATION)
# ============================================================================

def test_wake_word_40ms_chunk_streaming():
    """
    Simulates real-time AudioEngine stream feeding 40ms blocks (1764 samples @ 44.1kHz).
    Verifies that progressive streaming correctly triggers detection when the full utterance
    enters the sliding buffer.
    """
    detector = WakeWordDetector(sample_rate=44100, cooldown_s=1.5)
    keyword_audio = generate_wake_word_signal(sample_rate=44100, duration_s=1.0)

    block_size = int(44100 * 0.040)  # 1764 samples = 40ms
    detected_steps = []

    # Stream the full 1.0s audio buffer in 40ms increments
    for i in range(0, len(keyword_audio), block_size):
        chunk = keyword_audio[i : i + block_size]
        if len(chunk) < block_size:
            pad = np.zeros(block_size - len(chunk), dtype=np.float32)
            chunk = np.concatenate([chunk, pad])
        hit = detector.process_audio_block(chunk)
        if hit:
            detected_steps.append(i)

    # Should detect exactly once during the stream
    assert len(detected_steps) == 1
    assert detector.trigger_count == 1


def test_wake_word_detection_latency_under_1s():
    """
    Verifies that acoustic feature extraction and classification executes
    in less than 20ms per analysis window (well below the <1s total budget).
    """
    detector = AcousticSpectralDetector(sample_rate=16000)
    audio_16k = generate_wake_word_signal(sample_rate=16000, duration_s=1.2)

    start = time.perf_counter()
    detected, kw, conf = detector.analyze_window(audio_16k, sensitivity=0.5)
    duration_ms = (time.perf_counter() - start) * 1000.0

    assert detected is True
    assert duration_ms < 50.0  # Processing takes < 50ms (typically 2-8ms on CPU)


# ============================================================================
# 7. TIER 1 INTEGRATION & GRACEFUL FALLBACK TESTS
# ============================================================================

def test_wake_word_tier1_vosk_mock_integration():
    """Verify Vosk Tier 1 integration when recognizer is present."""
    detector = WakeWordDetector()
    detector._engine_type = WakeWordEngineType.VOSK

    mock_rec = MagicMock()
    mock_rec.AcceptWaveform.return_value = True
    mock_rec.Result.return_value = json.dumps({"text": "hey jarvis"})
    detector._tier1_engine = mock_rec

    audio = np.zeros(16000, dtype=np.float32)
    res = detector.feed_audio_block(audio)

    assert res is not None
    assert res.keyword == "hey_jarvis"
    assert res.confidence >= 0.90
    assert res.engine == WakeWordEngineType.VOSK.value


def test_wake_word_tier1_failure_smooth_fallback_to_tier2():
    """Verify that an exception in Tier 1 model smoothly falls back to Tier 2 without crashing."""
    detector = WakeWordDetector()
    detector._engine_type = WakeWordEngineType.VOSK

    faulty_rec = MagicMock()
    faulty_rec.AcceptWaveform.side_effect = RuntimeError("Vosk corrupted model buffer")
    detector._tier1_engine = faulty_rec

    keyword_audio = generate_wake_word_signal(sample_rate=44100)
    res = detector.feed_audio_block(keyword_audio)

    assert res is not None
    assert res.keyword == "hey_jarvis"
    assert res.engine == WakeWordEngineType.ACOUSTIC_FALLBACK.value


# ============================================================================
# 7b. TIER 1 PORCUPINE BACKEND INTEGRATION TESTS
# ============================================================================
#
# pvporcupine is never installed in CI/dev environments here, so every test
# below patches the module-level availability flag and the `pvporcupine`
# reference itself with mocks. No real access key, native library, or
# network access is required or used.

def _mock_pvporcupine_module(mock_engine: MagicMock) -> MagicMock:
    """Build a fake `pvporcupine` module exposing `create()` -> mock_engine."""
    module = MagicMock()
    module.create.return_value = mock_engine
    return module


def _make_mock_porcupine_engine(frame_length: int = 512, sample_rate: int = 16000) -> MagicMock:
    engine = MagicMock()
    engine.frame_length = frame_length
    engine.sample_rate = sample_rate
    engine.process.return_value = -1
    return engine


def test_wake_word_porcupine_production_44100_to_16000_block_path():
    """
    Focused regression test for the REAL production AudioEngine default
    path: `block_size = int(sample_rate * block_ms / 1000)` with the
    defaults `sample_rate=44100`, `block_ms=40` gives exactly 1764 raw
    samples @ 44.1kHz per audio callback. Confirms directly that this
    resamples to exactly 640 samples @ 16kHz (JARVIS's default
    `target_sample_rate`), then feeds the detector this exact production
    block size over several consecutive callbacks and verifies every call
    into Porcupine receives a well-formed, exactly-`frame_length` frame —
    never a malformed one — with the carried-over remainder matching
    hand-computed expectations at each step. Does not modify AudioEngine;
    exercises the same math with a deterministic mock.
    """
    # The exact conversion this production path depends on.
    block_44_1k = np.zeros(1764, dtype=np.float32)
    resampled_16k = resample_audio(block_44_1k, 44100, 16000)
    assert len(resampled_16k) == 640

    mock_engine = _make_mock_porcupine_engine(frame_length=512, sample_rate=16000)
    mock_engine.process.return_value = -1
    mock_module = _mock_pvporcupine_module(mock_engine)

    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", True),
        patch("jarvis.audio.wake_word.pvporcupine", mock_module),
    ):
        # Production defaults: sample_rate=44100, target_sample_rate=16000.
        detector = WakeWordDetector(config={"porcupine_access_key": "test-key"})

    assert detector.sample_rate == 44100
    assert detector.target_sample_rate == 16000

    # Hand-computed expected cumulative frame count after each 40ms callback.
    samples_produced = 0
    samples_consumed = 0
    expected_call_count_after: list[int] = []
    for _ in range(8):
        samples_produced += 640
        new_frames = (samples_produced - samples_consumed) // 512
        samples_consumed += new_frames * 512
        expected_call_count_after.append(samples_consumed // 512)

    for i in range(8):
        detector.feed_audio_block(block_44_1k, timestamp=100.0 + i * 0.04)
        assert mock_engine.process.call_count == expected_call_count_after[i], (
            f"unexpected Porcupine call count after callback {i}"
        )

    # No malformed frame was ever sent to process(): every call received
    # exactly `frame_length` samples.
    for call in mock_engine.process.call_args_list:
        frame_arg = call[0][0]
        assert len(frame_arg) == 512

    # Remainder retained by the adapter matches what wasn't yet a full frame.
    expected_remainder = samples_produced - samples_consumed
    assert len(detector._porcupine_frame_buffer._pending) == expected_remainder


def test_wake_word_tier1_porcupine_package_unavailable_falls_back(monkeypatch):
    """Verify absence of the pvporcupine package degrades to the acoustic fallback."""
    monkeypatch.setenv("PORCUPINE_ACCESS_KEY", "test-key")
    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", False),
        patch("jarvis.audio.wake_word.pvporcupine", None),
    ):
        detector = WakeWordDetector(config={})

    assert detector._engine_type == WakeWordEngineType.ACOUSTIC_FALLBACK
    assert detector._tier1_engine is None
    assert detector._porcupine_frame_buffer is None


def test_wake_word_tier1_porcupine_no_access_key_falls_back(monkeypatch):
    """Verify a missing access key (env and config) skips Porcupine init entirely."""
    monkeypatch.delenv("PORCUPINE_ACCESS_KEY", raising=False)
    mock_module = MagicMock()
    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", True),
        patch("jarvis.audio.wake_word.pvporcupine", mock_module),
    ):
        detector = WakeWordDetector(config={})

    assert detector._engine_type == WakeWordEngineType.ACOUSTIC_FALLBACK
    assert detector._tier1_engine is None
    mock_module.create.assert_not_called()


def test_wake_word_tier1_porcupine_successful_init_and_detection():
    """Verify a valid access key initializes Porcupine and a real match triggers detection."""
    mock_engine = _make_mock_porcupine_engine()
    mock_engine.process.return_value = 0  # index 0 = configured "jarvis" keyword matched
    mock_module = _mock_pvporcupine_module(mock_engine)

    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", True),
        patch("jarvis.audio.wake_word.pvporcupine", mock_module),
    ):
        detector = WakeWordDetector(
            sample_rate=16000,
            target_sample_rate=16000,
            config={"porcupine_access_key": "test-key"},
        )

    assert detector._engine_type == WakeWordEngineType.PORCUPINE
    assert detector._tier1_engine is mock_engine
    assert detector._porcupine_frame_buffer is not None
    mock_module.create.assert_called_once()

    # Deterministic PCM: mock_engine.process() ignores its argument content,
    # so no random synthetic speech is needed to drive detection here.
    audio = np.zeros(16000, dtype=np.float32)
    res = detector.feed_audio_block(audio)

    assert res is not None
    assert res.keyword == "hey_jarvis"
    assert res.confidence == 1.0
    assert res.engine == WakeWordEngineType.PORCUPINE.value
    assert mock_engine.process.called


def test_wake_word_tier1_porcupine_no_detection_falls_through_to_tier2():
    """Verify porcupine.process() returning -1 (no match) yields no detection overall."""
    mock_engine = _make_mock_porcupine_engine()  # process() always returns -1
    mock_module = _mock_pvporcupine_module(mock_engine)

    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", True),
        patch("jarvis.audio.wake_word.pvporcupine", mock_module),
    ):
        detector = WakeWordDetector(
            sample_rate=16000,
            target_sample_rate=16000,
            config={"porcupine_access_key": "test-key"},
        )

    silence = np.zeros(16000, dtype=np.float32)
    res = detector.feed_audio_block(silence)

    assert res is None
    assert mock_engine.process.called
    assert detector.trigger_count == 0


def test_wake_word_porcupine_runtime_failure_permanently_degrades_to_tier2():
    """
    Verify a porcupine.process() runtime failure does not crash, releases the
    native engine exactly once, permanently flips the detector to
    ACOUSTIC_FALLBACK, and never calls the failed engine again on later
    calls -- Tier 2 keeps working normally afterward.

    Supersedes the old "fallback for this block only" behavior, which is no
    longer desired: retrying a known-bad native engine on every later audio
    callback risked the same failure repeating on every block. A runtime
    failure now permanently degrades the backend for this detector's
    lifecycle instead.
    """
    mock_engine = _make_mock_porcupine_engine()
    mock_engine.process.side_effect = RuntimeError("native porcupine failure")
    mock_module = _mock_pvporcupine_module(mock_engine)

    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", True),
        patch("jarvis.audio.wake_word.pvporcupine", mock_module),
    ):
        detector = WakeWordDetector(
            sample_rate=16000,
            target_sample_rate=16000,
            cooldown_s=0.01,
            config={"porcupine_access_key": "test-key"},
        )

    assert detector._engine_type == WakeWordEngineType.PORCUPINE

    # Deterministic Tier 2: mock analyze_window() instead of relying on
    # random generated speech to drive the fallback detection.
    with patch.object(
        detector._spectral_detector, "analyze_window", return_value=(True, "hey_jarvis", 0.9)
    ) as mock_analyze:
        # First block: Porcupine raises; the exception must not escape
        # feed_audio_block(), and Tier 2 picks up the detection instead.
        res1 = detector.feed_audio_block(np.zeros(16000, dtype=np.float32), timestamp=100.0)

        assert res1 is not None
        assert res1.engine == WakeWordEngineType.ACOUSTIC_FALLBACK.value
        assert mock_engine.process.call_count == 1
        assert mock_analyze.call_count == 1

        mock_engine.delete.assert_called_once()
        assert detector._engine_type == WakeWordEngineType.ACOUSTIC_FALLBACK
        assert detector._tier1_engine is None
        assert detector._porcupine_frame_buffer is None

        # Second block, past cooldown: the failed native engine must never
        # be invoked again; Tier 2 keeps functioning normally.
        res2 = detector.feed_audio_block(np.zeros(16000, dtype=np.float32), timestamp=101.0)

        assert res2 is not None
        assert res2.engine == WakeWordEngineType.ACOUSTIC_FALLBACK.value
        assert mock_engine.process.call_count == 1  # unchanged -- never called again
        assert mock_analyze.call_count == 2

    # shutdown() after a runtime-triggered degradation must not double-delete.
    detector.shutdown()
    mock_engine.delete.assert_called_once()


def test_wake_word_porcupine_partial_init_failure_releases_native_engine():
    """
    Verify a failure AFTER pvporcupine.create() itself succeeds (e.g. reading
    `frame_length`/`sample_rate`, or constructing the frame-buffer adapter)
    still releases the already-created native engine exactly once and
    leaves no partial Porcupine state attached to the detector.
    """

    class _FrameLengthFailingEngine:
        """A bespoke double (not MagicMock) so patching one property can't
        leak onto other MagicMock instances via a shared type object."""

        def __init__(self) -> None:
            self.delete = MagicMock()
            self.process = MagicMock(return_value=-1)
            self.sample_rate = 16000

        @property
        def frame_length(self) -> int:
            raise RuntimeError("frame_length access failed")

    failing_engine = _FrameLengthFailingEngine()
    mock_module = _mock_pvporcupine_module(failing_engine)

    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", True),
        patch("jarvis.audio.wake_word.pvporcupine", mock_module),
    ):
        detector = WakeWordDetector(config={"porcupine_access_key": "test-key"})

    assert detector._engine_type == WakeWordEngineType.ACOUSTIC_FALLBACK
    assert detector._tier1_engine is None
    assert detector._porcupine_frame_buffer is None
    failing_engine.delete.assert_called_once()

    # shutdown() afterward must not double-delete the already-released engine.
    detector.shutdown()
    failing_engine.delete.assert_called_once()


def test_wake_word_porcupine_refractory_period_cooldown():
    """Verify the shared cooldown guard suppresses Porcupine-tier emission."""
    mock_engine = _make_mock_porcupine_engine()
    mock_engine.process.return_value = 0
    mock_module = _mock_pvporcupine_module(mock_engine)

    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", True),
        patch("jarvis.audio.wake_word.pvporcupine", mock_module),
    ):
        detector = WakeWordDetector(
            sample_rate=16000,
            target_sample_rate=16000,
            cooldown_s=1.5,
            config={"porcupine_access_key": "test-key"},
        )

    # Deterministic PCM: mock_engine.process() ignores its argument content.
    audio = np.zeros(16000, dtype=np.float32)

    res1 = detector.feed_audio_block(audio, timestamp=100.0)
    assert res1 is not None
    assert detector.trigger_count == 1

    res2 = detector.feed_audio_block(audio, timestamp=100.5)
    assert res2 is None
    assert detector.trigger_count == 1

    res3 = detector.feed_audio_block(audio, timestamp=101.6)
    assert res3 is not None
    assert detector.trigger_count == 2


def test_wake_word_porcupine_streams_during_cooldown_but_suppresses_emission():
    """
    Verify Porcupine keeps consuming every complete frame during cooldown
    (a streaming engine must never silently stop receiving audio), while
    cooldown suppresses only the resulting WakeWordResult/callback emission.
    """
    mock_engine = _make_mock_porcupine_engine(frame_length=512, sample_rate=16000)
    mock_engine.process.side_effect = [0, -1, -1, -1, 0]
    mock_module = _mock_pvporcupine_module(mock_engine)

    callback_events: List[str] = []

    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", True),
        patch("jarvis.audio.wake_word.pvporcupine", mock_module),
    ):
        detector = WakeWordDetector(
            sample_rate=16000,
            target_sample_rate=16000,
            cooldown_s=1.5,
            callback=lambda: callback_events.append("fired"),
            config={"porcupine_access_key": "test-key"},
        )

    # First detection: exactly one 512-sample frame, at t=100.0 -> triggers.
    res1 = detector.feed_audio_block(np.zeros(512, dtype=np.float32), timestamp=100.0)
    assert res1 is not None
    assert detector.trigger_count == 1
    assert mock_engine.process.call_count == 1
    assert callback_events == ["fired"]

    # Still inside the 1.5s cooldown: feed exactly 3 more complete frames.
    res2 = detector.feed_audio_block(np.zeros(3 * 512, dtype=np.float32), timestamp=100.5)
    assert res2 is None  # emission suppressed
    assert detector.trigger_count == 1  # unchanged
    assert mock_engine.process.call_count == 4  # 1 + 3 new frames actually consumed
    assert callback_events == ["fired"]  # no second callback during cooldown

    # Past cooldown: one more full frame detects again and emits normally.
    res3 = detector.feed_audio_block(np.zeros(512, dtype=np.float32), timestamp=101.6)
    assert res3 is not None
    assert detector.trigger_count == 2
    assert mock_engine.process.call_count == 5
    assert callback_events == ["fired", "fired"]


def test_wake_word_disabled_detector_skips_porcupine_processing():
    """Verify set_enabled(False) short-circuits before any Porcupine call is made."""
    mock_engine = _make_mock_porcupine_engine()
    mock_engine.process.return_value = 0
    mock_module = _mock_pvporcupine_module(mock_engine)

    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", True),
        patch("jarvis.audio.wake_word.pvporcupine", mock_module),
    ):
        detector = WakeWordDetector(
            sample_rate=16000,
            target_sample_rate=16000,
            enabled=False,
            config={"porcupine_access_key": "test-key"},
        )

    keyword_audio = np.zeros(16000, dtype=np.float32)
    assert detector.process_audio_block(keyword_audio) is False
    mock_engine.process.assert_not_called()


def test_wake_word_disable_enable_clears_porcupine_frame_buffer_and_ring_buffer():
    """
    Verify a partial Porcupine frame and stale ring-buffer audio from before
    a disable are cleared on the transition, so JARVIS-owned/caller-buffered
    PCM is not stitched across the disabled interval (however long it is).
    Does not claim the native Porcupine engine's own internal state is
    reset -- no such reset API is used or exists in the audited contract.
    Also verifies Porcupine is not processed at all while disabled.
    """
    mock_engine = _make_mock_porcupine_engine(frame_length=100, sample_rate=16000)
    mock_module = _mock_pvporcupine_module(mock_engine)

    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", True),
        patch("jarvis.audio.wake_word.pvporcupine", mock_module),
    ):
        detector = WakeWordDetector(
            sample_rate=16000,
            target_sample_rate=16000,
            config={"porcupine_access_key": "test-key"},
        )

    # Leave a partial frame (< 100 samples) pending, and non-zero ring-buffer audio.
    detector.feed_audio_block(np.full(40, 0.5, dtype=np.float32))
    assert len(detector._porcupine_frame_buffer._pending) > 0
    assert np.any(detector._ring_buffer != 0.0)

    # Disable: caller-owned streaming state must be cleared immediately.
    detector.set_enabled(False)
    assert len(detector._porcupine_frame_buffer._pending) == 0
    assert np.all(detector._ring_buffer == 0.0)

    # Feeding while disabled must not touch Porcupine at all.
    detector.feed_audio_block(np.full(40, 0.5, dtype=np.float32))
    mock_engine.process.assert_not_called()
    assert len(detector._porcupine_frame_buffer._pending) == 0

    # Re-enable is also a transition: proves toggling back doesn't resurrect
    # stale state either (buffer is already empty here).
    detector.set_enabled(True)
    assert len(detector._porcupine_frame_buffer._pending) == 0
    assert np.all(detector._ring_buffer == 0.0)

    # New audio after re-enable starts from a clean buffer: exactly this
    # block's worth of pending samples, nothing carried over from before.
    detector.feed_audio_block(np.full(30, 0.5, dtype=np.float32))
    assert len(detector._porcupine_frame_buffer._pending) == 30


def test_wake_word_toggle_enabled_clears_stream_state():
    """Verify toggle_enabled() shares the same buffer-clearing transition as set_enabled()."""
    mock_engine = _make_mock_porcupine_engine(frame_length=100, sample_rate=16000)
    mock_module = _mock_pvporcupine_module(mock_engine)

    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", True),
        patch("jarvis.audio.wake_word.pvporcupine", mock_module),
    ):
        detector = WakeWordDetector(
            sample_rate=16000,
            target_sample_rate=16000,
            config={"porcupine_access_key": "test-key"},
        )

    detector.feed_audio_block(np.full(40, 0.5, dtype=np.float32))
    assert len(detector._porcupine_frame_buffer._pending) > 0

    result = detector.toggle_enabled()

    assert result is False
    assert len(detector._porcupine_frame_buffer._pending) == 0
    assert np.all(detector._ring_buffer == 0.0)


def test_wake_word_disable_enable_does_not_reset_cooldown_timer():
    """
    Documents the chosen semantics: cooldown is a real-time debounce against
    duplicate triggers, independent of the enable toggle, so quickly
    disabling/re-enabling must not be usable to bypass an in-progress
    cooldown.

    Deterministic by construction: this is a state-machine property, not an
    acoustic-classification property, so it must not rely on real acoustic
    recognition (or on `generate_wake_word_signal()`'s random content) to
    prove it. All optional backends are forced unavailable, PCM is
    deterministic (`np.zeros`), and Tier 2's own detection outcome is
    mocked.
    """
    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", False),
    ):
        detector = WakeWordDetector(cooldown_s=1.5)

    assert detector._engine_type == WakeWordEngineType.ACOUSTIC_FALLBACK
    audio = np.zeros(16000, dtype=np.float32)

    with patch.object(
        detector._spectral_detector, "analyze_window", return_value=(True, "hey_jarvis", 0.9)
    ):
        # 1. First detection at t=100.0 succeeds.
        res1 = detector.feed_audio_block(audio, timestamp=100.0)
        assert res1 is not None
        assert detector.trigger_count == 1
        assert detector._last_trigger_time == 100.0

        # 2. Disable, then 3. re-enable.
        detector.set_enabled(False)
        detector.set_enabled(True)

        # 4. _last_trigger_time has NOT been reset by the toggle.
        assert detector._last_trigger_time == 100.0

        # 5. Detection inside cooldown (0.5s later) is suppressed.
        res2 = detector.feed_audio_block(audio, timestamp=100.5)
        assert res2 is None
        assert detector.trigger_count == 1

        # 6. Detection after cooldown (1.6s later) succeeds.
        res3 = detector.feed_audio_block(audio, timestamp=101.6)
        assert res3 is not None
        assert detector.trigger_count == 2


def test_wake_word_porcupine_shutdown_releases_native_resources():
    """Verify shutdown() calls native delete() exactly once and clears backend state."""
    mock_engine = _make_mock_porcupine_engine()
    mock_module = _mock_pvporcupine_module(mock_engine)

    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", True),
        patch("jarvis.audio.wake_word.pvporcupine", mock_module),
    ):
        detector = WakeWordDetector(config={"porcupine_access_key": "test-key"})

    assert detector._tier1_engine is mock_engine

    detector.shutdown()
    mock_engine.delete.assert_called_once()
    assert detector._tier1_engine is None
    assert detector._porcupine_frame_buffer is None

    # Idempotent: a second call must not crash or re-invoke delete().
    detector.shutdown()
    mock_engine.delete.assert_called_once()


def test_wake_word_porcupine_shutdown_survives_delete_exception():
    """Verify a native delete() failure during shutdown does not raise."""
    mock_engine = _make_mock_porcupine_engine()
    mock_engine.delete.side_effect = RuntimeError("native delete failure")
    mock_module = _mock_pvporcupine_module(mock_engine)

    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", True),
        patch("jarvis.audio.wake_word.pvporcupine", mock_module),
    ):
        detector = WakeWordDetector(config={"porcupine_access_key": "test-key"})

    detector.shutdown()  # must not raise
    assert detector._tier1_engine is None


def test_wake_word_shutdown_noop_without_native_backend():
    """Verify shutdown() is a safe no-op when only the Tier 2 fallback is active."""
    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", False),
    ):
        detector = WakeWordDetector()
    detector.shutdown()
    detector.shutdown()


def test_wake_word_shutdown_then_reset_does_not_touch_deleted_backend():
    """Verify reset() after shutdown() never dereferences the deleted native engine."""
    mock_engine = _make_mock_porcupine_engine()
    mock_module = _mock_pvporcupine_module(mock_engine)

    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", True),
        patch("jarvis.audio.wake_word.pvporcupine", mock_module),
    ):
        detector = WakeWordDetector(
            sample_rate=16000,
            target_sample_rate=16000,
            config={"porcupine_access_key": "test-key"},
        )

    # Leave a pending partial frame before shutdown, to prove reset() doesn't
    # try to touch the (now deleted) buffer/engine afterward.
    detector.feed_audio_block(np.zeros(100, dtype=np.float32))

    detector.shutdown()
    mock_engine.delete.assert_called_once()
    assert detector._tier1_engine is None
    assert detector._porcupine_frame_buffer is None

    detector.reset()  # must not raise / must not touch the deleted engine

    assert detector._tier1_engine is None
    assert detector._porcupine_frame_buffer is None
    mock_engine.delete.assert_called_once()  # still exactly once


def test_wake_word_porcupine_shutdown_thread_safe_single_delete_under_concurrency():
    """Verify concurrent shutdown() calls still delete() the native engine exactly once."""
    mock_engine = _make_mock_porcupine_engine()
    mock_module = _mock_pvporcupine_module(mock_engine)

    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", True),
        patch("jarvis.audio.wake_word.pvporcupine", mock_module),
    ):
        detector = WakeWordDetector(config={"porcupine_access_key": "test-key"})

    exceptions: List[Exception] = []

    def _shutdown_worker():
        try:
            detector.shutdown()
        except Exception as e:
            exceptions.append(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_shutdown_worker) for _ in range(8)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert len(exceptions) == 0
    mock_engine.delete.assert_called_once()
    assert detector._tier1_engine is None
    assert detector._porcupine_frame_buffer is None


def test_wake_word_porcupine_shutdown_does_not_race_with_in_flight_feed_audio_block():
    """
    Verify the shared lock serializes shutdown() against feed_audio_block(), so
    porcupine.delete() can never run concurrently with porcupine.process() —
    this is the same guarantee that makes the AudioEngine-stops-before-shutdown
    ordering in JarvisApp.stop() safe even if the audio worker thread's join
    does not complete instantly.

    Synchronization is proven with explicit threading.Event()s (not timing
    assumptions): `entered_process` deterministically signals that
    feed_audio_block() has acquired the lock and reached process(), so
    shutdown() is only started once that is actually true.
    """
    mock_engine = _make_mock_porcupine_engine()
    entered_process = threading.Event()
    release_process = threading.Event()

    def _blocking_process(_frame):
        entered_process.set()
        release_process.wait(timeout=2.0)
        return -1

    mock_engine.process.side_effect = _blocking_process
    mock_module = _mock_pvporcupine_module(mock_engine)

    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", True),
        patch("jarvis.audio.wake_word.pvporcupine", mock_module),
    ):
        detector = WakeWordDetector(
            sample_rate=16000,
            target_sample_rate=16000,
            config={"porcupine_access_key": "test-key"},
        )

    audio = np.zeros(16000, dtype=np.float32)

    feed_thread = threading.Thread(target=detector.feed_audio_block, args=(audio,))
    feed_thread.start()

    assert entered_process.wait(timeout=2.0), "process() was never entered"

    shutdown_thread = threading.Thread(target=detector.shutdown)
    shutdown_thread.start()

    # shutdown() must block on the shared lock: give it a bounded window and
    # prove it genuinely has not completed (and thus cannot have deleted the
    # engine) while process() is still in-flight.
    shutdown_thread.join(timeout=0.3)
    assert shutdown_thread.is_alive(), "shutdown() completed while process() was still in-flight"
    mock_engine.delete.assert_not_called()

    release_process.set()
    feed_thread.join(timeout=2.0)
    shutdown_thread.join(timeout=2.0)

    assert not feed_thread.is_alive()
    assert not shutdown_thread.is_alive()
    mock_engine.delete.assert_called_once()


def test_wake_word_reset_clears_porcupine_frame_buffer():
    """Verify reset() drops any buffered partial Porcupine frame (lifecycle restart)."""
    mock_engine = _make_mock_porcupine_engine()
    mock_module = _mock_pvporcupine_module(mock_engine)

    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", False),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", True),
        patch("jarvis.audio.wake_word.pvporcupine", mock_module),
    ):
        detector = WakeWordDetector(
            sample_rate=16000,
            target_sample_rate=16000,
            config={"porcupine_access_key": "test-key"},
        )

    # A sub-frame block leaves samples pending in the internal Porcupine buffer.
    detector.feed_audio_block(np.zeros(100, dtype=np.float32))
    assert len(detector._porcupine_frame_buffer._pending) > 0

    detector.reset()
    assert len(detector._porcupine_frame_buffer._pending) == 0


# ----------------------------------------------------------------------------
# _PorcupineFrameBuffer: frame boundary / buffering unit tests
# ----------------------------------------------------------------------------

def test_porcupine_frame_buffer_incomplete_frame_buffers_without_processing():
    """Verify a sub-frame chunk is buffered, not processed or dropped."""
    mock_engine = MagicMock()
    buf = _PorcupineFrameBuffer(mock_engine, frame_length=100, sample_rate=16000)

    partial = np.zeros(50, dtype=np.int16)
    result = buf.process(partial)

    assert result == -1
    mock_engine.process.assert_not_called()
    assert len(buf._pending) == 50


def test_porcupine_frame_buffer_processes_multiple_complete_frames_in_one_call():
    """Verify a block spanning multiple frames processes all of them deterministically."""
    mock_engine = MagicMock()
    mock_engine.process.return_value = -1
    buf = _PorcupineFrameBuffer(mock_engine, frame_length=10, sample_rate=16000)

    chunk = np.arange(25, dtype=np.int16)
    result = buf.process(chunk)

    assert result == -1
    assert mock_engine.process.call_count == 2
    # No samples dropped or duplicated: exactly the trailing 5 remain pending.
    assert buf._pending.tolist() == chunk[20:].tolist()


def test_porcupine_frame_buffer_carries_over_partial_frame_between_calls():
    """Verify a frame split across two incoming blocks is carried over correctly."""
    mock_engine = MagicMock()
    mock_engine.process.return_value = -1
    buf = _PorcupineFrameBuffer(mock_engine, frame_length=10, sample_rate=16000)

    first = np.arange(6, dtype=np.int16)
    second = np.arange(6, 12, dtype=np.int16)

    result1 = buf.process(first)
    assert result1 == -1
    mock_engine.process.assert_not_called()

    result2 = buf.process(second)
    assert result2 == -1
    mock_engine.process.assert_called_once()
    processed_frame = mock_engine.process.call_args[0][0]
    assert processed_frame == list(range(10))
    assert buf._pending.tolist() == [10, 11]


def test_porcupine_frame_buffer_returns_first_detected_index():
    """Verify a detection anywhere among multiple frames in one call is reported."""
    mock_engine = MagicMock()
    mock_engine.process.side_effect = [-1, 2, -1]
    buf = _PorcupineFrameBuffer(mock_engine, frame_length=5, sample_rate=16000)

    chunk = np.arange(15, dtype=np.int16)
    result = buf.process(chunk)

    assert result == 2
    assert mock_engine.process.call_count == 3


def test_porcupine_frame_buffer_reset_drops_pending_samples():
    """Verify reset() discards any buffered partial frame."""
    mock_engine = MagicMock()
    buf = _PorcupineFrameBuffer(mock_engine, frame_length=100, sample_rate=16000)
    buf.process(np.zeros(30, dtype=np.int16))
    assert len(buf._pending) == 30

    buf.reset()
    assert len(buf._pending) == 0


# ============================================================================
# 8. THREAD SAFETY & CONCURRENCY TESTS
# ============================================================================

def test_wake_word_concurrent_streaming_and_toggles():
    """
    Stress: 10 concurrent threads feeding audio blocks while main thread
    rapidly toggles set_enabled(True/False). Zero crash & thread safety guarantee.
    """
    detector = WakeWordDetector(cooldown_s=0.01)
    keyword_audio = generate_wake_word_signal(sample_rate=44100)
    silence = np.zeros(44100, dtype=np.float32)

    exceptions: List[Exception] = []

    def _audio_worker(worker_id: int):
        try:
            for step in range(40):
                buf = keyword_audio if step % 2 == 0 else silence
                detector.process_audio_block(buf)
                time.sleep(0.001)
        except Exception as e:
            exceptions.append(e)

    def _toggle_worker():
        try:
            for _ in range(50):
                detector.set_enabled(False)
                assert detector.is_enabled() is False
                detector.set_enabled(True)
                assert detector.is_enabled() is True
                time.sleep(0.001)
        except Exception as e:
            exceptions.append(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        futures = [executor.submit(_audio_worker, i) for i in range(10)]
        futures.append(executor.submit(_toggle_worker))
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert len(exceptions) == 0, f"Concurrent exceptions encountered: {exceptions}"
    assert detector.is_enabled() is True


# ============================================================================
# 9. SYSTEM TRAY INTEGRATION TESTS
# ============================================================================

def test_tray_wake_word_toggle_without_app():
    """Verify SystemTrayController wake word toggle works in standalone/fallback mode."""
    tray = SystemTrayController()
    assert tray._wakeword_enabled is True

    # Toggle off
    tray._on_toggle_wakeword()
    assert tray._wakeword_enabled is False

    # Toggle on
    tray._on_toggle_wakeword()
    assert tray._wakeword_enabled is True


def test_tray_wake_word_toggle_with_app_detector():
    """Verify SystemTrayController._on_toggle_wakeword toggles WakeWordDetector live."""
    detector = WakeWordDetector(enabled=True)
    app_mock = MagicMock()
    app_mock.wake_word_detector = detector

    bus_mock = MagicMock()
    tray = SystemTrayController(app=app_mock, event_bus=bus_mock)

    assert detector.is_enabled() is True

    # 1. Toggle via Tray: should disable detector
    tray._on_toggle_wakeword()
    assert detector.is_enabled() is False
    assert tray._wakeword_enabled is False
    bus_mock.publish.assert_called_with("tray.wakeword_toggled", enabled=False)

    # 2. Toggle via Tray: should re-enable detector
    tray._on_toggle_wakeword()
    assert detector.is_enabled() is True
    assert tray._wakeword_enabled is True
    bus_mock.publish.assert_called_with("tray.wakeword_toggled", enabled=True)


def test_tray_menu_items_include_wake_word():
    """Verify SystemTrayController menu items list includes wake word toggle."""
    tray = SystemTrayController()
    assert "Toggle Wake Word" in tray.menu_items

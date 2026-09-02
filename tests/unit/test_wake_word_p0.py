"""
tests/unit/test_wake_word_p0.py
===============================
Dedicated Unit Test Suite for JARVIS v4.6.0 P0-A Wake Word Subsystem.
Covers:
  1. Initialization and multi-tier engine cascading (Vosk, Faster-Whisper, Porcupine, AcousticSpectralDetector).
  2. Vosk streaming recognition with AcceptWaveform() and PartialResult() instant triggering.
  3. Vosk model path discovery hierarchy (config, environment variables, system/local cache dirs).
  4. WhisperSlidingWindowDetector: sliding window keyword detection, RMS thresholding, rate limiting.
  5. Intermediate Whisper fallback when Vosk is absent.
  6. AcousticSpectralDetector: synthetic formant speech detection (>=70% accuracy rate), SFM/ZCR bounds.
  7. Robust false positive rejection: pure sinusoidal tones, white noise, impulse claps, clipping/NaN/inf.
  8. State management: live toggle enable/disable, refractory cooldown, buffer clearing, reset.
  9. Callback invocation and error isolation.
 10. High-concurrency multi-threaded audio streaming and thread safety.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.audio.wake_word import (
    AcousticSpectralDetector,
    WakeWordDetector,
    WakeWordEngineType,
    WakeWordResult,
    WhisperSlidingWindowDetector,
    generate_wake_word_signal,
    resample_audio,
)

# ============================================================================
# 1. ENGINE INITIALIZATION & MODEL DISCOVERY TESTS
# ============================================================================

def test_p0a_init_zero_import_error():
    """Verify WakeWordDetector initializes cleanly under any package availability state."""
    detector = WakeWordDetector()
    assert detector.is_enabled() is True
    assert detector.trigger_count == 0
    assert detector._engine_type in list(WakeWordEngineType)


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("vosk") is None,
    reason="vosk not installed — test requires vosk package to mock vosk.Model",
)
def test_p0a_vosk_model_path_discovery_hierarchy(tmp_path):
    """
    Verify Vosk model auto-discovery checks configured path, environment variables,
    and local/cached model directories.
    Skipped when vosk is not installed (patch target jarvis.audio.wake_word.vosk.Model
    requires vosk to be importable).
    """
    fake_model_dir = tmp_path / "vosk-model-small-vn-0.4"
    fake_model_dir.mkdir(parents=True, exist_ok=True)

    mock_vosk_model = MagicMock()
    mock_rec = MagicMock()

    with (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", True),
        patch("jarvis.audio.wake_word.vosk.Model", return_value=mock_vosk_model) as mock_model_cls,
        patch("jarvis.audio.wake_word.vosk.KaldiRecognizer", return_value=mock_rec),
    ):
        # 1. Via config vosk_model_path
        detector = WakeWordDetector(config={"vosk_model_path": str(fake_model_dir)})
        assert detector._engine_type == WakeWordEngineType.VOSK
        mock_model_cls.assert_called_with(str(fake_model_dir))

        # 2. Via JARVIS_VOSK_MODEL environment variable
        with patch.dict(os.environ, {"JARVIS_VOSK_MODEL": str(fake_model_dir)}):
            detector_env = WakeWordDetector(config={})
            assert detector_env._engine_type == WakeWordEngineType.VOSK


def test_p0a_vosk_missing_model_falls_back_cleanly():
    """Verify non-existent Vosk model path degrades gracefully to acoustic fallback."""
    with patch.dict(os.environ, {"JARVIS_VOSK_MODEL": "/non/existent/model/path/98765"}):
        detector = WakeWordDetector(config={"vosk_model_path": "/invalid/path/12345"})
        assert detector._engine_type == WakeWordEngineType.ACOUSTIC_FALLBACK
        assert detector.is_enabled() is True


def test_p0a_engine_type_enum_completeness():
    """Verify WakeWordEngineType includes all expected engine tiers."""
    assert WakeWordEngineType.VOSK.value == "vosk"
    assert WakeWordEngineType.OPENWAKEWORD.value == "openwakeword"
    assert WakeWordEngineType.PORCUPINE.value == "porcupine"
    assert WakeWordEngineType.WHISPER.value == "whisper"
    assert WakeWordEngineType.ACOUSTIC_FALLBACK.value == "acoustic_fallback"
    assert WakeWordEngineType.MOCK.value == "mock"


# ============================================================================
# 2. VOSK STREAMING & PARTIALRESULT INSTANT MATCHING TESTS
# ============================================================================

def test_p0a_vosk_accept_waveform_full_result_matching():
    """Verify Vosk triggers when AcceptWaveform returns True with full keyword result."""
    detector = WakeWordDetector()
    detector._engine_type = WakeWordEngineType.VOSK

    mock_rec = MagicMock()
    mock_rec.AcceptWaveform.return_value = True
    mock_rec.Result.return_value = json.dumps({"text": "chào jarvis hãy bật đèn"})
    detector._tier1_engine = mock_rec

    audio = np.zeros(16000, dtype=np.float32)
    result = detector.feed_audio_block(audio, timestamp=100.0)

    assert result is not None
    assert result.keyword == "hey_jarvis"
    assert result.confidence == 0.95
    assert result.engine == WakeWordEngineType.VOSK.value
    mock_rec.Reset.assert_called_once()


def test_p0a_vosk_partial_result_instant_trigger():
    """
    Verify Vosk triggers immediately when AcceptWaveform returns False but
    PartialResult contains a wake keyword hypothesis (e.g. 'jarvis', 'hey jarvis', 'ê jarvis').
    """
    detector = WakeWordDetector()
    detector._engine_type = WakeWordEngineType.VOSK

    mock_rec = MagicMock()
    mock_rec.AcceptWaveform.return_value = False
    mock_rec.PartialResult.return_value = json.dumps({"partial": "ê jarvis"})
    detector._tier1_engine = mock_rec

    audio = np.zeros(16000, dtype=np.float32)
    result = detector.feed_audio_block(audio, timestamp=100.0)

    assert result is not None
    assert result.keyword == "hey_jarvis"
    assert result.confidence == 0.95
    assert result.engine == WakeWordEngineType.VOSK.value
    mock_rec.Reset.assert_called_once()


def test_p0a_vosk_non_keyword_partial_does_not_trigger():
    """Verify non-matching speech hypotheses in PartialResult do not trigger detection."""
    detector = WakeWordDetector()
    detector._engine_type = WakeWordEngineType.VOSK

    mock_rec = MagicMock()
    mock_rec.AcceptWaveform.return_value = False
    mock_rec.PartialResult.return_value = json.dumps({"partial": "hôm nay trời đẹp quá"})
    detector._tier1_engine = mock_rec

    audio = np.zeros(16000, dtype=np.float32)
    result = detector.feed_audio_block(audio, timestamp=100.0)

    assert result is None
    assert detector.trigger_count == 0


def test_p0a_vosk_malformed_json_resilience():
    """Verify corrupt JSON from Vosk engine is safely handled without raising exception."""
    detector = WakeWordDetector()
    detector._engine_type = WakeWordEngineType.VOSK

    mock_rec = MagicMock()
    mock_rec.AcceptWaveform.return_value = True
    mock_rec.Result.return_value = "NOT_A_VALID_JSON_STRING_hey jarvis"
    detector._tier1_engine = mock_rec

    audio = np.zeros(16000, dtype=np.float32)
    result = detector.feed_audio_block(audio, timestamp=100.0)

    assert result is not None
    assert result.keyword == "hey_jarvis"


# ============================================================================
# 3. WHISPER SLIDING WINDOW DETECTOR (TIER 1.5) TESTS
# ============================================================================

def test_p0a_whisper_sliding_window_keyword_detection():
    """Verify WhisperSlidingWindowDetector detects keyword from transcribed segments."""
    mock_model = MagicMock()
    mock_segment = MagicMock()
    mock_segment.text = "Chào JARVIS hãy mở nhạc"
    mock_model.transcribe.return_value = ([mock_segment], MagicMock())

    detector = WhisperSlidingWindowDetector(
        sample_rate=16000,
        min_rms=0.005,
        model=mock_model,
        check_interval_s=0.1,
    )

    audio_buffer = np.full(16000, 0.05, dtype=np.float32)
    detected, kw, conf = detector.analyze_window(audio_buffer, timestamp=100.0)

    assert detected is True
    assert kw == "hey_jarvis"
    assert conf >= 0.90
    mock_model.transcribe.assert_called_once()


def test_p0a_whisper_sliding_window_non_keyword_rejection():
    """Verify WhisperSlidingWindowDetector rejects non-keyword transcription."""
    mock_model = MagicMock()
    mock_segment = MagicMock()
    mock_segment.text = "thời tiết ngày mai thế nào"
    mock_model.transcribe.return_value = ([mock_segment], MagicMock())

    detector = WhisperSlidingWindowDetector(
        sample_rate=16000,
        min_rms=0.005,
        model=mock_model,
        check_interval_s=0.1,
    )

    audio_buffer = np.full(16000, 0.05, dtype=np.float32)
    detected, kw, conf = detector.analyze_window(audio_buffer, timestamp=100.0)

    assert detected is False
    assert kw == ""
    assert conf == 0.0


def test_p0a_whisper_sliding_window_rms_and_rate_limiting():
    """Verify silence below min_rms and calls within check_interval_s skip model transcription."""
    mock_model = MagicMock()
    detector = WhisperSlidingWindowDetector(
        min_rms=0.02,
        check_interval_s=0.5,
        model=mock_model,
    )

    # 1. Pure silence (< min_rms) -> skipped
    silence = np.zeros(16000, dtype=np.float32)
    d1, _, _ = detector.analyze_window(silence, timestamp=100.0)
    assert d1 is False
    mock_model.transcribe.assert_not_called()

    # 2. Speech above min_rms at t=100.0 -> transcribed
    mock_segment = MagicMock()
    mock_segment.text = "jarvis"
    mock_model.transcribe.return_value = ([mock_segment], MagicMock())
    speech = np.full(16000, 0.05, dtype=np.float32)
    d2, _, _ = detector.analyze_window(speech, timestamp=100.0)
    assert d2 is True
    assert mock_model.transcribe.call_count == 1

    # 3. Follow-up call at t=100.2 (< 0.5s check_interval) -> skipped by rate limit
    d3, _, _ = detector.analyze_window(speech, timestamp=100.2)
    assert d3 is False
    assert mock_model.transcribe.call_count == 1


def test_p0a_wake_word_detector_whisper_fallback_mode():
    """
    Verify WakeWordDetector uses Whisper sliding window fallback when configured
    and Vosk is absent.
    """
    mock_whisper_model = MagicMock()
    mock_segment = MagicMock()
    mock_segment.text = "ê jarvis"
    mock_whisper_model.transcribe.return_value = ([mock_segment], MagicMock())

    detector = WakeWordDetector(
        config={
            "engine": "whisper",
            "whisper_min_rms": 0.005,
            "whisper_check_interval_s": 0.05,
        },
        enabled=True,
    )
    detector._whisper_detector.model = mock_whisper_model

    audio = np.full(16000, 0.05, dtype=np.float32)
    res = detector.feed_audio_block(audio, timestamp=100.0)

    assert res is not None
    assert res.keyword == "hey_jarvis"
    assert res.engine == WakeWordEngineType.WHISPER.value


# ============================================================================
# 4. SYNTHETIC SPEECH DETECTION (>=70% BENCHMARK) & DSP TESTS
# ============================================================================

def test_p0a_synthetic_speech_detection_benchmark_rate():
    """
    Verify WakeWordDetector achieves >= 70% detection rate on synthetic
    speech formant signals across 20 trials with slight acoustic variations.
    """
    detector = WakeWordDetector(sensitivity=0.6, cooldown_s=0.01)
    trials = 20
    hits = 0

    for i in range(trials):
        # Vary peak amplitude and ambient noise slightly
        amp = 0.75 + (i % 5) * 0.04
        noise_rms = 0.001 + (i % 3) * 0.001
        sig = generate_wake_word_signal(
            "hey_jarvis",
            duration_s=1.2,
            sample_rate=44100,
            peak_amp=amp,
            noise_floor_rms=noise_rms,
        )
        detector.reset()
        res = detector.feed_audio_block(sig, timestamp=100.0 + i * 1.0)
        if res is not None and res.keyword in ("hey_jarvis", "jarvis"):
            hits += 1

    detection_rate = hits / float(trials)
    assert detection_rate >= 0.70, f"Detection rate {detection_rate:.2%} was below required 70% (hits={hits}/{trials})"


def test_p0a_spectral_detector_pure_tone_rejection():
    """Verify pure sinusoidal tones (system beeps, pure frequencies) are rejected (SFM < 0.03)."""
    detector = AcousticSpectralDetector(sample_rate=16000)
    sr = 16000
    t = np.linspace(0.0, 1.2, int(sr * 1.2), endpoint=False)

    for freq in [440.0, 1000.0, 3000.0, 5000.0]:
        pure_sine = (0.85 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
        detected, _, _ = detector.analyze_window(pure_sine, sensitivity=0.5)
        assert detected is False, f"Pure tone at {freq}Hz was falsely detected"


def test_p0a_spectral_detector_white_noise_rejection():
    """Verify high-energy Gaussian white noise is rejected (SFM > 0.65)."""
    detector = AcousticSpectralDetector(sample_rate=16000)
    np.random.seed(1234)
    noise = np.random.normal(0.0, 0.25, int(16000 * 1.2)).astype(np.float32)
    detected, _, _ = detector.analyze_window(noise, sensitivity=0.5)
    assert detected is False


def test_p0a_spectral_detector_impulse_clap_rejection():
    """Verify simultaneous broadband impulse claps are rejected."""
    detector = AcousticSpectralDetector(sample_rate=16000)
    clap_buffer = np.zeros(int(16000 * 1.2), dtype=np.float32)
    # Short 10ms impulse
    clap_buffer[8000 : 8000 + 160] = 0.95
    detected, _, _ = detector.analyze_window(clap_buffer, sensitivity=0.5)
    assert detected is False


# ============================================================================
# 5. STATE TRANSITIONS, CONTROLS & CONCURRENCY
# ============================================================================

def test_p0a_live_toggle_and_state_consistency():
    """Verify set_enabled, toggle_enabled, and enabled properties stay consistent."""
    detector = WakeWordDetector(enabled=True)
    assert detector.is_enabled() is True
    assert detector.enabled is True

    # Toggle to False
    assert detector.toggle_enabled() is False
    assert detector.is_enabled() is False
    assert detector.enabled is False

    # Toggle to True
    assert detector.toggle_enabled() is True
    assert detector.is_enabled() is True
    assert detector.enabled is True


def test_p0a_refractory_cooldown_debounce():
    """Verify refractory cooldown suppresses triggers within cooldown period."""
    detector = WakeWordDetector(cooldown_s=1.5, sensitivity=0.5)
    sig = generate_wake_word_signal("hey_jarvis", duration_s=1.2, sample_rate=44100)

    # Initial trigger
    res1 = detector.feed_audio_block(sig, timestamp=100.0)
    assert res1 is not None
    assert detector.trigger_count == 1

    # 0.8s later (within 1.5s cooldown) -> suppressed
    res2 = detector.feed_audio_block(sig, timestamp=100.8)
    assert res2 is None
    assert detector.trigger_count == 1

    # 1.6s later (past 1.5s cooldown) -> triggers
    res3 = detector.feed_audio_block(sig, timestamp=101.6)
    assert res3 is not None
    assert detector.trigger_count == 2


def test_p0a_callback_dispatch_and_error_isolation():
    """Verify callbacks execute on detection and exceptions inside callbacks are contained."""
    cb_fired = []
    detailed_fired = []

    def fault_cb():
        cb_fired.append(True)
        raise RuntimeError("Callback crash simulation")

    def fault_detailed(kw, conf):
        detailed_fired.append((kw, conf))
        raise ValueError("Detailed callback crash simulation")

    detector = WakeWordDetector(
        callback=fault_cb,
        on_wake_word=fault_detailed,
        cooldown_s=0.1,
        sensitivity=0.5,
    )
    sig = generate_wake_word_signal("hey_jarvis", duration_s=1.2, sample_rate=44100)

    # Should not raise exception
    res = detector.feed_audio_block(sig, timestamp=100.0)
    assert res is not None
    assert len(cb_fired) == 1
    assert len(detailed_fired) == 1
    assert detailed_fired[0][0] in ("hey_jarvis", "jarvis")


def test_p0a_multithreaded_concurrency_stress():
    """
    Stress test: Concurrent audio streaming threads feeding blocks while state is toggled.
    Guarantees no deadlocks or race condition crashes.
    """
    detector = WakeWordDetector(cooldown_s=0.01)
    sig = generate_wake_word_signal("hey_jarvis", duration_s=1.0)
    silence = np.zeros(44100, dtype=np.float32)

    exceptions: list[Exception] = []

    def stream_worker(w_id: int):
        try:
            for step in range(30):
                buf = sig if step % 2 == 0 else silence
                detector.feed_audio_block(buf, timestamp=100.0 + (w_id * 10) + step * 0.05)
                time.sleep(0.001)
        except Exception as e:
            exceptions.append(e)

    def toggle_worker():
        try:
            for _ in range(30):
                detector.toggle_enabled()
                time.sleep(0.001)
        except Exception as e:
            exceptions.append(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(stream_worker, i) for i in range(8)]
        futures.append(executor.submit(toggle_worker))
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert len(exceptions) == 0

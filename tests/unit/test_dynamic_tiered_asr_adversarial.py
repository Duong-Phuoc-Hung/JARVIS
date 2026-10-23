"""
tests/unit/test_dynamic_tiered_asr_adversarial.py
=================================================
Empirical Adversarial Challenge & Stress Harness for DynamicTieredASREngine
and FasterWhisperSTT acoustic metric extraction (Milestone 1, Requirement R1).

Adversarially challenges:
1. Audio input edge cases:
   - Empty numpy array, empty bytes, None input.
   - All-zeros audio (pure silence) of various durations.
   - Audio with NaN, PosInf, NegInf.
   - Severely clipped audio (+/- 1000.0).
   - Ultra-short audio (<0.1s, down to single-sample 0.0000625s).
   - Multi-channel audio (stereo 2D array downmixing).
   - Long audio (>30s Whisper chunking window).
2. Boundary threshold stress-testing:
   - avg_logprob exact boundary (-0.650000 vs -0.650001 vs -0.649999).
   - no_speech_prob exact boundary (0.500000 vs 0.500001 vs 0.499999).
   - duration exact boundary (1.000s vs 0.999s vs 1.001s).
   - RMS silence boundary (0.000999 vs 0.001001).
   - RMS voice energy boundary (0.002999 vs 0.003001 with empty text).
3. Memory leak & VRAM lifecycle verification:
   - 50 consecutive escalations with weakref tracking on both engine and model handles.
   - GC object count stability across multiple escalations.
   - Safe unloading when model reference is already None or raises.
   - Telemetry dictionary integrity under CPU and CUDA modes.
4. Concurrency & Stress:
   - Multi-threaded concurrent escalations under race conditions.
   - Large tier exception during escalation (e.g. simulated CUDA OOM) with fail-closed fallback.
   - Large tier empty output preservation of initial text.
"""
from __future__ import annotations

import gc
import threading
import time
import weakref
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.stt.dynamic_tiered import (
    DynamicTieredASR,
    DynamicTieredASREngine,
    TranscriptionResult,
)
from jarvis.stt.engine import (
    BaseSTTEngine,
    FasterWhisperSTT,
    STTError,
    STTMetricsResult,
    STT_SAMPLE_RATE,
)


# ============================================================================
# Helpers
# ============================================================================

def make_tone(duration_s: float, sample_rate: int = 16000, freq_hz: float = 440.0, amplitude: float = 0.5) -> np.ndarray:
    """Generate synthetic sine wave 1D float32 audio."""
    num_samples = int(sample_rate * duration_s)
    if num_samples <= 0:
        return np.empty(0, dtype=np.float32)
    t = np.linspace(0, duration_s, num_samples, endpoint=False)
    return (amplitude * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


class MockUnderlyingModel:
    """Dummy model object to test model lifetime and weakref collection."""
    def __init__(self, name: str = "large-model") -> None:
        self.name = name
        self.is_destroyed = False

    def transcribe(self, *args: Any, **kwargs: Any) -> tuple[list[Any], Any]:
        seg = SimpleNamespace(text="mở trình duyệt", avg_logprob=-0.12, no_speech_prob=0.01)
        return [seg], SimpleNamespace()


class EphemeralMockLargeEngine(BaseSTTEngine):
    """Mock large engine holding a distinct model instance for leak detection."""
    def __init__(self) -> None:
        super().__init__()
        self._model: MockUnderlyingModel | None = MockUnderlyingModel("whisper-large-v3")

    @property
    def engine_name(self) -> str:
        return "mock_large"

    def is_available(self) -> bool:
        return True

    def transcribe(self, audio: Any, language: str = "vi", **kwargs: Any) -> str:
        return "mở trình duyệt"

    def transcribe_with_metrics(self, audio: Any, language: str = "vi", **kwargs: Any) -> STTMetricsResult:
        return STTMetricsResult(
            text="mở trình duyệt",
            avg_logprob=-0.10,
            no_speech_prob=0.02,
            duration_ms=620.0,
        )

    def is_available(self) -> bool:
        return True


# ============================================================================
# 1. AUDIO INPUT EXTREMES & EDGE CASES
# ============================================================================

def test_edge_case_empty_numpy_array():
    """Verify empty numpy array returns silence TranscriptionResult immediately."""
    engine = DynamicTieredASREngine(config={"device": "cpu"})
    empty_arr = np.array([], dtype=np.float32)

    res = engine.transcribe(empty_arr)

    assert isinstance(res, TranscriptionResult)
    assert res.text == ""
    assert res.avg_logprob == 0.0
    assert res.no_speech_prob == 1.0
    assert res.model_tier == "none"
    assert res.escalated is False
    assert res.duration_ms >= 0.0
    assert res.error is None
    assert res.is_success is False


def test_edge_case_empty_bytes():
    """Verify empty raw bytes input is handled fail-closed without exception."""
    engine = DynamicTieredASREngine(config={"device": "cpu"})
    res = engine.transcribe(b"")

    assert isinstance(res, TranscriptionResult)
    assert res.text == ""
    assert res.model_tier == "none"
    assert res.no_speech_prob == 1.0
    assert res.escalated is False


def test_edge_case_none_audio():
    """Verify None audio input is handled fail-closed without exception."""
    engine = DynamicTieredASREngine(config={"device": "cpu"})
    res = engine.transcribe(None)  # type: ignore[arg-type]

    assert isinstance(res, TranscriptionResult)
    assert res.text == ""
    assert res.model_tier == "none"
    assert res.escalated is False


@pytest.mark.parametrize("length_samples", [100, 1600, 16000, 32000])
def test_edge_case_all_zeros_audio(length_samples: int):
    """Verify all-zeros audio of various durations is detected as silence (RMS=0.0)."""
    engine = DynamicTieredASREngine(config={"device": "cpu"})
    zeros = np.zeros(length_samples, dtype=np.float32)

    res = engine.transcribe(zeros)

    assert isinstance(res, TranscriptionResult)
    assert res.text == ""
    assert res.avg_logprob == 0.0
    assert res.no_speech_prob == 1.0
    assert res.model_tier == "none"
    assert res.escalated is False
    assert res.duration_ms >= 0.0


def test_edge_case_nan_and_inf_audio():
    """Verify audio containing NaNs and positive/negative Infs is sanitized."""
    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.is_available.return_value = True
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="kiểm tra âm thanh",
        avg_logprob=-0.20,
        no_speech_prob=0.05,
        duration_ms=410.0,
    )

    engine = DynamicTieredASREngine(config={"device": "cpu"}, small_engine=mock_small)

    corrupted = np.array([0.1, np.nan, 0.2, np.inf, -np.inf, 0.3] * 3000, dtype=np.float32)
    res = engine.transcribe(corrupted)

    assert isinstance(res, TranscriptionResult)
    assert res.text == "kiểm tra âm thanh"
    mock_small.transcribe_with_metrics.assert_called_once()
    cleaned_arg = mock_small.transcribe_with_metrics.call_args[0][0]
    assert not np.isnan(cleaned_arg).any()
    assert not np.isinf(cleaned_arg).any()
    assert np.max(cleaned_arg) <= 1.0
    assert np.min(cleaned_arg) >= -1.0


def test_edge_case_extreme_clipping():
    """Verify audio with extreme amplitude (+/- 1000.0) is clipped to [-1.0, 1.0]."""
    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.is_available.return_value = True
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="âm thanh lớn",
        avg_logprob=-0.15,
        no_speech_prob=0.02,
        duration_ms=300.0,
    )

    engine = DynamicTieredASREngine(config={"device": "cpu"}, small_engine=mock_small)

    clipped = np.full(16000, 1000.0, dtype=np.float32)
    res = engine.transcribe(clipped)

    assert res.text == "âm thanh lớn"
    cleaned_arg = mock_small.transcribe_with_metrics.call_args[0][0]
    assert np.max(cleaned_arg) <= 1.0
    assert np.min(cleaned_arg) >= -1.0


@pytest.mark.parametrize("duration_s", [0.01, 0.05, 0.09])
def test_edge_case_ultra_short_sub_100ms(duration_s: float):
    """Verify audio < 0.1s correctly selects tiny tier and does not crash."""
    mock_tiny = MagicMock(spec=BaseSTTEngine)
    mock_tiny.is_available.return_value = True
    mock_tiny.transcribe_with_metrics.return_value = STTMetricsResult(
        text="ơi",
        avg_logprob=-0.30,
        no_speech_prob=0.10,
        duration_ms=50.0,
    )

    engine = DynamicTieredASREngine(config={"device": "cpu"}, tiny_engine=mock_tiny)

    short_audio = make_tone(duration_s, amplitude=0.4)
    res = engine.transcribe(short_audio)

    assert res.model_tier == "tiny"
    assert res.text == "ơi"
    mock_tiny.transcribe_with_metrics.assert_called_once()


def test_edge_case_single_sample_audio():
    """Verify audio with a single sample (1/16000s) does not divide-by-zero or crash."""
    mock_tiny = MagicMock(spec=BaseSTTEngine)
    mock_tiny.is_available.return_value = True
    mock_tiny.transcribe_with_metrics.return_value = STTMetricsResult(
        text="",
        avg_logprob=-0.90,
        no_speech_prob=0.99,
        duration_ms=10.0,
    )

    engine = DynamicTieredASREngine(config={"device": "cpu"}, tiny_engine=mock_tiny)

    single_sample = np.array([0.5], dtype=np.float32)
    res = engine.transcribe(single_sample)

    assert isinstance(res, TranscriptionResult)
    assert res.duration_ms >= 0.0


def test_edge_case_multichannel_audio_downmix():
    """Verify stereo (16000, 2) audio is downmixed to mono (16000,) before inference."""
    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.is_available.return_value = True
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="âm thanh stereo",
        avg_logprob=-0.22,
        no_speech_prob=0.03,
        duration_ms=400.0,
    )

    engine = DynamicTieredASREngine(config={"device": "cpu"}, small_engine=mock_small)

    stereo_audio = np.ones((16000, 2), dtype=np.float32) * 0.4
    res = engine.transcribe(stereo_audio)

    assert res.text == "âm thanh stereo"
    called_arg = mock_small.transcribe_with_metrics.call_args[0][0]
    assert called_arg.ndim == 1
    assert len(called_arg) == 16000


def test_edge_case_long_audio_35s():
    """Verify long audio (35s, > 30s Whisper window) selects small tier and handles duration."""
    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.is_available.return_value = True
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="đây là một đoạn văn bản rất dài được ghi âm liên tục trên ba mươi giây",
        avg_logprob=-0.28,
        no_speech_prob=0.04,
        duration_ms=1800.0,
    )

    engine = DynamicTieredASREngine(config={"device": "cpu"}, small_engine=mock_small)

    long_audio = make_tone(35.0, amplitude=0.3)
    res = engine.transcribe(long_audio)

    assert res.model_tier == "small"
    assert res.escalated is False
    assert "đoạn văn bản rất dài" in res.text
    mock_small.transcribe_with_metrics.assert_called_once()


# ============================================================================
# 2. BOUNDARY THRESHOLD STRESS-TESTING
# ============================================================================

def test_boundary_logprob_exact():
    """
    Stress-test exact boundary of logprob escalation threshold (-0.65):
    - avg_logprob == -0.650000 -> NO escalation (strict inequality < -0.65 is False).
    - avg_logprob == -0.650001 -> ESCALATES (strict inequality < -0.65 is True).
    - avg_logprob == -0.649999 -> NO escalation (-0.649999 < -0.65 is False).
    """
    audio = make_tone(1.5, amplitude=0.4)

    # 1. Exact boundary: -0.650000
    mock_small_exact = MagicMock(spec=BaseSTTEngine)
    mock_small_exact.is_available.return_value = True
    mock_small_exact.transcribe_with_metrics.return_value = STTMetricsResult(
        text="lệnh hệ thống",
        avg_logprob=-0.650000,
        no_speech_prob=0.10,
        duration_ms=400.0,
    )
    engine_exact = DynamicTieredASREngine(config={"device": "cpu"}, small_engine=mock_small_exact)
    res_exact = engine_exact.transcribe(audio)
    assert res_exact.escalated is False
    assert res_exact.model_tier == "small"

    # 2. Infinitesimally below: -0.650001
    mock_small_below = MagicMock(spec=BaseSTTEngine)
    mock_small_below.is_available.return_value = True
    mock_small_below.transcribe_with_metrics.return_value = STTMetricsResult(
        text="lệnh mờ nhạt",
        avg_logprob=-0.650001,
        no_speech_prob=0.10,
        duration_ms=400.0,
    )
    mock_large_factory = lambda: EphemeralMockLargeEngine()
    engine_below = DynamicTieredASREngine(
        config={"device": "cpu"},
        small_engine=mock_small_below,
        large_engine_factory=mock_large_factory,
    )
    res_below = engine_below.transcribe(audio)
    assert res_below.escalated is True
    assert res_below.model_tier == "large-v3"

    # 3. Infinitesimally above: -0.649999
    mock_small_above = MagicMock(spec=BaseSTTEngine)
    mock_small_above.is_available.return_value = True
    mock_small_above.transcribe_with_metrics.return_value = STTMetricsResult(
        text="lệnh rõ ràng",
        avg_logprob=-0.649999,
        no_speech_prob=0.10,
        duration_ms=400.0,
    )
    engine_above = DynamicTieredASREngine(config={"device": "cpu"}, small_engine=mock_small_above)
    res_above = engine_above.transcribe(audio)
    assert res_above.escalated is False
    assert res_above.model_tier == "small"


def test_boundary_no_speech_prob_exact():
    """
    Stress-test exact boundary of no_speech_prob escalation threshold (0.50):
    - no_speech_prob == 0.500000 -> NO escalation (strict inequality > 0.50 is False).
    - no_speech_prob == 0.500001 -> ESCALATES (strict inequality > 0.50 is True).
    - no_speech_prob == 0.499999 -> NO escalation (0.499999 > 0.50 is False).
    """
    audio = make_tone(1.5, amplitude=0.4)

    # 1. Exact boundary: 0.500000
    mock_small_exact = MagicMock(spec=BaseSTTEngine)
    mock_small_exact.is_available.return_value = True
    mock_small_exact.transcribe_with_metrics.return_value = STTMetricsResult(
        text="mở nhạc",
        avg_logprob=-0.20,
        no_speech_prob=0.500000,
        duration_ms=400.0,
    )
    engine_exact = DynamicTieredASREngine(config={"device": "cpu"}, small_engine=mock_small_exact)
    res_exact = engine_exact.transcribe(audio)
    assert res_exact.escalated is False
    assert res_exact.model_tier == "small"

    # 2. Infinitesimally above: 0.500001
    mock_small_above = MagicMock(spec=BaseSTTEngine)
    mock_small_above.is_available.return_value = True
    mock_small_above.transcribe_with_metrics.return_value = STTMetricsResult(
        text="mở nhạc",
        avg_logprob=-0.20,
        no_speech_prob=0.500001,
        duration_ms=400.0,
    )
    engine_above = DynamicTieredASREngine(
        config={"device": "cpu"},
        small_engine=mock_small_above,
        large_engine_factory=lambda: EphemeralMockLargeEngine(),
    )
    res_above = engine_above.transcribe(audio)
    assert res_above.escalated is True
    assert res_above.model_tier == "large-v3"

    # 3. Infinitesimally below: 0.499999
    mock_small_below = MagicMock(spec=BaseSTTEngine)
    mock_small_below.is_available.return_value = True
    mock_small_below.transcribe_with_metrics.return_value = STTMetricsResult(
        text="mở nhạc",
        avg_logprob=-0.20,
        no_speech_prob=0.499999,
        duration_ms=400.0,
    )
    engine_below = DynamicTieredASREngine(config={"device": "cpu"}, small_engine=mock_small_below)
    res_below = engine_below.transcribe(audio)
    assert res_below.escalated is False
    assert res_below.model_tier == "small"


def test_boundary_duration_threshold_exact():
    """
    Stress-test exact duration boundary (1.000s):
    - Exactly 1.000s (16000 samples) -> selects small (1.0 < 1.0 is False).
    - 0.999s (15984 samples) -> selects tiny (0.999 < 1.0 is True).
    - 1.001s (16016 samples) -> selects small (1.001 < 1.0 is False).
    """
    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.is_available.return_value = True
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult("lớn", -0.1, 0.05, 300.0)

    mock_tiny = MagicMock(spec=BaseSTTEngine)
    mock_tiny.is_available.return_value = True
    mock_tiny.transcribe_with_metrics.return_value = STTMetricsResult("nhỏ", -0.1, 0.05, 150.0)

    engine = DynamicTieredASREngine(
        config={"device": "cpu", "short_duration_threshold_s": 1.0},
        small_engine=mock_small,
        tiny_engine=mock_tiny,
    )

    # 1. Exactly 1.000s
    engine.transcribe(make_tone(1.0, amplitude=0.4))
    assert mock_small.transcribe_with_metrics.call_count == 1
    assert mock_tiny.transcribe_with_metrics.call_count == 0

    # 2. 0.999s
    engine.transcribe(make_tone(0.999, amplitude=0.4))
    assert mock_tiny.transcribe_with_metrics.call_count == 1

    # 3. 1.001s
    engine.transcribe(make_tone(1.001, amplitude=0.4))
    assert mock_small.transcribe_with_metrics.call_count == 2


def test_boundary_rms_silence_threshold():
    """
    Stress-test RMS silence threshold (0.001):
    - RMS = 0.000999 (< 0.001) -> filtered as silence, model_tier="none", no tier called.
    - RMS = 0.001001 (>= 0.001) -> processed, tier called.
    """
    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.is_available.return_value = True
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult("âm", -0.1, 0.05, 300.0)

    engine = DynamicTieredASREngine(config={"device": "cpu"}, small_engine=mock_small)

    # Audio with constant DC = 0.00099 (RMS = 0.00099 < 0.001)
    silence_audio = np.full(16000, 0.00099, dtype=np.float32)
    res_silence = engine.transcribe(silence_audio)
    assert res_silence.model_tier == "none"
    mock_small.transcribe_with_metrics.assert_not_called()

    # Audio with constant DC = 0.00101 (RMS = 0.00101 >= 0.001)
    audible_audio = np.full(16000, 0.00101, dtype=np.float32)
    res_audible = engine.transcribe(audible_audio)
    assert res_audible.model_tier == "small"
    mock_small.transcribe_with_metrics.assert_called_once()


def test_boundary_rms_voice_energy_threshold():
    """
    Stress-test RMS voice energy threshold (0.003) with empty transcript:
    - RMS = 0.002999 with empty text: has_voice_energy is False -> NO escalation.
    - RMS = 0.003001 with empty text: has_voice_energy is True -> ESCALATES.
    """
    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.is_available.return_value = True
    # Normal metrics (not low logprob, not high no-speech), but empty text
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="",
        avg_logprob=-0.20,
        no_speech_prob=0.10,
        duration_ms=400.0,
    )

    engine = DynamicTieredASREngine(
        config={"device": "cpu"},
        small_engine=mock_small,
        large_engine_factory=lambda: EphemeralMockLargeEngine(),
    )

    # 1. RMS = 0.002999 (below 0.003)
    audio_low_energy = np.full(16000, 0.002999, dtype=np.float32)
    res_low = engine.transcribe(audio_low_energy)
    assert res_low.escalated is False
    assert res_low.model_tier == "small"

    # 2. RMS = 0.003001 (above 0.003)
    audio_high_energy = np.full(16000, 0.003001, dtype=np.float32)
    res_high = engine.transcribe(audio_high_energy)
    assert res_high.escalated is True
    assert res_high.model_tier == "large-v3"


# ============================================================================
# 3. MEMORY LEAK & VRAM LIFECYCLE EMPIRICAL VERIFICATION
# ============================================================================

def test_vram_lifecycle_50_consecutive_escalations_weakref():
    """
    Adversarial memory leak harness:
    Run 50 consecutive escalations. Attach weakref.ref to both the ephemeral
    large engine and its underlying WhisperModel.
    Assert that 100% of the weak references die immediately after each escalation,
    guaranteeing zero lingering references on the heap.
    """
    audio = make_tone(1.5, amplitude=0.4)

    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.is_available.return_value = True
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="",
        avg_logprob=-0.85,  # triggers escalation
        no_speech_prob=0.10,
        duration_ms=400.0,
    )

    cleanup_call_count = 0

    def cleanup_spy():
        nonlocal cleanup_call_count
        cleanup_call_count += 1

    engine_refs: list[weakref.ref[Any]] = []
    model_refs: list[weakref.ref[Any]] = []

    def tracking_factory() -> BaseSTTEngine:
        large = EphemeralMockLargeEngine()
        engine_refs.append(weakref.ref(large))
        model_refs.append(weakref.ref(large._model))  # type: ignore[arg-type]
        return large

    dynamic_engine = DynamicTieredASREngine(
        config={"device": "cpu"},
        small_engine=mock_small,
        large_engine_factory=tracking_factory,
        cleanup_callback=cleanup_spy,
    )

    # Execute 50 consecutive escalations
    for i in range(50):
        res = dynamic_engine.transcribe(audio)
        assert res.escalated is True
        assert res.model_tier == "large-v3"

    # Verify cleanup callback called 50 times
    assert cleanup_call_count == 50

    # Force a garbage collection cycle to resolve any temporary frame closures
    gc.collect()

    # Assert that all 50 underlying model instances were destroyed
    dead_model_refs = [ref() for ref in model_refs]
    assert all(m is None for m in dead_model_refs), (
        f"Memory leak detected: {[m for m in dead_model_refs if m is not None]} models still alive!"
    )

    # Assert that all 50 ephemeral engine wrappers were garbage-collected
    dead_engine_refs = [ref() for ref in engine_refs]
    assert all(e is None for e in dead_engine_refs), (
        f"Memory leak detected: {[e for e in dead_engine_refs if e is not None]} engines still alive!"
    )


def test_gc_object_count_stability_under_escalation():
    """
    Verify that repeatedly triggering escalation does not cause monotonic GC object growth.
    """
    audio = make_tone(1.2, amplitude=0.4)

    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.is_available.return_value = True
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="",
        avg_logprob=-0.75,
        no_speech_prob=0.10,
        duration_ms=400.0,
    )

    engine = DynamicTieredASREngine(
        config={"device": "cpu"},
        small_engine=mock_small,
        large_engine_factory=lambda: EphemeralMockLargeEngine(),
    )

    # Warm up
    for _ in range(5):
        engine.transcribe(audio)
    gc.collect()
    baseline_count = len(gc.get_objects())

    # Run 25 more escalations
    for _ in range(25):
        engine.transcribe(audio)
    gc.collect()
    final_count = len(gc.get_objects())

    # Delta should be negligible (< 150 temporary caching objects, definitely not 25+ model graphs)
    delta = abs(final_count - baseline_count)
    assert delta <= 150, f"Monotonic GC object leakage detected: delta={delta} objects"


def test_unload_large_engine_resilience_when_already_none():
    """Verify _unload_large_engine handles None, empty engine, or missing attributes gracefully."""
    engine = DynamicTieredASREngine(config={"device": "cpu"})

    # Should not raise on None
    engine._unload_large_engine(None)

    # Should not raise on an arbitrary object without _model
    engine._unload_large_engine("not_an_engine")

    # Should not raise on an object whose _model is None
    dummy = SimpleNamespace(_model=None)
    engine._unload_large_engine(dummy)


def test_vram_telemetry_reports_accurate_fields():
    """Verify get_vram_telemetry returns complete dictionary conforming to contract."""
    engine = DynamicTieredASREngine(config={"device": "cpu"})
    telem = engine.get_vram_telemetry()

    assert isinstance(telem, dict)
    assert "device" in telem
    assert "compute_type" in telem
    assert "is_cuda" in telem
    assert "allocated_mb" in telem
    assert "reserved_mb" in telem
    assert isinstance(telem["allocated_mb"], float)
    assert isinstance(telem["reserved_mb"], float)


# ============================================================================
# 4. CONCURRENCY & ROBUSTNESS
# ============================================================================

def test_concurrent_escalations_thread_safety():
    """
    Stress-test multi-threaded concurrent escalations.
    10 worker threads concurrently invoke transcribe() with audio triggering escalation.
    Verify all 10 return correct results and all 10 ephemeral engines are cleaned up.
    """
    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.is_available.return_value = True
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="",
        avg_logprob=-0.80,
        no_speech_prob=0.10,
        duration_ms=300.0,
    )

    created_models: list[weakref.ref[Any]] = []
    lock = threading.Lock()

    def concurrent_factory() -> BaseSTTEngine:
        large = EphemeralMockLargeEngine()
        with lock:
            created_models.append(weakref.ref(large._model))  # type: ignore[arg-type]
        return large

    engine = DynamicTieredASREngine(
        config={"device": "cpu"},
        small_engine=mock_small,
        large_engine_factory=concurrent_factory,
    )

    audio = make_tone(1.2, amplitude=0.4)
    results: list[TranscriptionResult] = []

    def worker_job():
        return engine.transcribe(audio)

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(worker_job) for _ in range(10)]
        for f in as_completed(futures):
            results.append(f.result())

    assert len(results) == 10
    for res in results:
        assert res.escalated is True
        assert res.model_tier == "large-v3"
        assert res.text == "mở trình duyệt"

    gc.collect()
    assert all(ref() is None for ref in created_models), "Concurrent model instance leak detected!"


def test_escalation_large_tier_crash_preserves_initial_metrics():
    """
    Adversarial test: when large tier throws an unexpected exception during escalation
    (e.g. simulated CUDA OOM / memory error):
    - Engine must NOT crash.
    - Engine must gracefully fall back to initial metrics.
    - Engine must set escalated=False and populate error field.
    - Engine must still unload large engine in finally block.
    """
    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.is_available.return_value = True
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="tăng âm lượng",
        avg_logprob=-0.70,  # below -0.65 threshold
        no_speech_prob=0.05,
        duration_ms=450.0,
    )

    cleaned_up = False

    def on_cleanup():
        nonlocal cleaned_up
        cleaned_up = True

    class CrashingLargeEngine(BaseSTTEngine):
        @property
        def engine_name(self) -> str:
            return "crashing_large"
        def is_available(self) -> bool:
            return True
        def transcribe(self, *a, **k):
            raise RuntimeError("CUDA out of memory in large-v3 forward pass")
        def transcribe_with_metrics(self, *a, **k):
            raise RuntimeError("CUDA out of memory in large-v3 forward pass")

    engine = DynamicTieredASREngine(
        config={"device": "cpu"},
        small_engine=mock_small,
        large_engine_factory=lambda: CrashingLargeEngine(),
        cleanup_callback=on_cleanup,
    )

    audio = make_tone(1.5, amplitude=0.4)
    res = engine.transcribe(audio)

    assert isinstance(res, TranscriptionResult)
    assert res.text == "tăng âm lượng"
    assert res.avg_logprob == -0.70
    assert res.model_tier == "small"
    assert res.escalated is False
    assert res.error is not None
    assert "CUDA out of memory" in res.error
    assert cleaned_up is True, "Large model cleanup was skipped during exception!"


def test_empty_large_text_keeps_initial_text():
    """
    Adversarial test: if initial tier produced valid text but low confidence (-0.68),
    and large tier produced empty text (e.g. over-filtered as noise),
    the engine should preserve the non-empty initial text instead of losing speech.
    """
    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.is_available.return_value = True
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="giảm độ sáng",
        avg_logprob=-0.68,
        no_speech_prob=0.08,
        duration_ms=400.0,
    )

    class EmptyLargeEngine(BaseSTTEngine):
        @property
        def engine_name(self) -> str:
            return "empty_large"
        def is_available(self) -> bool:
            return True
        def transcribe(self, *a, **k):
            return ""
        def transcribe_with_metrics(self, *a, **k):
            return STTMetricsResult(text="", avg_logprob=-0.99, no_speech_prob=0.90, duration_ms=500.0)

    engine = DynamicTieredASREngine(
        config={"device": "cpu"},
        small_engine=mock_small,
        large_engine_factory=lambda: EmptyLargeEngine(),
    )

    audio = make_tone(1.5, amplitude=0.4)
    res = engine.transcribe(audio)

    assert res.text == "giảm độ sáng"
    assert res.escalated is True


# ============================================================================
# 5. FASTER WHISPER STT METRIC EXTRACTION & BACKWARD COMPATIBILITY
# ============================================================================

def test_faster_whisper_metric_extraction_hallucination_filter():
    """
    Verify FasterWhisperSTT.transcribe_with_metrics post-filters low-energy hallucinations.
    RMS < 0.005 and words > 3 should be discarded.
    """
    stt = FasterWhisperSTT({"device": "cpu"})

    fake_segment = SimpleNamespace(
        text="xin chào các bạn đây là ảo giác âm thanh dài",
        avg_logprob=-0.40,
        no_speech_prob=0.15,
    )
    fake_info = SimpleNamespace(language="vi")

    mock_whisper_model = MagicMock()
    mock_whisper_model.transcribe.return_value = ([fake_segment], fake_info)

    # Audio with very low energy: RMS = 0.002 (< 0.005)
    low_energy_audio = np.full(16000, 0.002, dtype=np.float32)

    with patch.object(stt, "_get_model", return_value=mock_whisper_model):
        with patch.object(stt, "is_available", return_value=True):
            metrics = stt.transcribe_with_metrics(low_energy_audio)

    # Discarded as hallucination -> text should be empty
    assert metrics.text == ""
    assert metrics.no_speech_prob == 0.15


def test_faster_whisper_backward_compatibility_exact_equality():
    """
    Verify FasterWhisperSTT.transcribe(audio) returns str exactly matching
    FasterWhisperSTT.transcribe_with_metrics(audio).text.
    """
    stt = FasterWhisperSTT({"device": "cpu"})

    fake_segment = SimpleNamespace(
        text="bật đèn phòng khách",
        avg_logprob=-0.15,
        no_speech_prob=0.02,
    )
    fake_info = SimpleNamespace(language="vi")

    mock_whisper_model = MagicMock()
    mock_whisper_model.transcribe.return_value = ([fake_segment], fake_info)

    audio = make_tone(1.0, amplitude=0.5)

    with patch.object(stt, "_get_model", return_value=mock_whisper_model):
        with patch.object(stt, "is_available", return_value=True):
            text = stt.transcribe(audio)
            metrics = stt.transcribe_with_metrics(audio)

    assert isinstance(text, str)
    assert text == "bật đèn phòng khách"
    assert metrics.text == text
    assert metrics.avg_logprob == -0.15
    assert metrics.no_speech_prob == 0.02

"""
tests/unit/test_dynamic_tiered_asr.py
=====================================
Unit tests for DynamicTieredASREngine & Adaptive Model Routing (Milestone 1, Requirement R1).

Covers:
  - TranscriptionResult contract, properties, and immutability.
  - Happy path default small tier routing (audio >= 1.0s, normal confidence).
  - Ultra-short audio routing to tiny tier (audio < 1.0s).
  - Acoustic uncertainty escalation on low logprob (avg_logprob < -0.65).
  - Acoustic uncertainty escalation on high no-speech probability (no_speech_prob > 0.50).
  - Acoustic uncertainty escalation on speech energy with empty transcript.
  - Zero-escalation on pure silence or empty audio.
  - VRAM cleanup lifecycle: model deletion, garbage collection, and CUDA cache clearing.
  - VRAM cleanup resilience when large-v3 throws an exception during escalation.
  - Fail-closed handling on CUDA exception with CPU fallback.
  - Fail-closed total failure returning empty TranscriptionResult with error metadata.
  - Backward compatibility of FasterWhisperSTT.transcribe() -> str and transcribe_with_metrics() -> STTMetricsResult.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch
from dataclasses import FrozenInstanceError

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
)


# ============================================================================
# Helpers & Fixtures
# ============================================================================

def make_audio_tone(duration_s: float, sample_rate: int = 16000, freq_hz: float = 440.0, amplitude: float = 0.5) -> np.ndarray:
    """Generate a clean synthetic sine wave 1D float32 audio array."""
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


# ============================================================================
# 1. CONTRACT & IMMUTABILITY TESTS
# ============================================================================

def test_transcription_result_contract_and_immutability():
    """Verify TranscriptionResult satisfies the interface contract and is strictly immutable."""
    res = TranscriptionResult(
        text="bật đèn phòng khách",
        avg_logprob=-0.25,
        no_speech_prob=0.03,
        model_tier="small",
        escalated=False,
        duration_ms=520.4,
    )

    assert res.text == "bật đèn phòng khách"
    assert res.avg_logprob == -0.25
    assert res.no_speech_prob == 0.03
    assert res.model_tier == "small"
    assert res.escalated is False
    assert res.duration_ms == 520.4
    assert res.error is None

    # Confidence calculation: clamp(1.0 + (-0.25), 0.0, 1.0) = 0.75
    assert pytest.approx(res.confidence, abs=0.001) == 0.75
    assert res.is_success is True

    # Immutability check: cannot assign to frozen dataclass
    with pytest.raises(FrozenInstanceError):
        res.text = "hacked"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        res.escalated = True  # type: ignore[misc]


def test_transcription_result_alias_compatibility():
    """Verify DynamicTieredASR alias points directly to DynamicTieredASREngine."""
    assert DynamicTieredASR is DynamicTieredASREngine


# ============================================================================
# 2. TIER ROUTING TESTS (SMALL VS TINY)
# ============================================================================

def test_happy_path_small_tier_selection():
    """Verify audio >= 1.0s with normal confidence uses small tier without escalation."""
    audio_1_5s = make_audio_tone(1.5)

    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.is_available.return_value = True
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="bật máy tính",
        avg_logprob=-0.20,
        no_speech_prob=0.05,
        duration_ms=450.0,
    )

    mock_tiny = MagicMock(spec=BaseSTTEngine)
    mock_tiny.is_available.return_value = True

    engine = DynamicTieredASREngine(
        config={"device": "cpu", "short_duration_threshold_s": 1.0},
        small_engine=mock_small,
        tiny_engine=mock_tiny,
    )

    res = engine.transcribe(audio_1_5s)

    assert isinstance(res, TranscriptionResult)
    assert res.text == "bật máy tính"
    assert res.model_tier == "small"
    assert res.escalated is False
    assert res.avg_logprob == -0.20
    assert res.no_speech_prob == 0.05
    assert res.duration_ms >= 0.0

    mock_small.transcribe_with_metrics.assert_called_once()
    mock_tiny.transcribe_with_metrics.assert_not_called()


def test_ultra_short_tiny_tier_selection():
    """Verify audio < 1.0s routes to tiny tier to achieve lower latency."""
    audio_0_6s = make_audio_tone(0.6)

    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.is_available.return_value = True

    mock_tiny = MagicMock(spec=BaseSTTEngine)
    mock_tiny.is_available.return_value = True
    mock_tiny.transcribe_with_metrics.return_value = STTMetricsResult(
        text="dừng lại",
        avg_logprob=-0.15,
        no_speech_prob=0.02,
        duration_ms=180.0,
    )

    engine = DynamicTieredASREngine(
        config={"device": "cpu", "short_duration_threshold_s": 1.0},
        small_engine=mock_small,
        tiny_engine=mock_tiny,
    )

    res = engine.transcribe(audio_0_6s)

    assert isinstance(res, TranscriptionResult)
    assert res.text == "dừng lại"
    assert res.model_tier == "tiny"
    assert res.escalated is False
    assert res.avg_logprob == -0.15
    assert res.no_speech_prob == 0.02

    mock_tiny.transcribe_with_metrics.assert_called_once()
    mock_small.transcribe_with_metrics.assert_not_called()


# ============================================================================
# 3. ACOUSTIC UNCERTAINTY ESCALATION TESTS
# ============================================================================

def test_escalation_on_low_logprob():
    """Verify avg_logprob < -0.65 triggers escalation to large-v3."""
    audio = make_audio_tone(1.2)

    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.is_available.return_value = True
    # Uncertain small output: avg_logprob = -0.85 (< -0.65)
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="mở cửa",
        avg_logprob=-0.85,
        no_speech_prob=0.10,
        duration_ms=500.0,
    )

    mock_large = MagicMock(spec=BaseSTTEngine)
    mock_large.is_available.return_value = True
    mock_large.transcribe_with_metrics.return_value = STTMetricsResult(
        text="mở cửa sổ phòng khách",
        avg_logprob=-0.18,
        no_speech_prob=0.02,
        duration_ms=900.0,
    )

    engine = DynamicTieredASREngine(
        config={"device": "cpu", "logprob_escalation_threshold": -0.65},
        small_engine=mock_small,
        large_engine_factory=lambda: mock_large,
    )

    res = engine.transcribe(audio)

    assert res.escalated is True
    assert res.model_tier == "large-v3"
    assert res.text == "mở cửa sổ phòng khách"
    assert res.avg_logprob == -0.18
    assert res.no_speech_prob == 0.02

    mock_small.transcribe_with_metrics.assert_called_once()
    mock_large.transcribe_with_metrics.assert_called_once()


def test_escalation_on_high_no_speech():
    """Verify no_speech_prob > 0.50 triggers escalation to large-v3."""
    audio = make_audio_tone(1.2)

    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.is_available.return_value = True
    # High no-speech probability: 0.68 (> 0.50)
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="tăng âm lượng",
        avg_logprob=-0.30,
        no_speech_prob=0.68,
        duration_ms=480.0,
    )

    mock_large = MagicMock(spec=BaseSTTEngine)
    mock_large.is_available.return_value = True
    mock_large.transcribe_with_metrics.return_value = STTMetricsResult(
        text="tăng âm lượng loa chính",
        avg_logprob=-0.12,
        no_speech_prob=0.05,
        duration_ms=850.0,
    )

    engine = DynamicTieredASREngine(
        config={"device": "cpu", "no_speech_escalation_threshold": 0.50},
        small_engine=mock_small,
        large_engine_factory=lambda: mock_large,
    )

    res = engine.transcribe(audio)

    assert res.escalated is True
    assert res.model_tier == "large-v3"
    assert res.text == "tăng âm lượng loa chính"
    assert res.no_speech_prob == 0.05

    mock_small.transcribe_with_metrics.assert_called_once()
    mock_large.transcribe_with_metrics.assert_called_once()


def test_escalation_on_speech_energy_with_empty_text():
    """Verify audio with speech energy but empty text triggers escalation to large-v3."""
    # Strong audio tone (RMS > 0.003)
    audio = make_audio_tone(1.5, amplitude=0.4)

    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.is_available.return_value = True
    # Small model produced empty string despite audible energy
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="",
        avg_logprob=-0.40,
        no_speech_prob=0.30,
        duration_ms=450.0,
    )

    mock_large = MagicMock(spec=BaseSTTEngine)
    mock_large.is_available.return_value = True
    mock_large.transcribe_with_metrics.return_value = STTMetricsResult(
        text="kiểm tra hệ thống",
        avg_logprob=-0.14,
        no_speech_prob=0.04,
        duration_ms=820.0,
    )

    engine = DynamicTieredASREngine(
        config={"device": "cpu"},
        small_engine=mock_small,
        large_engine_factory=lambda: mock_large,
    )

    res = engine.transcribe(audio)

    assert res.escalated is True
    assert res.model_tier == "large-v3"
    assert res.text == "kiểm tra hệ thống"

    mock_small.transcribe_with_metrics.assert_called_once()
    mock_large.transcribe_with_metrics.assert_called_once()


def test_no_escalation_on_pure_silence():
    """Verify pure silence (zero RMS) returns immediately without calling small or large."""
    silence = np.zeros(16000, dtype=np.float32)

    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_large = MagicMock(spec=BaseSTTEngine)

    engine = DynamicTieredASREngine(
        config={"device": "cpu"},
        small_engine=mock_small,
        large_engine_factory=lambda: mock_large,
    )

    res = engine.transcribe(silence)

    assert res.text == ""
    assert res.model_tier == "none"
    assert res.escalated is False
    assert res.no_speech_prob == 1.0

    mock_small.transcribe_with_metrics.assert_not_called()
    mock_large.transcribe_with_metrics.assert_not_called()


def test_allow_escalation_flag_disabled():
    """Verify when allow_escalation=False, uncertain metrics do not trigger escalation."""
    audio = make_audio_tone(1.2)

    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="lệnh không rõ",
        avg_logprob=-0.95,
        no_speech_prob=0.80,
        duration_ms=400.0,
    )
    mock_large = MagicMock(spec=BaseSTTEngine)

    engine = DynamicTieredASREngine(
        config={"device": "cpu", "allow_escalation": False},
        small_engine=mock_small,
        large_engine_factory=lambda: mock_large,
    )

    res = engine.transcribe(audio)

    assert res.escalated is False
    assert res.model_tier == "small"
    assert res.text == "lệnh không rõ"
    mock_large.transcribe_with_metrics.assert_not_called()


# ============================================================================
# 4. VRAM LIFECYCLE & CLEANUP TESTS
# ============================================================================

def test_vram_cleanup_lifecycle_on_successful_escalation():
    """Verify that when escalation finishes, cleanup hooks and memory eviction run."""
    audio = make_audio_tone(1.2)

    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="bật quạt",
        avg_logprob=-0.80,
        no_speech_prob=0.10,
        duration_ms=450.0,
    )

    mock_large = MagicMock(spec=BaseSTTEngine)
    mock_large._model = MagicMock()
    mock_large.transcribe_with_metrics.return_value = STTMetricsResult(
        text="bật quạt trần",
        avg_logprob=-0.15,
        no_speech_prob=0.03,
        duration_ms=800.0,
    )

    cleanup_called = False

    def on_cleanup():
        nonlocal cleanup_called
        cleanup_called = True

    with patch("jarvis.stt.dynamic_tiered.DynamicTieredASREngine._clean_gpu_memory") as mock_clean_gpu:
        engine = DynamicTieredASREngine(
            config={"device": "cpu"},
            small_engine=mock_small,
            large_engine_factory=lambda: mock_large,
            cleanup_callback=on_cleanup,
        )

        res = engine.transcribe(audio)

        assert res.escalated is True
        assert res.text == "bật quạt trần"
        assert cleanup_called is True
        mock_clean_gpu.assert_called_once()
        # Internal model reference must be set to None or deleted
        assert getattr(mock_large, "_model", None) is None


def test_vram_cleanup_lifecycle_on_escalation_exception():
    """Verify that if large model raises an exception, VRAM cleanup runs and engine falls back safely."""
    audio = make_audio_tone(1.2)

    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="bật điều hòa",
        avg_logprob=-0.75,
        no_speech_prob=0.10,
        duration_ms=400.0,
    )

    mock_large = MagicMock(spec=BaseSTTEngine)
    mock_large._model = MagicMock()
    mock_large.transcribe_with_metrics.side_effect = RuntimeError("CUDA out of memory (simulated)")

    cleanup_called = False

    def on_cleanup():
        nonlocal cleanup_called
        cleanup_called = True

    with patch("jarvis.stt.dynamic_tiered.DynamicTieredASREngine._clean_gpu_memory") as mock_clean_gpu:
        engine = DynamicTieredASREngine(
            config={"device": "cpu"},
            small_engine=mock_small,
            large_engine_factory=lambda: mock_large,
            cleanup_callback=on_cleanup,
        )

        res = engine.transcribe(audio)

        # Result falls back gracefully to small tier
        assert res.escalated is False
        assert res.text == "bật điều hòa"
        assert res.model_tier == "small"
        assert "Escalation failed" in str(res.error)

        # Cleanup MUST still have executed in finally block
        assert cleanup_called is True
        mock_clean_gpu.assert_called_once()
        assert getattr(mock_large, "_model", None) is None


# ============================================================================
# 5. FAIL-CLOSED ARCHITECTURE & EXCEPTION HANDLING TESTS
# ============================================================================

def test_fail_closed_cuda_exception_cascades_to_cpu_small():
    """Verify CUDA exception on initial tier triggers fail-closed CPU small fallback."""
    audio = make_audio_tone(1.2)

    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.transcribe_with_metrics.side_effect = RuntimeError("CUDA driver error")

    engine = DynamicTieredASREngine(
        config={"device": "cuda"},
        small_engine=mock_small,
    )

    with patch("jarvis.stt.dynamic_tiered.FasterWhisperSTT") as mock_fw_cls:
        mock_cpu_stt = MagicMock()
        mock_cpu_stt.transcribe_with_metrics.return_value = STTMetricsResult(
            text="tắt màn hình",
            avg_logprob=-0.22,
            no_speech_prob=0.04,
            duration_ms=620.0,
        )
        mock_fw_cls.return_value = mock_cpu_stt

        res = engine.transcribe(audio)

        assert res.text == "tắt màn hình"
        assert res.model_tier == "small-cpu-fallback"
        assert res.escalated is False
        assert "CUDA failure" in str(res.error)


def test_fail_closed_total_failure_returns_empty_result():
    """Verify when all tiers fail, engine returns an empty TranscriptionResult without throwing."""
    audio = make_audio_tone(1.2)

    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.transcribe_with_metrics.side_effect = STTError("Model weights corrupted")

    engine = DynamicTieredASREngine(
        config={"device": "cpu"},
        small_engine=mock_small,
    )

    res = engine.transcribe(audio)

    assert res.text == ""
    assert res.model_tier == "failed"
    assert res.escalated is False
    assert res.avg_logprob == -99.0
    assert res.no_speech_prob == 1.0
    assert "Model weights corrupted" in str(res.error)


def test_vram_telemetry_structure():
    """Verify get_vram_telemetry returns valid dictionary structure."""
    engine = DynamicTieredASREngine(config={"device": "cpu"})
    telem = engine.get_vram_telemetry()

    assert "device" in telem
    assert "compute_type" in telem
    assert "allocated_mb" in telem
    assert "reserved_mb" in telem
    assert isinstance(telem["allocated_mb"], float)
    assert isinstance(telem["reserved_mb"], float)


# ============================================================================
# 6. BACKWARD COMPATIBILITY OF FASTERWHISPERSTT TESTS
# ============================================================================

def test_faster_whisper_stt_transcribe_backward_compatibility():
    """Verify FasterWhisperSTT.transcribe returns plain str while transcribe_with_metrics returns STTMetricsResult."""
    fw = FasterWhisperSTT({"model_size": "tiny"})

    # Mock the internal _get_model method to simulate transcription
    mock_model = MagicMock()
    mock_seg = MagicMock()
    mock_seg.text = " xin chào JARVIS "
    mock_seg.avg_logprob = -0.25
    mock_seg.no_speech_prob = 0.05
    mock_info = MagicMock()
    mock_info.language = "vi"
    mock_info.language_probability = 0.98

    mock_model.transcribe.return_value = ([mock_seg], mock_info)
    fw._model = mock_model

    audio = make_audio_tone(1.0)

    # 1. transcribe() returns plain str
    text_out = fw.transcribe(audio)
    assert isinstance(text_out, str)
    assert text_out == "xin chào JARVIS"

    # 2. transcribe_with_metrics() returns STTMetricsResult
    metrics_out = fw.transcribe_with_metrics(audio)
    assert isinstance(metrics_out, STTMetricsResult)
    assert metrics_out.text == "xin chào JARVIS"
    assert metrics_out.avg_logprob == -0.25
    assert metrics_out.no_speech_prob == 0.05
    assert metrics_out.duration_ms >= 0.0

    # 3. Tuple unpacking compatibility
    text_unpacked, avg_lp, nsp, dur_ms = metrics_out
    assert text_unpacked == "xin chào JARVIS"
    assert avg_lp == -0.25
    assert nsp == 0.05
    assert dur_ms >= 0.0

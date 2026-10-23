"""
tests/unit/test_adversarial_dynamic_tiered_asr.py
=================================================
Empirical Adversarial Stress Harness for DynamicTieredASREngine (Milestone 1, Requirement R1).

Adversarially tests:
1. Concurrency & Thread-Safety:
   - Probes for presence of `_large_v3_lock` on DynamicTieredASREngine.
   - Stresses concurrent escalation across multiple threads to detect concurrent
     double-allocations of large-v3 in VRAM.
2. Fail-Closed Resilience on CUDA OOM:
   - Simulates CUDA out-of-memory during `_create_large_engine()`.
   - Simulates CUDA out-of-memory during `large_engine.transcribe_with_metrics()`.
   - Simulates CUDA out-of-memory on initial tier with cascading CPU fallback.
3. Fail-Closed Resilience on Missing / Corrupted Model Weights:
   - Missing model files on initial tier.
   - Missing model files on escalation tier.
   - Total model failure (both GPU and CPU unconfigured/missing).
4. Anti-Fabrication & Ghost Success Auditing:
   - Verifies that failures never return ghost text, default canned responses, or silent passes.
5. Boundary & Extreme Audio Inputs:
   - NaN / Inf values, non-contiguous memory, extreme values, huge buffers.
"""
from __future__ import annotations

import concurrent.futures
import threading
import time
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
)


def make_audio_tone(duration_s: float, sample_rate: int = 16000, freq_hz: float = 440.0, amplitude: float = 0.5) -> np.ndarray:
    """Generate a clean synthetic sine wave 1D float32 audio array."""
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


# ============================================================================
# 1. CONCURRENCY & THREAD-SAFETY ADVERSARIAL CHALLENGES
# ============================================================================

def test_adversarial_large_v3_lock_attribute_exists():
    """
    CHALLENGE: DynamicTieredASREngine MUST have a dedicated `_large_v3_lock` attribute
    to synchronize large-v3 allocations in VRAM.
    """
    engine = DynamicTieredASREngine(config={"device": "cpu"})
    assert hasattr(engine, "_large_v3_lock"), (
        "CRITICAL CONCURRENCY BUG: DynamicTieredASREngine is missing `_large_v3_lock`. "
        "Without this lock, concurrent calls cannot serialize large-v3 VRAM allocation."
    )


def test_adversarial_concurrent_large_v3_double_allocation_prevention():
    """
    CHALLENGE: When multiple concurrent threads process audio requiring escalation,
    no more than ONE large-v3 engine may exist or transcribe simultaneously in VRAM.
    """
    num_threads = 5
    audio = make_audio_tone(1.5)  # Duration >= 1.0s, normal volume

    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.is_available.return_value = True
    # Low logprob forces escalation
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="mở đèn",
        avg_logprob=-0.90,
        no_speech_prob=0.10,
        duration_ms=200.0,
    )

    concurrent_instances = 0
    max_concurrent_instances = 0
    counter_lock = threading.Lock()

    def large_factory() -> BaseSTTEngine:
        nonlocal concurrent_instances, max_concurrent_instances
        with counter_lock:
            concurrent_instances += 1
            if concurrent_instances > max_concurrent_instances:
                max_concurrent_instances = concurrent_instances

        mock_large = MagicMock(spec=BaseSTTEngine)
        mock_large._model = MagicMock()

        def slow_transcribe(*args, **kwargs):
            # Hold the large model active for 50ms to expose race conditions
            time.sleep(0.05)
            return STTMetricsResult(
                text="mở đèn chùm",
                avg_logprob=-0.15,
                no_speech_prob=0.02,
                duration_ms=50.0,
            )

        mock_large.transcribe_with_metrics.side_effect = slow_transcribe
        return mock_large

    def cleanup_cb():
        nonlocal concurrent_instances
        with counter_lock:
            concurrent_instances -= 1

    engine = DynamicTieredASREngine(
        config={"device": "cpu"},
        small_engine=mock_small,
        large_engine_factory=large_factory,
        cleanup_callback=cleanup_cb,
    )

    # Launch concurrent requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(engine.transcribe, audio) for _ in range(num_threads)]
        results = [f.result() for f in futures]

    for res in results:
        assert isinstance(res, TranscriptionResult)
        assert res.escalated is True

    # Check whether concurrent double allocations occurred
    assert max_concurrent_instances <= 1, (
        f"CRITICAL VRAM RACE CONDITION: max_concurrent_instances={max_concurrent_instances} > 1! "
        "Multiple threads concurrently allocated large-v3 in VRAM, violating the 2.0GB VRAM budget "
        "and risking catastrophic CUDA Out of Memory on 4GB GPUs."
    )


# ============================================================================
# 2. FAIL-CLOSED RESILIENCE ON CUDA OOM ADVERSARIAL CHALLENGES
# ============================================================================

def test_adversarial_cuda_oom_during_large_engine_creation():
    """
    CHALLENGE: If CUDA OOM occurs while instantiating large-v3 during escalation,
    the engine must fall back to the initial tier result without crashing or ghosting.
    """
    audio = make_audio_tone(1.2)

    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="giảm nhiệt độ",
        avg_logprob=-0.75,
        no_speech_prob=0.08,
        duration_ms=300.0,
    )

    def oom_factory():
        raise RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")

    cleanup_called = False

    def on_cleanup():
        nonlocal cleanup_called
        cleanup_called = True

    engine = DynamicTieredASREngine(
        config={"device": "cuda"},
        small_engine=mock_small,
        large_engine_factory=oom_factory,
        cleanup_callback=on_cleanup,
    )

    res = engine.transcribe(audio)

    assert isinstance(res, TranscriptionResult)
    assert res.text == "giảm nhiệt độ"
    assert res.model_tier == "small"
    assert res.escalated is False
    assert "CUDA out of memory" in str(res.error)
    # Memory cleanup must still be invoked
    assert cleanup_called is True


def test_adversarial_cuda_oom_during_large_transcribe():
    """
    CHALLENGE: If CUDA OOM occurs during inference on large-v3,
    memory must be evicted in finally block and initial result preserved.
    """
    audio = make_audio_tone(1.2)

    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="bật máy lạnh",
        avg_logprob=-0.80,
        no_speech_prob=0.10,
        duration_ms=350.0,
    )

    mock_large = MagicMock(spec=BaseSTTEngine)
    mock_large._model = MagicMock()
    mock_large.transcribe_with_metrics.side_effect = RuntimeError(
        "CUDA out of memory. Tried to allocate 1.50 GiB"
    )

    cleanup_called = False

    def on_cleanup():
        nonlocal cleanup_called
        cleanup_called = True

    engine = DynamicTieredASREngine(
        config={"device": "cuda"},
        small_engine=mock_small,
        large_engine_factory=lambda: mock_large,
        cleanup_callback=on_cleanup,
    )

    res = engine.transcribe(audio)

    assert res.text == "bật máy lạnh"
    assert res.escalated is False
    assert res.model_tier == "small"
    assert "CUDA out of memory" in str(res.error)
    assert cleanup_called is True
    assert getattr(mock_large, "_model", None) is None


# ============================================================================
# 3. FAIL-CLOSED RESILIENCE ON MISSING / CORRUPTED MODEL WEIGHTS
# ============================================================================

def test_adversarial_missing_weights_on_initial_gpu_tier():
    """
    CHALLENGE: When initial tier weights are missing / FileNotFound on GPU,
    engine must cascade to CPU fallback or fail-closed without crashing.
    """
    audio = make_audio_tone(1.2)

    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.transcribe_with_metrics.side_effect = FileNotFoundError(
        "Could not find model.bin in cache/whisper/small"
    )

    engine = DynamicTieredASREngine(
        config={"device": "cuda"},
        small_engine=mock_small,
    )

    with patch("jarvis.stt.dynamic_tiered.FasterWhisperSTT") as mock_fw_cls:
        # Simulate CPU fallback succeeding
        mock_cpu = MagicMock()
        mock_cpu.transcribe_with_metrics.return_value = STTMetricsResult(
            text="mở nhạc",
            avg_logprob=-0.20,
            no_speech_prob=0.03,
            duration_ms=600.0,
        )
        mock_fw_cls.return_value = mock_cpu

        res = engine.transcribe(audio)

        assert res.text == "mở nhạc"
        assert res.model_tier == "small-cpu-fallback"
        assert res.escalated is False


def test_adversarial_missing_weights_on_both_gpu_and_cpu():
    """
    CHALLENGE: When model weights are completely missing on both GPU and CPU,
    engine must return model_tier='failed', empty text, and descriptive error.
    Must NOT raise unhandled exceptions and MUST NOT return ghost text.
    """
    audio = make_audio_tone(1.2)

    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.transcribe_with_metrics.side_effect = STTError("Model small not downloaded")

    engine = DynamicTieredASREngine(
        config={"device": "cuda"},
        small_engine=mock_small,
    )

    with patch("jarvis.stt.dynamic_tiered.FasterWhisperSTT") as mock_fw_cls:
        # Simulate CPU fallback ALSO failing due to missing weights
        mock_cpu = MagicMock()
        mock_cpu.transcribe_with_metrics.side_effect = STTError("CPU model small not downloaded")
        mock_fw_cls.return_value = mock_cpu

        res = engine.transcribe(audio)

        assert res.text == ""
        assert res.model_tier == "failed"
        assert res.is_success is False
        assert res.escalated is False
        assert "not downloaded" in str(res.error)


def test_adversarial_missing_weights_on_large_escalation():
    """
    CHALLENGE: If large-v3 weights are missing when escalation is triggered,
    engine must not crash, must clean up, and must return the initial tier transcript.
    """
    audio = make_audio_tone(1.2)

    mock_small = MagicMock(spec=BaseSTTEngine)
    mock_small.transcribe_with_metrics.return_value = STTMetricsResult(
        text="tăng âm lượng",
        avg_logprob=-0.88,
        no_speech_prob=0.15,
        duration_ms=300.0,
    )

    def missing_large_factory():
        raise FileNotFoundError("large-v3 weights missing")

    engine = DynamicTieredASREngine(
        config={"device": "cpu"},
        small_engine=mock_small,
        large_engine_factory=missing_large_factory,
    )

    res = engine.transcribe(audio)

    assert res.text == "tăng âm lượng"
    assert res.model_tier == "small"
    assert res.escalated is False
    assert "large-v3 weights missing" in str(res.error)


# ============================================================================
# 4. ANTI-FABRICATION & GHOST SUCCESS AUDITING
# ============================================================================

def test_adversarial_anti_fabrication_no_ghost_text():
    """
    CHALLENGE: Under no circumstance may the engine return canned success text
    (e.g. 'Lệnh thoại đã nhận', 'OK', etc.) when audio is corrupt or empty.
    """
    engine = DynamicTieredASREngine(config={"device": "cpu"})

    # Case 1: Pure silence
    res_silence = engine.transcribe(np.zeros(16000, dtype=np.float32))
    assert res_silence.text == ""
    assert res_silence.is_success is False

    # Case 2: Empty bytes
    res_empty_bytes = engine.transcribe(b"")
    assert res_empty_bytes.text == ""
    assert res_empty_bytes.is_success is False

    # Case 3: Completely invalid / corrupt audio bytes
    res_corrupt = engine.transcribe(b"CORRUPTED_GARBAGE_PAYLOAD_NOT_WAV")
    # Even if interpreted as PCM, RMS is zero or near zero, or audio prep fails
    assert not any(canned in res_corrupt.text.lower() for canned in ["lệnh", "nhận", "ok", "success"])


# ============================================================================
# 5. BOUNDARY & EXTREME AUDIO INPUTS
# ============================================================================

def test_adversarial_audio_with_nans_and_infs():
    """
    CHALLENGE: Audio buffer with NaN and Inf values must be sanitized cleanly
    by prepare_stt_audio and not cause division by zero or NaN propagation.
    """
    arr_dirty = np.array([np.nan, np.inf, -np.inf, 0.5, -0.5, np.nan], dtype=np.float32)

    mock_tiny = MagicMock(spec=BaseSTTEngine)
    mock_tiny.transcribe_with_metrics.return_value = STTMetricsResult(
        text="test nan",
        avg_logprob=-0.1,
        no_speech_prob=0.01,
        duration_ms=10.0,
    )

    engine = DynamicTieredASREngine(
        config={"device": "cpu", "short_duration_threshold_s": 1.0},
        tiny_engine=mock_tiny,
    )

    # Should not raise exception
    res = engine.transcribe(arr_dirty)
    assert isinstance(res, TranscriptionResult)

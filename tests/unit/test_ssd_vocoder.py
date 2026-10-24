"""
tests/unit/test_ssd_vocoder.py
==============================
Unit tests for Frontier 16.0 State-Space Streaming Neural Vocoder.
Sprint 26 / Milestone v6.4.0.
"""
from __future__ import annotations

import numpy as np
import pytest

from jarvis.audio.ssd_vocoder import (
    DEFAULT_HIDDEN_DIM,
    FRAME_DURATION_SEC,
    STATE_DIM,
    SSDVocoderFrame,
    SSDVocoderSampleRate,
    StateSpaceStreamingVocoder,
)


def test_ssd_vocoder_frame_synthesis() -> None:
    """Tests 10ms audio frame synthesis from Mamba-2 hidden states."""
    vocoder = StateSpaceStreamingVocoder(
        hidden_dim=DEFAULT_HIDDEN_DIM,
        state_dim=STATE_DIM,
        sample_rate=SSDVocoderSampleRate.SR_16KHZ,
    )
    assert vocoder.frame_samples == 160  # 16000 * 0.010 = 160 samples

    h_t = np.random.randn(DEFAULT_HIDDEN_DIM).astype(np.float32) * 0.5
    frame = vocoder.synthesize_frame(h_t)

    assert isinstance(frame, SSDVocoderFrame)
    assert len(frame.samples_pcm16) == 160
    assert len(frame.samples_float32) == 160
    assert frame.sample_rate == 16000
    assert frame.duration_ms == 10.0
    assert len(frame.raw_bytes) == 320  # 160 * 2 bytes for int16
    assert frame.synthesis_latency_ms < 10.0  # Faster than real-time


def test_ssd_vocoder_realtime_factor() -> None:
    """Verifies that synthesis executes faster than real-time (RTF < 1.0)."""
    vocoder = StateSpaceStreamingVocoder(
        sample_rate=SSDVocoderSampleRate.SR_24KHZ,
    )
    assert vocoder.frame_samples == 240  # 24000 * 0.010 = 240 samples

    h_t = np.random.randn(DEFAULT_HIDDEN_DIM).astype(np.float32)
    for _ in range(5):
        vocoder.synthesize_frame(h_t)

    snapshot = vocoder.get_metrics_snapshot()
    assert snapshot["total_frames_synthesized"] == 5
    assert snapshot["faster_than_realtime"] is True
    assert snapshot["vram_delta_mib"] == 0.00


def test_ssd_vocoder_barge_in_interruption() -> None:
    """Verifies conversational barge-in interruption latency (< 45ms SLA)."""
    vocoder = StateSpaceStreamingVocoder()
    h_t = np.random.randn(DEFAULT_HIDDEN_DIM).astype(np.float32)

    # Synthesize two frames
    vocoder.synthesize_frame(h_t)
    vocoder.synthesize_frame(h_t)

    # User starts speaking -> trigger barge-in
    barge_in_latency_ms = vocoder.trigger_barge_in_interrupt()
    assert barge_in_latency_ms < 45.0  # Sub-45ms SLA (typically < 1ms)

    # Next frame should be muted silence
    silent_frame = vocoder.synthesize_frame(h_t)
    assert silent_frame.is_interrupted is True
    assert np.all(silent_frame.samples_pcm16 == 0)

    # Resume synthesis
    vocoder.resume_synthesis()
    resumed_frame = vocoder.synthesize_frame(h_t)
    assert resumed_frame.is_interrupted is False


def test_ssd_vocoder_invalid_hidden_dim_fail_closed() -> None:
    """Guards against dimension mismatch with descriptive exception."""
    vocoder = StateSpaceStreamingVocoder()
    invalid_h = np.zeros(128, dtype=np.float32)
    with pytest.raises(ValueError, match="Expected hidden_state dimension 512"):
        vocoder.synthesize_frame(invalid_h)


def test_ssd_vocoder_phase_continuity() -> None:
    """Verifies that synthesis maintains continuous carrier phase across 10ms frame chunks."""
    vocoder = StateSpaceStreamingVocoder()
    h = np.random.randn(DEFAULT_HIDDEN_DIM).astype(np.float32) * 0.1

    assert vocoder._phase == 0.0
    f1 = vocoder.synthesize_frame(h)
    phase_after_f1 = vocoder._phase
    assert phase_after_f1 > 0.0

    f2 = vocoder.synthesize_frame(h)
    phase_after_f2 = vocoder._phase
    assert phase_after_f2 != phase_after_f1

    # Resetting state resets phase
    vocoder.reset_state()
    assert vocoder._phase == 0.0


def test_ssd_vocoder_nan_inf_fail_closed() -> None:
    """Ensures fail-closed exception when NaN or Inf hidden states are provided."""
    vocoder = StateSpaceStreamingVocoder()
    h_nan = np.zeros(DEFAULT_HIDDEN_DIM, dtype=np.float32)
    h_nan[0] = np.nan

    with pytest.raises(ValueError, match="contains NaN or Inf"):
        vocoder.synthesize_frame(h_nan)

    h_inf = np.zeros(DEFAULT_HIDDEN_DIM, dtype=np.float32)
    h_inf[0] = np.inf

    with pytest.raises(ValueError, match="contains NaN or Inf"):
        vocoder.synthesize_frame(h_inf)


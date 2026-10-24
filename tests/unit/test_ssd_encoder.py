"""
tests/unit/test_ssd_encoder.py
==============================
Unit tests for Mamba-2 Structured State Space Duality (SSD) streaming speech encoder.
"""
from __future__ import annotations

import numpy as np
import pytest

from jarvis.stt.ssd_encoder import Mamba2SSDBlock, SSDConfig, StreamingSpeechSSDEncoder


def test_mamba2_ssd_block_initialization_and_memory():
    """Verifies that Mamba-2 SSD block initializes with strictly constant O(1) memory."""
    config = SSDConfig(d_model=64, d_state=16, d_inner=128, d_conv=4)
    block = Mamba2SSDBlock(config=config)

    assert block.conv_buffer.shape == (128, 4)
    assert block.ssm_state.shape == (128, 16)

    # Constant memory footprint check
    mem_bytes = block.persistent_state_memory_bytes
    expected_bytes = (128 * 4 * 4) + (128 * 16 * 4)  # float32 = 4 bytes
    assert mem_bytes == expected_bytes
    assert mem_bytes < 50 * 1024  # Less than 50 KB


def test_mamba2_ssd_block_streaming_step():
    """Verifies single-step streaming forward pass and latency."""
    config = SSDConfig(d_model=64, d_state=16, d_inner=128, d_conv=4)
    block = Mamba2SSDBlock(config=config)

    x_t = np.ones(64, dtype=np.float32) * 0.5
    step_out = block.step(x_t, is_glottal_stop=False)

    assert step_out.output.shape == (64,)
    assert step_out.output.dtype == np.float32
    assert step_out.step_latency_ms > 0.0
    assert step_out.step_latency_ms < 50.0  # Ultra-fast sub-50ms CPU execution
    assert step_out.total_frames_processed == 1
    assert not step_out.is_glottal_reset


def test_mamba2_ssd_glottal_triggered_reset():
    """Verifies that glottal stop flag triggers GTSR state decay."""
    config = SSDConfig(d_model=64, d_state=16, d_inner=128, d_conv=4, gtsr_decay=0.1)
    block = Mamba2SSDBlock(config=config)

    # Accumulate state over 10 steps
    for _ in range(10):
        _ = block.step(np.ones(64, dtype=np.float32))

    norm_before = float(np.linalg.norm(block.ssm_state))
    assert norm_before > 0.0

    # Step with glottal stop
    step_out = block.step(np.zeros(64, dtype=np.float32), is_glottal_stop=True)
    assert step_out.is_glottal_reset

    # State should be significantly decayed
    norm_after = float(np.linalg.norm(block.ssm_state))
    assert norm_after < norm_before


def test_streaming_speech_ssd_encoder_multi_layer():
    """Verifies multi-layer stacked SSD encoder with residual connections."""
    config = SSDConfig(d_model=64, d_state=16, d_inner=128, d_conv=4)
    encoder = StreamingSpeechSSDEncoder(num_layers=3, config=config)

    assert len(encoder.layers) == 3
    total_mem = encoder.total_state_memory_bytes
    assert total_mem > 0
    assert total_mem < 200 * 1024  # Under 200 KB

    x_frame = np.random.default_rng(123).normal(0.0, 1.0, 64).astype(np.float32)
    out_vector, telemetry = encoder.process_frame(x_frame, is_glottal_stop=False)

    assert out_vector.shape == (64,)
    assert "total_latency_ms" in telemetry
    assert "memory_kb" in telemetry
    assert telemetry["total_latency_ms"] < 25.0


def test_ssd_encoder_memory_invariance_over_time():
    """Critical verification: asserts state memory buffer does not grow over 100 consecutive steps."""
    config = SSDConfig(d_model=64, d_state=16, d_inner=128, d_conv=4)
    encoder = StreamingSpeechSSDEncoder(num_layers=2, config=config)

    initial_mem = encoder.total_state_memory_bytes

    rng = np.random.default_rng(42)
    for _ in range(100):
        frame = rng.normal(0.0, 1.0, 64).astype(np.float32)
        _ = encoder.process_frame(frame)

    final_mem = encoder.total_state_memory_bytes
    # Memory must be strictly constant O(1)
    assert final_mem == initial_mem

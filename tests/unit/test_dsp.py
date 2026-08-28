"""
tests/unit/test_dsp.py
======================
Unit tests for Acoustic DSP Module (jarvis.audio.dsp).
"""
import math

import numpy as np
import pytest

from jarvis.audio.dsp import (
    AudioDSPProcessor,
    DSPBlockResult,
    NoiseFloorTracker,
    SchmittTrigger,
    calculate_rms,
    rms_mono,
)


def test_calculate_rms_silence():
    """Verify zero RMS for digital silence and empty buffers."""
    silence = np.zeros(1764, dtype=np.float32)
    assert calculate_rms(silence) == 0.0
    assert calculate_rms(np.array([], dtype=np.float32)) == 0.0
    assert calculate_rms(None) == 0.0
    assert rms_mono(silence) == 0.0


def test_calculate_rms_dc_and_sine():
    """Verify exact RMS calculation for DC offset and sinusoidal waveform."""
    dc = np.full(1764, 0.5, dtype=np.float32)
    assert math.isclose(calculate_rms(dc), 0.5, abs_tol=1e-5)

    t = np.linspace(0, 0.04, 1764, endpoint=False)
    sine = np.sin(2 * np.pi * 1000 * t).astype(np.float32)
    assert math.isclose(calculate_rms(sine), 1.0 / math.sqrt(2), rel_tol=1e-2)


def test_calculate_rms_multichannel_downmixing():
    """Verify 2D stereo array downmixing computes identical RMS."""
    t = np.linspace(0, 0.04, 1764, endpoint=False)
    sine = np.sin(2 * np.pi * 1000 * t).astype(np.float32)
    stereo = np.column_stack([sine, sine])
    assert math.isclose(calculate_rms(stereo), 1.0 / math.sqrt(2), rel_tol=1e-2)


def test_calculate_rms_int16_normalization():
    """Verify int16 buffers are normalized by 32768.0."""
    int16_buf = np.full(1000, 16384, dtype=np.int16)
    rms = calculate_rms(int16_buf)
    assert math.isclose(rms, 0.5, abs_tol=1e-4)


def test_calculate_rms_nan_inf_sanitization():
    """Verify corrupt buffers with NaN and +/-Inf are sanitized."""
    corrupt = np.array([np.nan, 0.5, np.inf, -np.inf, 0.5], dtype=np.float32)
    rms = calculate_rms(corrupt)
    assert not math.isnan(rms)
    assert not math.isinf(rms)
    assert rms >= 0.0


def test_noise_floor_tracker_adaptation():
    """Verify EMA noise floor adapts downwards during quiet periods."""
    tracker = NoiseFloorTracker(alpha=0.992, initial_floor=0.010)
    for _ in range(400):
        tracker.update(0.002)
    assert tracker.noise_floor < 0.010
    assert math.isclose(tracker.noise_floor, 0.002, abs_tol=1e-3)


def test_noise_floor_tracker_quiet_gate_freeze():
    """Verify noise floor adaptation freezes when RMS exceeds quiet gate multiplier."""
    tracker = NoiseFloorTracker(alpha=0.992, quiet_gate_mult=2.2, initial_floor=0.005)
    for _ in range(100):
        floor, is_gated = tracker.update(0.030)
        assert is_gated is True
    assert tracker.noise_floor == 0.005


def test_schmitt_trigger_hysteresis():
    """Verify Schmitt trigger re-arms only after dropping below retrigger level."""
    trigger = SchmittTrigger(spike_ratio=7.0, retrigger_ratio=0.55, min_rms=0.012)
    noise_floor = 0.005
    threshold = 0.035  # max(0.005 * 7.0, 0.012) = 0.035
    retrigger = 0.035 * 0.55  # 0.01925

    # 1. Trigger clap
    is_transient, is_armed, th, retrig = trigger.evaluate(0.050, noise_floor)
    assert is_transient is True
    assert is_armed is False

    # 2. Mid-level decay above retrigger level -> remains disarmed
    is_transient, is_armed, _, _ = trigger.evaluate(0.025, noise_floor)
    assert is_transient is False
    assert is_armed is False

    # 3. Quiet block below retrigger level -> re-arms
    is_transient, is_armed, _, _ = trigger.evaluate(0.010, noise_floor)
    assert is_transient is False
    assert is_armed is True


def test_audio_dsp_processor_full_pipeline():
    """Verify AudioDSPProcessor returns structured dict and DSPBlockResult."""
    dsp = AudioDSPProcessor(spike_ratio=7.0, min_rms=0.012)

    # Process baseline
    for _ in range(20):
        dsp.process_block(np.full(1764, 0.002, dtype=np.float32))

    # Process loud transient
    res_dict = dsp.process_block(np.full(1764, 0.5, dtype=np.float32))
    assert res_dict["is_transient"] is True
    assert res_dict["is_armed"] is False
    assert res_dict["rms"] == 0.5

    # Process detailed
    res_detailed = dsp.process_block_detailed(np.full(1764, 0.001, dtype=np.float32))
    assert isinstance(res_detailed, DSPBlockResult)
    assert res_detailed.is_armed is True

    # Reset
    dsp.reset()
    assert dsp.spike_armed is True

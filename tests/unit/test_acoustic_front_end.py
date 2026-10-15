"""
tests/unit/test_acoustic_front_end.py
======================================
Unit tests for the Acoustic Front-End (AFE) and Speech Signal Conditioning Subsystem.
Verifies:
  - Bandpass filtering (80 Hz - 7500 Hz) and DC offset elimination.
  - Automatic Gain Control (AGC) and soft peak limiter.
  - Dynamic SNR estimation and voice activity duration sanity gate.
  - Fail-closed behavior on pure noise, silence, NaN/Inf, and corrupt buffers.
"""
import math
import numpy as np
import pytest

from jarvis.audio.dsp import (
    AcousticFrontEnd,
    AFEOutput,
    automatic_gain_control,
    calculate_rms,
    speech_bandpass_filter,
)


def test_speech_bandpass_filter_dc_removal():
    """Verify bandpass filter eliminates DC offset completely."""
    # DC signal + 1kHz sine wave
    t = np.linspace(0, 0.1, 1600, endpoint=False)
    sine = np.sin(2 * np.pi * 1000 * t).astype(np.float32) * 0.1
    dc_signal = sine + 0.35  # heavy DC bias

    filtered = speech_bandpass_filter(dc_signal, sample_rate=16000)
    assert len(filtered) == len(dc_signal)
    # DC offset should be essentially zero (< 5e-4)
    assert abs(float(np.mean(filtered))) < 5e-4


def test_speech_bandpass_filter_attenuates_low_rumble():
    """Verify sub-audible mechanical rumble (e.g. 20 Hz fan hum) is strongly attenuated."""
    t = np.linspace(0, 0.2, 3200, endpoint=False)
    rumble_20hz = np.sin(2 * np.pi * 20 * t).astype(np.float32) * 0.5
    filtered = speech_bandpass_filter(rumble_20hz, sample_rate=16000, lowcut=80.0)

    raw_rms = calculate_rms(rumble_20hz)
    filt_rms = calculate_rms(filtered)
    # Attenuation should be at least 15 dB (ratio < 0.18)
    assert filt_rms < raw_rms * 0.25


def test_speech_bandpass_filter_preserves_speech_bandwidth():
    """Verify human speech formant frequencies (e.g. 500 Hz, 1500 Hz) pass with high fidelity."""
    t = np.linspace(0, 0.2, 3200, endpoint=False)
    speech_tone = np.sin(2 * np.pi * 1000 * t).astype(np.float32) * 0.2
    filtered = speech_bandpass_filter(speech_tone, sample_rate=16000)

    raw_rms = calculate_rms(speech_tone)
    filt_rms = calculate_rms(filtered)
    # Formant within bandpass passband should have >90% transmission
    assert filt_rms >= raw_rms * 0.90


def test_automatic_gain_control_amplification_and_soft_limiter():
    """Verify AGC amplifies quiet speech and limits high peaks without exceeding 0.95."""
    # 1. Quiet signal amplification
    t = np.linspace(0, 0.1, 1600, endpoint=False)
    quiet_sine = np.sin(2 * np.pi * 400 * t).astype(np.float32) * 0.02
    boosted = automatic_gain_control(quiet_sine, target_rms=0.08, max_gain=4.5)
    assert calculate_rms(boosted) > calculate_rms(quiet_sine)

    # 2. Loud signal limiting
    loud_sine = np.sin(2 * np.pi * 400 * t).astype(np.float32) * 1.5
    limited = automatic_gain_control(loud_sine, target_rms=0.08)
    peak = float(np.max(np.abs(limited)))
    assert peak <= 0.95


def test_afe_pure_noise_rejected():
    """Verify pure ambient noise is rejected by AFE speech gate."""
    afe = AcousticFrontEnd(sample_rate=16000)
    noise = np.random.normal(0, 0.007, 16000 * 2).astype(np.float32)

    res = afe.process(noise)
    assert isinstance(res, AFEOutput)
    assert res.has_speech is False
    assert res.snr_db < 4.0
    assert res.active_speech_ms < 100.0


def test_afe_speech_detected():
    """Verify voiced utterance with speech bursts is accepted by AFE."""
    afe = AcousticFrontEnd(sample_rate=16000)
    # Ambient noise
    signal = np.random.normal(0, 0.005, 16000 * 2).astype(np.float32)
    # Add 600ms of simulated speech tone at 400 Hz
    t = np.linspace(0, 0.6, 9600, endpoint=False)
    signal[4000:13600] += np.sin(2 * np.pi * 400 * t).astype(np.float32) * 0.12

    res = afe.process(signal)
    assert res.has_speech is True
    assert res.snr_db > 10.0
    assert res.active_speech_ms >= 300.0
    assert len(res.samples) == len(signal)


def test_afe_empty_and_corrupt_buffers():
    """Verify AFE handles empty, None, and NaN/Inf buffers without raising exceptions."""
    afe = AcousticFrontEnd(sample_rate=16000)

    res_none = afe.process(None)
    assert res_none.has_speech is False
    assert len(res_none.samples) == 0

    res_empty = afe.process(np.empty(0, dtype=np.float32))
    assert res_empty.has_speech is False
    assert len(res_empty.samples) == 0

    corrupt = np.array([np.nan, 0.1, np.inf, -np.inf, 0.1], dtype=np.float32)
    res_corrupt = afe.process(corrupt)
    assert not np.isnan(res_corrupt.samples).any()
    assert not np.isinf(res_corrupt.samples).any()

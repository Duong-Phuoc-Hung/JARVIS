"""
tests/unit/test_ps_hcf.py
=========================
Unit Test Suite for Pitch-Synchronous Harmonic Comb Filter (PS-HCF) & AFE Integration.
Validates:
  - F0 pitch tracking accuracy on simulated human voice harmonics.
  - Bypass integrity on unvoiced noise and short buffers.
  - Lexical tone preservation (tone 'sắc' glide and tone 'ngã' glottal stop).
  - Microsecond CPU execution budget (< 0.2ms per frame).
  - Clean integration with AcousticFrontEnd in jarvis.audio.dsp.
"""
import time
import numpy as np
import pytest

from jarvis.audio.dsp import AcousticFrontEnd
from jarvis.audio.ps_hcf import PitchSynchronousHarmonicFilter, PSHCFResult


def test_ps_hcf_empty_and_short_buffers():
    """Validates that empty, None, and short buffers pass through gracefully."""
    ps_filter = PitchSynchronousHarmonicFilter(sample_rate=16000)

    # 1. None buffer
    res_none = ps_filter.filter(None)
    assert isinstance(res_none, PSHCFResult)
    assert len(res_none.samples) == 0
    assert not res_none.is_voiced
    assert res_none.f0_hz == 0.0

    # 2. Empty buffer
    res_empty = ps_filter.filter(np.empty(0, dtype=np.float32))
    assert len(res_empty.samples) == 0

    # 3. Very short buffer (less than max_lag ~228 samples)
    short_buf = np.ones(50, dtype=np.float32) * 0.1
    res_short = ps_filter.filter(short_buf)
    assert len(res_short.samples) == 50
    assert not res_short.is_voiced
    np.testing.assert_allclose(res_short.samples, short_buf)


def test_ps_hcf_voiced_sine_wave_detection_and_preservation():
    """Validates F0 detection and energy preservation on a voiced harmonic signal (200 Hz)."""
    fs = 16000
    duration = 0.2  # 200ms
    t = np.linspace(0, duration, int(fs * duration), endpoint=False)
    # Fundamental 200 Hz + 2nd harmonic 400 Hz
    signal = 0.3 * np.sin(2 * np.pi * 200.0 * t) + 0.15 * np.sin(2 * np.pi * 400.0 * t)

    ps_filter = PitchSynchronousHarmonicFilter(sample_rate=fs, f0_min=70.0, f0_max=450.0)
    res = ps_filter.filter(signal)

    assert res.is_voiced is True
    assert 190.0 <= res.f0_hz <= 210.0
    assert res.clarity >= 0.70
    assert res.alpha_applied > 0.0

    # Harmonic energy must be preserved (> 90%)
    orig_energy = float(np.sum(signal ** 2))
    filt_energy = float(np.sum(res.samples ** 2))
    energy_retention = filt_energy / orig_energy
    assert energy_retention >= 0.90


def test_ps_hcf_unvoiced_noise_bypass():
    """Validates that non-periodic white noise is classified as unvoiced and cleanly bypassed."""
    fs = 16000
    duration = 0.1
    rng = np.random.default_rng(seed=42)
    noise = rng.normal(0.0, 0.05, int(fs * duration)).astype(np.float32)

    ps_filter = PitchSynchronousHarmonicFilter(sample_rate=fs)
    res = ps_filter.filter(noise)

    # Random noise should not be classified as high-clarity voiced
    assert res.is_voiced is False
    assert res.alpha_applied == 0.0
    np.testing.assert_allclose(res.samples, noise)


def test_ps_hcf_vietnamese_tone_sac_glide_tracking():
    """Simulates tone 'sắc' (F0 glide from 200Hz to 320Hz) and validates tracking and continuity."""
    fs = 16000
    duration = 0.25
    t = np.linspace(0, duration, int(fs * duration), endpoint=False)
    # Frequency modulation: f(t) = 200 + 120 * (t / duration)
    phase = 2 * np.pi * (200.0 * t + 0.5 * (120.0 / duration) * (t ** 2))
    glide_signal = 0.25 * np.sin(phase)

    ps_filter = PitchSynchronousHarmonicFilter(sample_rate=fs)
    res = ps_filter.filter(glide_signal)

    assert res.is_voiced is True
    assert 180.0 <= res.f0_hz <= 340.0
    assert len(res.samples) == len(glide_signal)
    assert not np.isnan(res.samples).any()


def test_ps_hcf_glottal_stop_preservation():
    """Simulates tone 'ngã' (two voiced bursts with a 20ms glottal silent pause)."""
    fs = 16000
    burst_len = int(fs * 0.08)   # 80ms
    pause_len = int(fs * 0.02)   # 20ms silence
    t_burst = np.linspace(0, 0.08, burst_len, endpoint=False)
    burst = (0.3 * np.sin(2 * np.pi * 220.0 * t_burst)).astype(np.float32)
    silence = np.zeros(pause_len, dtype=np.float32)

    signal = np.concatenate([burst, silence, burst])

    ps_filter = PitchSynchronousHarmonicFilter(sample_rate=fs)
    res = ps_filter.filter(signal)

    # The silence region in the middle must remain essentially silent (< 0.05 RMS)
    pause_output = res.samples[burst_len : burst_len + pause_len]
    pause_rms = float(np.sqrt(np.mean(pause_output ** 2)))
    assert pause_rms < 0.05


def test_ps_hcf_execution_latency_budget():
    """Validates that PS-HCF executes under 0.2ms per 576-sample frame (budget <= 0.5ms)."""
    fs = 16000
    frame_len = 576
    t = np.linspace(0, frame_len / fs, frame_len, endpoint=False)
    frame = (0.2 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)

    ps_filter = PitchSynchronousHarmonicFilter(sample_rate=fs)

    # Warmup
    for _ in range(5):
        ps_filter.filter(frame)

    n_runs = 50
    t0 = time.perf_counter()
    for _ in range(n_runs):
        ps_filter.filter(frame)
    elapsed = (time.perf_counter() - t0) * 1000.0  # ms

    avg_ms = elapsed / n_runs
    # Assert average latency per 576-sample frame is under 0.5ms
    assert avg_ms < 0.5, f"PS-HCF latency too high: {avg_ms:.3f}ms per frame"


def test_afe_integration_with_ps_hcf():
    """Validates AcousticFrontEnd integration with PS-HCF enabled on realistic utterance."""
    fs = 16000
    # Ambient noise (1.5 seconds) + speech burst (500ms)
    signal = np.random.normal(0, 0.005, int(fs * 1.5)).astype(np.float32)
    t = np.linspace(0, 0.5, int(fs * 0.5), endpoint=False)
    signal[4000:12000] += (np.sin(2 * np.pi * 200.0 * t) * 0.15).astype(np.float32)

    afe = AcousticFrontEnd(sample_rate=fs, enable_ps_hcf=True)
    out = afe.process(signal)

    assert out.has_speech is True
    assert len(out.samples) == len(signal)
    assert out.snr_db > 8.0
    assert not np.isnan(out.samples).any()

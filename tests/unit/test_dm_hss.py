"""
tests/unit/test_dm_hss.py
=========================
Unit Test Suite for Dual-Mode Harmonic-Spectral Subtraction (DM-HSS).
Validates:
  1. Low-frequency pitch tracking down to 40 Hz (vocal fry in Vietnamese tones 'ngã'/'nặng').
  2. 50Hz and 100Hz notch filtering eliminating electrical power line hum.
  3. Spectral Floor Subtraction on unvoiced whispered speech frames.
  4. Proper telemetry classification of filter modes ('comb', 'spectral_subtraction', 'bypass').
"""
import numpy as np
import pytest

from jarvis.audio.ps_hcf import (
    PitchSynchronousHarmonicFilter,
    PSHCFResult,
    _apply_hum_notch_filters,
    _spectral_floor_subtraction,
)


def test_dm_hss_40hz_vocal_fry_detection():
    """Validates F0 tracking down to 40 Hz in DM-HSS mode."""
    fs = 16000
    duration = 0.3
    t = np.linspace(0, duration, int(fs * duration), endpoint=False)
    # 45 Hz low-pitched vocal fry + 90 Hz 2nd harmonic
    signal = 0.3 * np.sin(2 * np.pi * 45.0 * t) + 0.15 * np.sin(2 * np.pi * 90.0 * t)

    dm_filter = PitchSynchronousHarmonicFilter(
        sample_rate=fs,
        f0_min=40.0,
        f0_max=450.0,
        enable_dm_hss=True,
    )
    res = dm_filter.filter(signal)

    assert res.is_voiced is True
    assert 40.0 <= res.f0_hz <= 52.0
    assert res.filter_mode == "comb"
    assert res.alpha_applied > 0.0


def test_hum_notch_filtering_attenuates_50hz():
    """Validates that _apply_hum_notch_filters attenuates 50Hz power hum."""
    fs = 16000
    duration = 0.5
    t = np.linspace(0, duration, int(fs * duration), endpoint=False)
    hum_50hz = 0.5 * np.sin(2 * np.pi * 50.0 * t).astype(np.float32)

    filtered = _apply_hum_notch_filters(hum_50hz, fs)

    # Measure steady-state attenuation (discarding initial filter transient)
    orig_energy = float(np.sum(hum_50hz[1000:]**2))
    filt_energy = float(np.sum(filtered[1000:]**2))

    # 50 Hz power hum should be attenuated by > 80% (ratio < 0.20)
    attenuation_ratio = filt_energy / orig_energy
    assert attenuation_ratio < 0.20


def test_spectral_floor_subtraction_whisper_mode():
    """Validates that unvoiced whispered speech undergoes spectral floor subtraction."""
    fs = 16000
    duration = 0.15
    rng = np.random.default_rng(seed=123)
    # Simulated whispered aperiodic fricative with speech energy (RMS ~0.02)
    whisper_frame = rng.normal(0.0, 0.02, int(fs * duration)).astype(np.float32)

    dm_filter = PitchSynchronousHarmonicFilter(
        sample_rate=fs,
        enable_dm_hss=True,
    )
    res = dm_filter.filter(whisper_frame)

    assert res.is_voiced is False
    assert res.filter_mode == "spectral_subtraction"
    assert len(res.samples) == len(whisper_frame)
    assert not np.isnan(res.samples).any()


def test_dm_hss_silence_bypass():
    """Validates that near-silent frames bypass spectral subtraction."""
    fs = 16000
    duration = 0.1
    silent_frame = np.zeros(int(fs * duration), dtype=np.float32)

    dm_filter = PitchSynchronousHarmonicFilter(
        sample_rate=fs,
        enable_dm_hss=True,
    )
    res = dm_filter.filter(silent_frame)

    assert res.is_voiced is False
    assert res.filter_mode == "bypass"

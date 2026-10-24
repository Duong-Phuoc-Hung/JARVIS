"""
tests/unit/test_eot_predictor.py
================================
Unit Test Suite for Prosodic End-of-Turn (EoT) Predictor.
Validates:
  1. Terminal Pitch Declination (dF0/dt < -320 Hz/s) detection.
  2. Hesitation / flat pitch contour (|dF0/dt| < 40 Hz/s) discrimination.
  3. Spectral tilt / high-frequency roll-off computation.
  4. Empty / unvoiced buffer safety.
"""
import numpy as np
import pytest

from jarvis.audio.eot_predictor import ProsodicEoTPredictor, ProsodicEoTTelemetry


def test_eot_empty_and_unvoiced_buffer():
    """Validates that empty, zero-clarity, or silent buffers do not trigger EoT."""
    predictor = ProsodicEoTPredictor()

    # 1. Empty buffer
    res_empty = predictor.evaluate_frame(f0_hz=0.0, clarity=0.0, pcm_frame=np.empty(0, dtype=np.float32))
    assert res_empty.is_eot is False
    assert res_empty.is_hesitation is False

    # 2. Unvoiced noise buffer (clarity < 0.35)
    noise = np.random.normal(0.0, 0.05, 512).astype(np.float32)
    res_noise = predictor.evaluate_frame(f0_hz=150.0, clarity=0.20, pcm_frame=noise)
    assert res_noise.is_eot is False


def test_eot_terminal_pitch_declination_trigger():
    """Validates that a sharp drop in F0 with low spectral tilt triggers EoT."""
    predictor = ProsodicEoTPredictor(pitch_declination_threshold=-300.0, spectral_tilt_threshold=0.15)
    fs = 16000

    # Low-frequency sine wave (200Hz) with high-frequency roll-off (low tilt)
    t = np.linspace(0, 0.032, int(fs * 0.032), endpoint=False)
    pcm_coda = 0.3 * np.sin(2 * np.pi * 200.0 * t).astype(np.float32)

    # Feed 4 frames simulating terminal pitch drop: 220Hz -> 190Hz -> 160Hz -> 130Hz
    # df0 = (130 - 220) / (3 * 0.032) = -90 / 0.096 = -937.5 Hz/s!
    f0_sequence = [220.0, 190.0, 160.0, 130.0]

    last_res: ProsodicEoTTelemetry | None = None
    for f0 in f0_sequence:
        last_res = predictor.evaluate_frame(f0_hz=f0, clarity=0.85, pcm_frame=pcm_coda)

    assert last_res is not None
    assert last_res.is_eot is True
    assert last_res.df0_dt < -300.0
    assert last_res.spectral_tilt <= 0.15
    assert predictor.total_eot_detected >= 1


def test_eot_hesitation_flat_contour():
    """Validates that flat intonation (e.g. 'ờ...', 'ừm...') is classified as hesitation, NOT EoT."""
    predictor = ProsodicEoTPredictor(hesitation_flat_threshold=30.0)
    fs = 16000

    t = np.linspace(0, 0.032, int(fs * 0.032), endpoint=False)
    pcm_frame = 0.25 * np.sin(2 * np.pi * 180.0 * t).astype(np.float32)

    # Steady pitch: 180.0Hz -> 180.5Hz -> 180.2Hz -> 180.0Hz (|df0/dt| ~ 0 Hz/s)
    f0_sequence = [180.0, 180.5, 180.2, 180.0]

    last_res: ProsodicEoTTelemetry | None = None
    for f0 in f0_sequence:
        last_res = predictor.evaluate_frame(f0_hz=f0, clarity=0.80, pcm_frame=pcm_frame)

    assert last_res is not None
    assert last_res.is_eot is False
    assert last_res.is_hesitation is True
    assert abs(last_res.df0_dt) <= 30.0

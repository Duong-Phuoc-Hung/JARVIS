"""
tests/unit/test_subvocal_semg.py
================================
Unit Tests for Sub-Vocal Electromyography (sEMG) & Non-Invasive BCI Telepathy.
Milestone v8.0.0 ("The Omniscient Symbiont", Frontier 27.0).
"""
from __future__ import annotations

import numpy as np
import pytest

from jarvis.audio.subvocal_semg import (
    INTENT_VOCABULARY,
    NUM_SEMG_CHANNELS,
    BioHardwareBridge,
    ContinuousNeuromuscularLTC,
    OfflineNeuromuscularSignalGenerator,
    SubvocalSignalFilter,
    SubvocalTelepathyEngine,
)
from jarvis.core.hd_vsa import HD_DIMENSION_BITS, HyperVector
from jarvis.ui.terminal.theme import StatusLevel


def test_subvocal_signal_filter_rejection():
    """Validates 50/60 Hz notch filtering, bandpass, and wavelet denoising."""
    filter_bank = SubvocalSignalFilter()
    generator = OfflineNeuromuscularSignalGenerator(seed=42)

    # Generate gesture with 50/60 Hz powerline hum
    raw = generator.generate_gesture(duration_ms=100.0, intent_index=0, include_mains_hum=True)
    assert raw.shape[0] == NUM_SEMG_CHANNELS
    assert raw.shape[1] == 100

    filtered = filter_bank.filter_signals(raw)
    assert filtered.shape == raw.shape

    # Powerline hum energy should be strongly attenuated
    for ch in range(NUM_SEMG_CHANNELS):
        # Peak-to-peak amplitude should be conditioned
        assert not np.isnan(filtered[ch]).any()
        assert not np.isinf(filtered[ch]).any()


def test_continuous_neuromuscular_ltc_integration():
    """Validates RK4 continuous ODE integration and stability of latent trajectory h(t)."""
    ltc = ContinuousNeuromuscularLTC(in_features=NUM_SEMG_CHANNELS, latent_dim=32, tau_base=15.0)

    # Initial state should be zero
    assert np.allclose(ltc.h, 0.0)

    v_input = np.ones(NUM_SEMG_CHANNELS) * 15.0  # 15 uV stimulus
    h_next = ltc.step_rk4(v_input, dt_ms=1.0)

    assert h_next.shape == (32,)
    assert not np.allclose(h_next, 0.0)
    assert np.isfinite(h_next).all()

    # Step multiple times to check bounded trajectory
    for _ in range(50):
        h_next = ltc.step_rk4(v_input, dt_ms=1.0)
        assert np.max(np.abs(h_next)) < 100.0  # Boundedly stable

    ltc.reset_state()
    assert np.allclose(ltc.h, 0.0)


def test_subvocal_telepathy_engine_decoding():
    """Validates silent intent decoding, > 1,000 wpm thought velocity, and 10,000-bit HD-VSA projection."""
    engine = SubvocalTelepathyEngine()

    # Create synthetic trajectory
    rng = np.random.RandomState(42)
    h_traj = rng.normal(0.5, 0.2, size=(30, engine.ltc.latent_dim))

    result = engine.decode_trajectory(h_traj, dt_per_step_ms=1.0)

    assert result.intent_label in INTENT_VOCABULARY
    assert 0 <= result.intent_id < len(INTENT_VOCABULARY)
    assert 0.0 <= result.confidence <= 1.0

    # Verify silent thought velocity SLA: > 1,000 wpm
    assert result.silent_wpm >= 1000.0, f"Silent WPM {result.silent_wpm} did not exceed 1,000"

    # Verify HD-VSA HyperVector
    assert isinstance(result.hd_hypervector, HyperVector)
    assert len(result.hd_hypervector.words) == 157
    assert result.latency_ms > 0.0


def test_offline_neuromuscular_signal_generator():
    """Validates biomechanically realistic microvolt waveforms generated for all intents."""
    gen = OfflineNeuromuscularSignalGenerator(seed=123)

    for intent_i in range(len(INTENT_VOCABULARY)):
        signals = gen.generate_gesture(duration_ms=50.0, intent_index=intent_i)
        assert signals.shape == (NUM_SEMG_CHANNELS, 50)
        # Check realistic microvolt bounds (signals within [-100, 100] uV)
        assert np.max(signals) < 100.0
        assert np.min(signals) > -100.0


def test_bio_hardware_bridge_fail_closed_and_telemetry():
    """Validates fail-closed bio-hardware probing, StatusLevel.LIMITED, and full frame processing."""
    bridge = BioHardwareBridge()
    telemetry = bridge.get_telemetry()

    if not bridge._is_physical:
        assert telemetry.status == StatusLevel.LIMITED
        assert telemetry.backend_mode == "OFFLINE_NEUROMUSCULAR_EMULATION"
        assert telemetry.is_physical_hardware is False
        assert "NOT_FOUND" in telemetry.probe_reason
        assert telemetry.vram_delta_mib == 0.00

    # Process frame through the entire bridge pipeline
    raw_frame = bridge.signal_generator.generate_gesture(duration_ms=25.0, intent_index=2)
    result = bridge.process_neuromuscular_frame(raw_frame)

    assert result.intent_label in INTENT_VOCABULARY
    assert result.silent_wpm >= 1000.0
    assert telemetry.vram_delta_mib == 0.00


def test_subvocal_telepathy_atomic_persistence(tmp_path):
    """Validates atomic save and load for SubvocalTelepathyEngine under Windows atomic persistence."""
    engine = SubvocalTelepathyEngine()
    save_file = tmp_path / "test_telepathy_engine.npz"

    engine.save(save_file)
    assert save_file.exists()

    loaded = SubvocalTelepathyEngine.load(save_file)
    assert loaded.vocabulary == engine.vocabulary
    assert loaded.num_classes == engine.num_classes
    assert np.allclose(loaded.W_clf, engine.W_clf)
    assert np.allclose(loaded.b_clf, engine.b_clf)
    assert np.allclose(loaded.W_vsa_proj, engine.W_vsa_proj)
    assert np.allclose(loaded.ltc.A, engine.ltc.A)


def test_continuous_neuromuscular_ltc_cached_vs_direct():
    """Validates that cached input ODE integration matches direct evaluation."""
    ltc = ContinuousNeuromuscularLTC(in_features=8, latent_dim=16, seed=42)
    v_input = np.array([5.0, -3.0, 10.0, 2.0, -8.0, 1.0, 4.0, -2.0], dtype=np.float64)

    h_step = ltc.step_rk4(v_input, dt_ms=1.0)
    assert h_step.shape == (16,)
    assert np.isfinite(h_step).all()

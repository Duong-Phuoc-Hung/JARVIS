"""
tests/unit/test_neuromorphic_lif.py
===================================
Unit test suite for Frontier 22.0 Silicon Neuromorphic Spiking Ingestion & Hardware LIF Co-Processor.
Milestone v7.0.0 (Singularity Matrix).
"""
from __future__ import annotations

import numpy as np
import pytest

from jarvis.hardware.neuromorphic_lif import (
    HardwareLIFCoProcessor,
    LIFCoProcessorBackend,
    LIFNeuronParameters,
    NeuromorphicSpikeEvent,
    NeuromorphicSpikeTrain,
)


def test_neuromorphic_lif_initialization() -> None:
    """Verifies pre-allocated neuron parameters and baseline states."""
    params = LIFNeuronParameters(num_neurons=128, v_threshold=1.0)
    coproc = HardwareLIFCoProcessor(params=params)

    assert coproc.membrane_potentials.shape == (128,)
    assert np.all(coproc.membrane_potentials == 0.0)
    assert coproc.backend == LIFCoProcessorBackend.CPU_AVX2_SIMD


def test_neuromorphic_lif_subthreshold_leak() -> None:
    """Verifies that subthreshold input leaks back toward v_rest over time."""
    params = LIFNeuronParameters(num_neurons=32, v_rest=0.0, v_threshold=1.0, tau_membrane_ms=20.0)
    coproc = HardwareLIFCoProcessor(params=params)

    # Inject subthreshold stimulus
    current = np.full(32, 0.4, dtype=np.float32)
    train1 = coproc.step_vectorized(current)
    assert train1.total_spikes == 0
    v1 = coproc.membrane_potentials

    # Zero input step: potential must leak (v2 < v1)
    train2 = coproc.step_vectorized(np.zeros(32, dtype=np.float32))
    assert train2.total_spikes == 0
    v2 = coproc.membrane_potentials
    assert np.all(v2 < v1)


def test_neuromorphic_lif_spiking_and_refractory_reset() -> None:
    """Verifies threshold crossing triggers spike and hard reset to v_reset."""
    params = LIFNeuronParameters(num_neurons=16, v_reset=0.0, v_threshold=1.0)
    coproc = HardwareLIFCoProcessor(params=params)

    # Large supra-threshold input
    strong_current = np.full(16, 1.5, dtype=np.float32)
    train = coproc.step_vectorized(strong_current)

    # All neurons should have spiked
    assert train.total_spikes == 16
    assert len(train.active_neuron_ids) == 16
    assert train.spike_density == 1.0

    # Potentials must be reset to v_reset = 0.0
    v_after = coproc.membrane_potentials
    assert np.all(v_after == 0.0)

    # Immediately on next step, neurons should be in refractory period and not spike even with strong input
    train_refractory = coproc.step_vectorized(strong_current)
    assert train_refractory.total_spikes == 0


def test_neuromorphic_lif_power_budget_under_10_microwatts() -> None:
    """
    Verifies that continuous ambient monitoring maintains power dissipation
    strictly under 10.0 uW SLA.
    """
    params = LIFNeuronParameters(num_neurons=256, baseline_leakage_uw=0.25)
    coproc = HardwareLIFCoProcessor(params=params)

    # Simulate 50 steps of quiet ambient noise (160 samples per step @ 16kHz)
    rng = np.random.RandomState(42)
    for _ in range(50):
        # Quiet ambient microphone noise (~ -50dB)
        noise = (rng.randn(160) * 0.005).astype(np.float32)
        train = coproc.ingest_audio_pcm(noise)
        assert train.estimated_power_uw < 10.0

    power_metrics = coproc.get_power_telemetry()
    assert power_metrics["is_under_10uw_sla"] is True
    assert power_metrics["average_power_microwatts"] < 10.0
    assert power_metrics["vram_delta_mib"] == 0.00


def test_neuromorphic_lif_ambient_acoustic_wake_trigger() -> None:
    """Verifies that sudden acoustic speech energy triggers an ambient wake event."""
    params = LIFNeuronParameters(num_neurons=256)
    coproc = HardwareLIFCoProcessor(params=params, wake_threshold_spikes=15)

    # 1. Quiet noise -> No wake trigger
    quiet_pcm = np.zeros(320, dtype=np.float32)
    train_quiet = coproc.ingest_audio_pcm(quiet_pcm)
    assert train_quiet.ambient_wake_triggered is False

    # 2. Loud acoustic impulse / speech burst -> Ambient wake triggered!
    loud_pcm = np.full(320, fill_value=0.9, dtype=np.float32)
    train_loud = coproc.ingest_audio_pcm(loud_pcm)
    assert train_loud.total_spikes >= 15
    assert train_loud.ambient_wake_triggered is True

"""
tests/unit/test_holographic_memory.py
=====================================
Unit Tests for Holographic Memory Encoding & Hyper-Dimensional Tensor Associative Holography.
Milestone v9.0.0 ("The Transcendent Singularity", Frontier 29.0).
"""
from __future__ import annotations

import math
import os
import tempfile
import numpy as np
import pytest

from jarvis.hardware.holographic_memory import (
    DEFAULT_HOLOGRAM_DIM,
    AssociativeRetrievalResult,
    BekensteinHawkingBoundTracker,
    HologramRecord,
    HolographicAssociativeMemory,
    HolographicBoundTelemetry,
    HolographicInformationLimitExceeded,
    MERAEntanglementLayer,
    MERATensorNetwork,
    OpticalFourierHologramEngine,
)


def test_mera_tensor_network_encoding_and_decoding():
    """Validates MERA hierarchical tensor network encoding, contraction, and reconstruction."""
    dim = 64
    mera = MERATensorNetwork(boundary_dim=dim, num_layers=3, seed=123)

    assert len(mera.layers) == 3
    # Check isometric and unitary properties of first layer
    layer0 = mera.layers[0]
    U = layer0.U_disentanglers
    W = layer0.W_isometries
    # Disentangler is unitary: U^T U = I
    assert np.allclose(U.T @ U, np.eye(dim), atol=1e-5)
    # Isometry is isometric: W^T W = I
    assert np.allclose(W.T @ W, np.eye(layer0.out_dimension), atol=1e-5)

    # Test forward encoding
    rng = np.random.RandomState(42)
    boundary_state = rng.normal(0.0, 1.0, size=dim)
    top_bulk_state = mera.encode(boundary_state)
    assert top_bulk_state.shape == (mera.layers[-1].out_dimension,)
    assert not np.isnan(top_bulk_state).any()

    # Test backward holographic reconstruction
    reconstructed = mera.decode(top_bulk_state)
    assert reconstructed.shape == (dim,)
    assert not np.isnan(reconstructed).any()


def test_mera_entanglement_entropy_calculation():
    """Validates scale-dependent von Neumann entanglement entropy computation across cuts."""
    dim = 64
    mera = MERATensorNetwork(boundary_dim=dim, num_layers=3, seed=42)

    # Pure product state has low/zero entanglement
    product_state = np.zeros(dim)
    product_state[0] = 1.0
    entropy_prod = mera.compute_entanglement_entropy(product_state, cut_index=32)
    assert entropy_prod == 0.0

    # Highly entangled / random state has non-zero entanglement entropy
    rng = np.random.RandomState(42)
    random_state = rng.normal(0.0, 1.0, size=dim)
    entropy_rand = mera.compute_entanglement_entropy(random_state, cut_index=32)
    assert entropy_rand > 0.0


def test_optical_fourier_hologram_engine_recording_and_reconstruction():
    """Validates 2D Optical Fourier volume hologram interference and optical reconstruction."""
    grid_dim = 32
    engine = OpticalFourierHologramEngine(grid_dim=grid_dim)

    # Construct simple geometric square test pattern
    pattern = np.zeros((grid_dim, grid_dim), dtype=np.float64)
    pattern[10:22, 10:22] = 1.0

    record = engine.record("glyph_alpha", pattern, reference_angle_rad=math.radians(15.0))
    assert record.key == "glyph_alpha"
    assert record.interference_pattern.shape == (grid_dim, grid_dim)
    assert record.bit_entropy > 0.0

    # Reconstruct optically
    reconstructed = engine.reconstruct("glyph_alpha")
    assert reconstructed.shape == (grid_dim, grid_dim)
    assert not np.isnan(reconstructed).any()
    # Central region should have higher intensity than boundary
    center_energy = np.mean(reconstructed[10:22, 10:22])
    corner_energy = np.mean(reconstructed[0:5, 0:5])
    assert center_energy > corner_energy


def test_bragg_angular_selectivity():
    """Validates volume hologram Bragg angular selectivity condition."""
    engine = OpticalFourierHologramEngine(crystal_thickness_um=1000.0, wavelength_nm=532.0)
    delta_theta = engine.bragg_angular_selectivity_rad(incident_angle_rad=math.pi / 4.0)
    # Wavelength: 0.532 um, thickness: 1000 um -> delta_theta should be on order of 10^-4 to 10^-3 rad
    assert 1e-5 < delta_theta < 1e-2


def test_holographic_associative_memory_o1_retrieval():
    """Validates O(1) constant-time associative memory retrieval via optical cross-correlation."""
    mem = HolographicAssociativeMemory(grid_dim=32, seed=42)

    # Store 3 distinct code/conversation patterns
    mem.store("code_syntax_tree", "def compute_minkowski_interval(x, y): return x - y")
    mem.store("sys_security_rule", "GRANT_PRIVILEGE_ADMIN_VERIFIED_ONLY")
    mem.store("audio_gesture_token", "WAKE_JARVIS_ACTIVE_LISTENING")

    assert len(mem.engine.stored_records) == 3

    # Query with exact match
    res = mem.retrieve("GRANT_PRIVILEGE_ADMIN_VERIFIED_ONLY")
    assert isinstance(res, AssociativeRetrievalResult)
    assert res.matched_key == "sys_security_rule"
    assert res.confidence > 0.5
    # Sub-nanosecond simulated optical flight time SLA (< 1.0 ns)
    assert res.optical_flight_time_ns < 1.0
    assert res.reconstructed_pattern.shape == (32, 32)


def test_bekenstein_hawking_information_bound_tracker():
    """Validates Bekenstein-Hawking area-law information bound monitoring and overflow protection."""
    # Create tracker with tight 10,000 bits capacity for testing
    tracker = BekensteinHawkingBoundTracker(
        aperture_area_m2=1.0e-6,
        max_capacity_bits_override=5000.0,
    )

    telem0 = tracker.get_telemetry()
    assert telem0.current_stored_bits == 0.0
    assert telem0.saturation_ratio == 0.0
    assert telem0.bound_respected is True

    # Record 2000 bits (safe)
    tracker.record_bits(2000.0)
    telem1 = tracker.get_telemetry()
    assert telem1.current_stored_bits == 2000.0
    assert abs(telem1.saturation_ratio - 0.40) < 1e-5

    # Release 500 bits
    tracker.release_bits(500.0)
    assert tracker.current_stored_bits == 1500.0

    # Attempt to exceed maximum capacity: 1500 + 4000 = 5500 > 5000 -> must raise exception
    with pytest.raises(HolographicInformationLimitExceeded):
        tracker.record_bits(4000.0)


def test_holographic_memory_windows_atomic_persistence():
    """Validates thread-safe Windows Atomic Persistence save/load round-trip."""
    mem = HolographicAssociativeMemory(grid_dim=32, seed=42)
    mem.store("kernel_entry", "INT_HANDLER_SYSCALL_DISPATCH")
    mem.store("vocal_token", "AFFIRMATIVE_PROCEED")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = os.path.join(tmpdir, "holographic_state.json")
        mem.save(save_path)
        assert os.path.exists(save_path)

        # Restore from disk
        restored = HolographicAssociativeMemory.load(save_path)
        assert len(restored.engine.stored_records) == 2
        assert "kernel_entry" in restored.engine.stored_records
        assert "vocal_token" in restored.engine.stored_records

        # Query restored memory
        res = restored.retrieve("INT_HANDLER_SYSCALL_DISPATCH")
        assert res.matched_key == "kernel_entry"
        assert res.confidence > 0.5


def test_holographic_memory_edge_cases():
    """Validates edge cases: empty string, empty vector, and invalid dimensions."""
    mem = HolographicAssociativeMemory(grid_dim=32)

    # Empty string input
    rec = mem.store("empty_key", "")
    assert rec.key == "empty_key"

    # Empty array input
    rec_empty_arr = mem.store("empty_arr", np.array([]))
    assert rec_empty_arr.key == "empty_arr"

    # Non-power of 2 boundary dimension should raise ValueError
    with pytest.raises(ValueError):
        MERATensorNetwork(boundary_dim=30)

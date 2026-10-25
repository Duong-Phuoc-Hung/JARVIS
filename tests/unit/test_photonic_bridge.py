"""
tests/unit/test_photonic_bridge.py
==================================
Unit Tests for Coherent Photonic-Accelerated Tensor-Core Matrix Multiplications.
Milestone v8.0.0 ("The Omniscient Symbiont", Frontier 25.0).
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from jarvis.hardware.photonic_bridge import (
    MZICell,
    MZIMesh,
    PhotonicHardwareBridge,
    PhotonicTensorCore,
)
from jarvis.ui.terminal.theme import StatusLevel


def _generate_random_unitary(N: int, seed: int = 42) -> np.ndarray:
    """Helper creating an N x N Haar-random unitary matrix."""
    rng = np.random.RandomState(seed)
    X = rng.normal(0.0, 1.0, size=(N, N)) + 1j * rng.normal(0.0, 1.0, size=(N, N))
    Q, R = np.linalg.qr(X)
    d = np.diagonal(R)
    ph = d / np.abs(d)
    return Q * ph


def test_mzi_cell_transfer_matrix_unitarity():
    """Validates that a single 2-mode MZI transfer matrix is strictly unitary."""
    angles = [
        (0.0, 0.0),
        (math.pi / 4.0, math.pi / 3.0),
        (math.pi / 2.0, 0.5),
        (-0.7, 1.8),
    ]
    for th, ph in angles:
        cell = MZICell(mode_i=0, mode_j=1, theta=th, phi=ph)
        M = cell.transfer_matrix()
        assert M.shape == (2, 2)
        assert np.allclose(M @ M.conj().T, np.eye(2), atol=1e-12)


def test_clements_mzi_decomposition_exact_reconstruction():
    """Validates exact analytical Clements decomposition and reconstruction error < 10^-12."""
    for dim in [3, 4, 6]:
        U = _generate_random_unitary(dim, seed=dim * 17)
        mesh = MZIMesh.decompose(U)

        expected_cells = dim * (dim - 1) // 2
        assert len(mesh.cells) == expected_cells
        assert len(mesh.diagonal_phases) == dim

        U_rec = mesh.reconstruct_unitary(phase_noise_std=0.0)
        frob_err = float(np.linalg.norm(U - U_rec))
        assert frob_err < 1e-12, f"Reconstruction error {frob_err} exceeded 1e-12 for dim={dim}"

        # Test apply
        x = np.ones(dim, dtype=np.complex128)
        y_direct = U @ x
        y_mesh = mesh.apply(x)
        assert np.allclose(y_direct, y_mesh, atol=1e-12)


def test_photonic_tensor_core_forward_and_physical_telemetry():
    """Validates passive optical inference, sub-10ps latency SLA, and physical power metrics."""
    core = PhotonicTensorCore(
        dimension=4,
        phase_noise_std=0.005,
        laser_power_mw=12.0,
        waveguide_length_mm=0.8,
    )

    # Verify optical latency SLA: tau = L / v_group < 10 ps
    assert core.optical_latency_ps < 10.0
    assert core.optical_latency_ps > 0.0

    U = _generate_random_unitary(4, seed=101)
    mesh = MZIMesh.decompose(U)
    X = np.random.RandomState(42).normal(0.0, 1.0, size=(4, 8)) + 1j * 0.0

    # 1. Without phase noise
    Y_ideal, metrics_ideal = core.forward_unitary(mesh, X, simulate_phase_noise=False)
    assert np.allclose(Y_ideal, U @ X, atol=1e-12)
    assert metrics_ideal.optical_latency_ps < 10.0
    assert metrics_ideal.total_power_dissipation_mw > metrics_ideal.laser_power_mw
    assert metrics_ideal.vram_delta_mib == 0.00

    # 2. With modeled phase noise
    Y_noisy, metrics_noisy = core.forward_unitary(mesh, X, simulate_phase_noise=True, seed=42)
    assert metrics_noisy.signal_to_noise_ratio_db > 20.0
    # Difference should be bounded by noise level
    diff = np.linalg.norm(Y_noisy - Y_ideal) / np.linalg.norm(Y_ideal)
    assert diff < 0.10


def test_general_matrix_svd_factorization():
    """Validates SVD decomposition of arbitrary linear layer into dual optical MZI meshes."""
    core = PhotonicTensorCore(dimension=4)
    rng = np.random.RandomState(42)
    W = rng.normal(0.0, 1.0, size=(4, 4))

    mesh_U, s, mesh_V = core.factorize_general_matrix(W)

    U_mat = mesh_U.reconstruct_unitary()
    V_mat = mesh_V.reconstruct_unitary()
    Sigma_mat = np.diag(s)

    # Reconstruct W = U * Sigma * V^H
    W_rec = U_mat @ Sigma_mat @ V_mat.conj().T
    assert np.allclose(W, W_rec, atol=1e-12)


def test_photonic_hardware_bridge_fail_closed_and_telemetry():
    """Validates fail-closed hardware discovery and zero synthetic data invariant (Rule 2 AGENTS.md)."""
    bridge = PhotonicHardwareBridge()
    telemetry = bridge.get_telemetry()

    # Unless running on specialized photonic hardware testbed, must report StatusLevel.LIMITED
    if not bridge._is_physical:
        assert telemetry.status == StatusLevel.LIMITED
        assert telemetry.backend_mode == "EMULATED_OPTICAL_AVX"
        assert telemetry.is_physical_hardware is False
        assert "NOT_FOUND" in telemetry.probe_reason
        assert telemetry.vram_delta_mib == 0.00

    # Execute matrix multiplication through bridge
    U = _generate_random_unitary(4, seed=55)
    mesh = MZIMesh.decompose(U)
    X = np.eye(4, dtype=np.complex128)

    Y, metrics = bridge.execute_matrix_multiplication(mesh, X)
    assert Y.shape == (4, 4)
    assert metrics.vram_delta_mib == 0.00

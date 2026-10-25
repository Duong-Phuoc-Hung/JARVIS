"""
tests/unit/test_quantum_tensor_policy.py
========================================
Unit Tests for Quantum-Inspired Tensor Networks & Quantum Annealing Policy Search.
Milestone v8.0.0 ("The Omniscient Symbiont", Frontier 26.0).
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from jarvis.learning.quantum_tensor_policy import (
    MatrixProductStatePolicy,
    SimulatedQuantumAnnealer,
)


def test_mps_policy_initialization_and_dimensions():
    """Validates MPS tensor train core shapes, boundary bonds chi_0=chi_K=1, and max bond limit."""
    policy = MatrixProductStatePolicy(num_stages=4, physical_dim=6, max_bond_dim=16, seed=42)
    telemetry = policy.get_telemetry()

    assert telemetry.num_stages == 4
    assert telemetry.physical_dims == [6, 6, 6, 6]
    assert all(chi <= 16 for chi in telemetry.bond_dimensions)
    assert telemetry.vram_delta_mib == 0.00

    # Verify cores
    assert policy.cores[0].shape[0] == 1
    assert policy.cores[-1].shape[2] == 1


def test_mps_canonicalization_and_entanglement_entropy():
    """Validates SVD canonicalization, bond truncation <= 32, and entanglement entropy calculation."""
    policy = MatrixProductStatePolicy(num_stages=5, physical_dim=4, max_bond_dim=12, seed=123)
    entropies = policy.canonicalize()

    assert len(entropies) == 4  # K - 1 bipartite cuts
    for s_cut in entropies:
        assert s_cut >= 0.0  # Entropy is non-negative
        # Bounded by maximum entanglement ln(chi_max)
        assert s_cut <= math.log(12) + 1e-5


def test_mps_probability_and_sampling():
    """Validates joint wave function amplitude, probability evaluation, and sequential sampling."""
    policy = MatrixProductStatePolicy(num_stages=3, physical_dim=4, max_bond_dim=8, seed=42)

    # 1. Compute amplitude and probability of a specific sequence
    actions = [1, 2, 0]
    amp = policy.compute_joint_amplitude(actions)
    prob = policy.compute_probability(actions)
    assert np.isclose(prob, amp * amp)
    assert prob >= 0.0

    # 2. Sequential sampling
    rng = np.random.RandomState(42)
    sampled_seq = policy.sample_action_sequence(temperature=1.0, rng=rng)
    assert len(sampled_seq) == 3
    for a in sampled_seq:
        assert 0 <= a < 4

    # 3. Deterministic / greedy sampling at low temperature
    sampled_cold = policy.sample_action_sequence(temperature=0.01, rng=rng)
    assert len(sampled_cold) == 3


def test_simulated_quantum_annealer_pimc_optimization():
    """Validates Path-Integral Monte Carlo quantum annealing on non-convex combinatorial cost."""
    num_spins = 12
    annealer = SimulatedQuantumAnnealer(num_spins=num_spins, num_replicas=16, gamma_0=3.0, seed=42)

    # Define an Ising spin Hamiltonian with local non-convex trap:
    # Target optimum: all spins = +1
    def cost_fn(sigma: np.ndarray) -> float:
        # Ferromagnetic interaction: prefers adjacent spins to agree
        e_inter = -np.sum(sigma[:-1] * sigma[1:])
        # Field pulling towards +1
        e_field = -2.0 * np.sum(sigma)
        # Non-convex barrier penalty if sum is zero
        barrier = 10.0 if np.abs(np.sum(sigma)) < 2 else 0.0
        return float(e_inter + e_field + barrier)

    result = annealer.optimize_macro_schedule(cost_fn, steps=150)

    assert result.trotter_replicas == 16
    assert result.best_energy <= result.initial_energy
    assert len(result.best_spins) == num_spins
    assert set(result.best_spins).issubset({-1, 1})
    assert result.execution_time_ms > 0.0
    assert result.vram_delta_mib == 0.00


def test_quantum_annealing_macro_scheduling():
    """Validates macro scheduling conflict minimization under simulated quantum annealing."""
    # 6 tasks: find binary assignment {-1, +1} to split onto 2 execution lanes
    # to balance runtimes and minimize cross-lane conflict
    runtimes = np.array([12.0, 8.0, 15.0, 6.0, 20.0, 9.0])
    conflict_matrix = np.array([
        [0, 5, 0, 0, 0, 2],
        [5, 0, 3, 0, 0, 0],
        [0, 3, 0, 4, 0, 0],
        [0, 0, 4, 0, 6, 0],
        [0, 0, 0, 6, 0, 7],
        [2, 0, 0, 0, 7, 0],
    ])

    def scheduling_cost(sigma: np.ndarray) -> float:
        # Balance difference between lane 1 (sigma=+1) and lane 2 (sigma=-1)
        load_diff = abs(np.sum(runtimes * sigma))
        # Conflict if two conflicting tasks are on the same lane (sigma_i * sigma_j = +1)
        cross_lane = 0.5 * (1 + np.outer(sigma, sigma))
        conflict_cost = np.sum(conflict_matrix * cross_lane)
        return float(load_diff + conflict_cost)

    annealer = SimulatedQuantumAnnealer(num_spins=6, num_replicas=12, seed=99)
    result = annealer.optimize_macro_schedule(scheduling_cost, steps=100)

    assert result.best_energy < result.initial_energy or result.best_energy < 50.0
    assert result.vram_delta_mib == 0.00


def test_quantum_annealing_tunneling_events_non_zero():
    """Validates that uphill barrier tunneling events are accurately recorded during PIMC annealing."""
    annealer = SimulatedQuantumAnnealer(num_spins=8, num_replicas=8, gamma_0=3.0, seed=42)
    # Define a barrier function where escaping requires uphill flips
    def barrier_cost(sigma: np.ndarray) -> float:
        return float(-np.sum(sigma) + 5.0 * (1 if np.sum(sigma) == 0 else 0))

    result = annealer.optimize_macro_schedule(barrier_cost, steps=60)
    assert result.tunneling_events_count > 0, "Tunneling events must be > 0 when crossing barrier"


def test_mps_greedy_zero_temperature_sampling():
    """Validates deterministic greedy argmax sampling when temperature <= 0.0."""
    policy = MatrixProductStatePolicy(num_stages=3, physical_dim=4, max_bond_dim=8, seed=42)
    seq1 = policy.sample_action_sequence(temperature=0.0)
    seq2 = policy.sample_action_sequence(temperature=0.0)
    assert seq1 == seq2, "Greedy sampling with temperature=0.0 must be strictly deterministic"


def test_mps_atomic_persistence(tmp_path):
    """Validates atomic save and load for MatrixProductStatePolicy under Windows atomic persistence."""
    policy = MatrixProductStatePolicy(num_stages=4, physical_dim=6, max_bond_dim=16, seed=42)
    save_file = tmp_path / "test_mps_policy.npz"

    policy.save(save_file)
    assert save_file.exists()

    loaded = MatrixProductStatePolicy.load(save_file)
    assert loaded.num_stages == policy.num_stages
    assert loaded.physical_dim == policy.physical_dim
    assert loaded.max_bond_dim == policy.max_bond_dim
    for k in range(policy.num_stages):
        assert np.allclose(loaded.cores[k], policy.cores[k])


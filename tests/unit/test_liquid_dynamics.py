"""
tests/unit/test_liquid_dynamics.py
==================================
Unit test suite for Frontier 21.0 Continuous Topological Liquid Time-Constant Neural Dynamics.
Milestone v7.0.0 (Singularity Matrix).
"""
from __future__ import annotations

import numpy as np
import pytest

from jarvis.audio.liquid_dynamics import (
    LiquidStateSpaceNetwork,
    LiquidTimeConstantConfig,
    LiquidTrajectoryMetrics,
    LTCSolverType,
)


def test_liquid_state_space_network_initialization() -> None:
    """Verifies proper dimension allocation and Lyapunov-stable matrix construction."""
    config = LiquidTimeConstantConfig(hidden_dim=32, input_dim=16)
    ltc = LiquidStateSpaceNetwork(config)

    assert ltc.state.shape == (32,)
    assert np.all(ltc.state == 0.0)
    assert ltc.A.shape == (32, 32)
    assert ltc.B.shape == (32, 16)
    assert ltc.W_gate.shape == (32, 16)

    # Check Lyapunov negative-definiteness of A: all eigenvalues should have negative real parts
    eigvals = np.linalg.eigvals(ltc.A)
    assert np.all(np.real(eigvals) < 0.0)


def test_liquid_state_space_rk4_step() -> None:
    """Tests forward integration via Runge-Kutta 4th order."""
    config = LiquidTimeConstantConfig(hidden_dim=16, input_dim=8, solver=LTCSolverType.RUNGE_KUTTA_4)
    ltc = LiquidStateSpaceNetwork(config)

    x = np.ones(8, dtype=np.float32)
    next_h = ltc.step(x)

    assert next_h.shape == (16,)
    assert not np.all(next_h == 0.0)
    assert not np.isnan(next_h).any()

    metrics = ltc.get_metrics()
    assert metrics["total_steps"] == 1
    assert metrics["is_lyapunov_stable"] is True
    assert metrics["vram_delta_mib"] == 0.00


def test_liquid_state_space_semi_implicit_euler() -> None:
    """Tests semi-implicit Euler integration stability."""
    config = LiquidTimeConstantConfig(hidden_dim=16, input_dim=8, solver=LTCSolverType.SEMI_IMPLICIT_EULER)
    ltc = LiquidStateSpaceNetwork(config)

    for _ in range(10):
        x = np.random.randn(8).astype(np.float32)
        h = ltc.step(x)
        assert not np.isnan(h).any()

    metrics = ltc.get_metrics()
    assert metrics["total_steps"] == 10
    assert metrics["energy_bound"] >= 0.0


def test_liquid_state_space_speaking_rate_invariance() -> None:
    """
    Verifies that topological phase-space trajectory remains invariant (> 0.75 alignment)
    when the same underlying phonetic content is uttered at 80 wpm vs 300 wpm.
    """
    config = LiquidTimeConstantConfig(hidden_dim=32, input_dim=16)
    ltc = LiquidStateSpaceNetwork(config)

    # Generate synthetic speech acoustic pattern: 5 distinct acoustic phoneme clusters
    rng = np.random.RandomState(42)
    phoneme_prototypes = [rng.randn(16).astype(np.float32) for _ in range(5)]

    # Slow speech (80 wpm): each phoneme lasts 20 frames = 100 frames total
    frames_slow = []
    for p in phoneme_prototypes:
        for _ in range(20):
            frames_slow.append(p + rng.randn(16) * 0.05)
    seq_slow = np.array(frames_slow, dtype=np.float32)

    # Fast speech (300 wpm): each phoneme lasts 5 frames = 25 frames total
    frames_fast = []
    for p in phoneme_prototypes:
        for _ in range(5):
            frames_fast.append(p + rng.randn(16) * 0.05)
    seq_fast = np.array(frames_fast, dtype=np.float32)

    invariance_score = ltc.compute_speaking_rate_invariance_score(seq_slow, seq_fast)
    # The topological trajectory alignment should be high (> 0.75) despite 4x temporal compression
    assert invariance_score > 0.75


def test_liquid_state_space_reset_and_dimension_validation() -> None:
    """Tests state resetting and dimension mismatch error handling."""
    config = LiquidTimeConstantConfig(hidden_dim=16, input_dim=8)
    ltc = LiquidStateSpaceNetwork(config)

    ltc.step(np.ones(8, dtype=np.float32))
    assert np.any(ltc.state != 0.0)

    ltc.reset_state()
    assert np.all(ltc.state == 0.0)

    # Mismatched dimension should raise ValueError
    with pytest.raises(ValueError):
        ltc.step(np.ones(12, dtype=np.float32))

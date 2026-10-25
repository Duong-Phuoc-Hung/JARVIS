"""
tests/unit/test_reversible_computing.py
=======================================
Unit Tests for Thermodynamic Reversible Computing & Landauer Bound Minimization.
Milestone v8.0.0 ("The Omniscient Symbiont", Frontier 24.0).
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from jarvis.core.hd_vsa import HD_DIMENSION_BITS, HyperVector
from jarvis.hardware.reversible_computing import (
    K_BOLTZMANN,
    AdiabaticMemoryRecycler,
    FeynmanGate,
    FredkinGate,
    LandauerEntropyTracker,
    ReversibleBlock,
    ReversibleVSAEngine,
    ToffoliGate,
)


def test_toffoli_gate_bijective_and_self_inverse():
    """Validates Toffoli CCNOT gate bijectivity, truth table, and self-inversion."""
    # Test truth table exhaustively across all 8 states
    expected_outputs = {
        (0, 0, 0): (0, 0, 0),
        (0, 0, 1): (0, 0, 1),
        (0, 1, 0): (0, 1, 0),
        (0, 1, 1): (0, 1, 1),
        (1, 0, 0): (1, 0, 0),
        (1, 0, 1): (1, 0, 1),
        (1, 1, 0): (1, 1, 1),  # Flipped
        (1, 1, 1): (1, 1, 0),  # Flipped
    }

    seen_outputs = set()
    for (a, b, c), expected in expected_outputs.items():
        out = ToffoliGate.apply(a, b, c)
        assert out == expected, f"Failed on input {(a, b, c)}"
        seen_outputs.add(out)

        # Verify self-inverse: Toffoli(Toffoli(x)) == x
        inv = ToffoliGate.apply(*out)
        assert inv == (a, b, c), f"Self-inverse failed for {(a, b, c)}"

    # Bijectivity: 8 distinct inputs produce 8 distinct outputs
    assert len(seen_outputs) == 8

    # Verify unitary permutation matrix
    P = ToffoliGate.permutation_matrix()
    assert P.shape == (8, 8)
    assert np.allclose(P @ P.T, np.eye(8))
    assert np.allclose(P @ P, np.eye(8))  # P^2 = I

    # Vectorized test
    a_arr = np.array([0, 1, 1, 0], dtype=np.uint8)
    b_arr = np.array([0, 1, 0, 1], dtype=np.uint8)
    c_arr = np.array([1, 0, 1, 1], dtype=np.uint8)
    va, vb, vc = ToffoliGate.apply_vectorized(a_arr, b_arr, c_arr)
    assert np.array_equal(va, a_arr)
    assert np.array_equal(vb, b_arr)
    assert np.array_equal(vc, np.array([1, 1, 1, 1], dtype=np.uint8))


def test_fredkin_gate_conservative_logic():
    """Validates Fredkin CSWAP gate conservative logic (Hamming weight conservation) and bijectivity."""
    expected_outputs = {
        (0, 0, 0): (0, 0, 0),
        (0, 0, 1): (0, 0, 1),
        (0, 1, 0): (0, 1, 0),
        (0, 1, 1): (0, 1, 1),
        (1, 0, 0): (1, 0, 0),
        (1, 0, 1): (1, 1, 0),  # Swapped
        (1, 1, 0): (1, 0, 1),  # Swapped
        (1, 1, 1): (1, 1, 1),
    }

    seen_outputs = set()
    for (c, a, b), expected in expected_outputs.items():
        out = FredkinGate.apply(c, a, b)
        assert out == expected, f"Failed on Fredkin input {(c, a, b)}"
        seen_outputs.add(out)

        # Conservative logic invariant: input Hamming weight == output Hamming weight
        assert (c + a + b) == sum(out)

        # Self-inverse
        inv = FredkinGate.apply(*out)
        assert inv == (c, a, b)

    assert len(seen_outputs) == 8

    # Matrix representation
    P = FredkinGate.permutation_matrix()
    assert np.allclose(P @ P.T, np.eye(8))
    assert np.allclose(P @ P, np.eye(8))


def test_feynman_gate_cnot():
    """Validates Feynman CNOT gate and bijectivity."""
    expected_outputs = {
        (0, 0): (0, 0),
        (0, 1): (0, 1),
        (1, 0): (1, 1),
        (1, 1): (1, 0),
    }

    seen = set()
    for (a, b), expected in expected_outputs.items():
        out = FeynmanGate.apply(a, b)
        assert out == expected
        seen.add(out)

        # Self inverse
        inv = FeynmanGate.apply(*out)
        assert inv == (a, b)

    assert len(seen) == 4

    P = FeynmanGate.permutation_matrix()
    assert np.allclose(P @ P.T, np.eye(4))
    assert np.allclose(P @ P, np.eye(4))


def test_landauer_entropy_tracker():
    """Validates physical Landauer limit computation and alert triggering."""
    tracker = LandauerEntropyTracker(temperature_kelvin=300.0, dissipation_alert_threshold_joules=1.0e-18)

    # 1. Reversible operation records 0 entropy and 0 heat
    tracker.record_reversible_op("toffoli_1", bit_width=3)
    t = tracker.get_telemetry()
    assert t.reversible_ops_count == 1
    assert t.erased_bits_count == 0
    assert t.entropy_generated_j_k == 0.0
    assert t.heat_dissipated_joules == 0.0
    assert t.is_landauer_optimal is True
    assert t.alert_triggered is False

    # 2. Record 1 bit erasure
    # Q >= k_B * T * ln(2) approx 2.8704e-21 J
    heat_1 = tracker.record_bit_erasure(1)
    expected_q1 = K_BOLTZMANN * 300.0 * math.log(2.0)
    assert np.isclose(heat_1, expected_q1, rtol=1e-5)

    # 3. Non-uniform erasure
    tracker.record_bit_erasure(2, probabilities=[0.8, 0.2])
    t2 = tracker.get_telemetry()
    assert t2.erased_bits_count == 3
    assert t2.is_landauer_optimal is False

    # 4. Trigger alert by erasing sufficient bits
    tracker.record_bit_erasure(1000)
    t3 = tracker.get_telemetry()
    assert t3.alert_triggered is True
    assert "exceeded" in str(t3.alert_reason)


def test_adiabatic_memory_recycler():
    """Validates Bennett's compute-uncompute paradigm with analytical unwinding."""
    tracker = LandauerEntropyTracker()
    recycler = AdiabaticMemoryRecycler(entropy_tracker=tracker)

    # Register invertible stages:
    # stage 1: x -> x + 5
    # stage 2: x -> x * 2
    # stage 3: x -> x - 3
    recycler.push_stage("add5", forward_fn=lambda x: x + 5, inverse_fn=lambda y: y - 5)
    recycler.push_stage("mul2", forward_fn=lambda x: x * 2, inverse_fn=lambda y: y / 2)
    recycler.push_stage("sub3", forward_fn=lambda x: x - 3, inverse_fn=lambda y: y + 3)

    assert recycler.tape_depth == 3

    # Forward computation starting at x = 10
    x0 = 10
    x1 = x0 + 5       # 15
    x2 = x1 * 2       # 30
    x3 = x2 - 3       # 27

    # Unwind tape analytically backwards from final state 27
    reconstructed_x0, history = recycler.unwind(x3)

    # Must recover exact initial input x = 10
    assert reconstructed_x0 == 10
    # Tape must be completely drained
    assert recycler.tape_depth == 0
    # Entropy tracker remains Landauer-optimal (0 bits erased)
    assert tracker.get_telemetry().is_landauer_optimal is True


def test_reversible_block_zero_drift():
    """Validates additive coupling reversible block with strict zero numerical drift (< 10^-7)."""
    block = ReversibleBlock()

    rng = np.random.RandomState(42)
    x1 = rng.normal(0.0, 1.0, size=(16, 32))
    x2 = rng.normal(0.0, 1.0, size=(16, 32))

    y1, y2 = block.forward(x1, x2)
    assert y1.shape == x1.shape
    assert y2.shape == x2.shape

    rec_x1, rec_x2 = block.inverse(y1, y2)
    zero_drift, max_drift = block.verify_zero_drift(x1, x2, tolerance=1e-7)

    assert zero_drift is True
    assert max_drift < 1e-7, f"Max drift {max_drift} exceeded tolerance 1e-7"


def test_reversible_vsa_engine():
    """Validates reversible HD-VSA binding, permutation, and ancilla bundling."""
    engine = ReversibleVSAEngine()

    v1 = HyperVector.from_seed("ACTION_TERMINAL")
    v2 = HyperVector.from_seed("ARG_STATUS")

    # 1. Reversible Binding
    bound = engine.bind_reversible(v1, v2)
    unbound = engine.unbind_reversible(bound, v2)
    # Must recover v1 exactly
    assert np.array_equal(unbound.words, v1.words)

    # 2. Reversible Permutation
    perm = engine.permute_reversible(v1, shifts=13)
    inv_perm = engine.inverse_permute(perm, shifts=13)
    assert np.array_equal(inv_perm.words, v1.words)

    # 3. Ancilla-Preserving Bundling
    v3 = HyperVector.from_seed("CONTEXT_DEV")
    bundle, ancilla = engine.bundle_with_ancilla([v1, v2, v3])
    assert len(ancilla) == 3
    assert np.array_equal(ancilla[0].words, v1.words)

    # 4. Permutation Entropy
    pe = engine.compute_permutation_entropy(v1)
    assert 0.0 <= pe <= 1.0

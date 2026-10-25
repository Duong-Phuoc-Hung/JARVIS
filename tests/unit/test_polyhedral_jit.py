"""
tests/unit/test_polyhedral_jit.py
=================================
Unit Tests for Self-Assembling Polyhedral JIT Compiler & Autonomous Machine Code Crystallizer.
Milestone v8.0.0 ("The Omniscient Symbiont", Frontier 28.0).
"""
from __future__ import annotations

import numpy as np
import pytest

from jarvis.hardware.polyhedral_jit import (
    AffineCacheScheduler,
    CrystallizedMemory,
    JITCompiledFunction,
    MachineCodeCrystallizer,
    PolyhedralIterationDomain,
)


def test_polyhedral_iteration_domain_affine_constraints():
    """Validates affine inequality modeling, boundary computation, and point containment."""
    # 3D iteration domain: 0 <= i < 16, 0 <= j < 32, 0 <= k < 64
    bounds = [(0, 15), (0, 31), (0, 63)]
    domain = PolyhedralIterationDomain.from_loop_bounds(bounds, names=["i", "j", "k"])

    assert domain.dimension == 3
    assert domain.num_constraints == 6

    # Test point containment
    assert domain.contains_point([0, 0, 0]) is True
    assert domain.contains_point([15, 31, 63]) is True
    assert domain.contains_point([7, 12, 45]) is True

    # Out of bounds points
    assert domain.contains_point([-1, 0, 0]) is False
    assert domain.contains_point([16, 0, 0]) is False
    assert domain.contains_point([0, 32, 0]) is False
    assert domain.contains_point([0, 0, 64]) is False

    # Compute bounds and volume
    dom_bounds = domain.compute_bounds()
    assert dom_bounds.lower_bounds == [0, 0, 0]
    assert dom_bounds.upper_bounds == [15, 31, 63]
    assert dom_bounds.volume == 16 * 32 * 64


def test_affine_cache_scheduler_unimodular_matrix_and_tiling():
    """Validates unimodular loop transformation det(T)=+/-1 and L1 cache tiling."""
    scheduler = AffineCacheScheduler(l1_cache_bytes=32768, cache_line_bytes=64)
    plan = scheduler.schedule_matmul(M=128, N=128, K=128)

    assert plan.is_unimodular is True
    assert abs(int(round(np.linalg.det(plan.transformation_matrix)))) == 1
    assert plan.transformed_loop_order == ["i", "k", "j"]
    assert plan.spatial_locality_stride == 1
    assert plan.l1_cache_utilization_ratio <= 1.0
    assert len(plan.tile_sizes) == 3


def test_machine_code_crystallizer_allocation_and_free():
    """Validates executable native memory allocation via VirtualAlloc/mmap and clean RAII release."""
    crystallizer = MachineCodeCrystallizer()
    mem = crystallizer.crystallize("dot_product")

    assert mem.address != 0
    assert mem.size >= 4096
    assert mem._is_freed is False

    # Explicit release
    mem.free()
    assert mem._is_freed is True
    assert mem.address == 0


def test_jit_compiled_function_dot_product():
    """Validates native crystallized machine code dot product execution vs numpy."""
    jit_fn = JITCompiledFunction()

    rng = np.random.RandomState(42)
    for length in [5, 16, 64, 128]:
        a = rng.normal(0.0, 1.0, size=length).astype(np.float32)
        b = rng.normal(0.0, 1.0, size=length).astype(np.float32)

        expected = float(np.dot(a, b))
        result = jit_fn.execute_dot_product(a, b)

        assert np.isclose(result, expected, rtol=1e-4, atol=1e-4), (
            f"Length {length}: result {result} != expected {expected}"
        )

    jit_fn.close()


def test_jit_compiled_function_vector_add_and_scale():
    """Validates native crystallized machine code vector add and vector scale."""
    jit_fn = JITCompiledFunction()

    rng = np.random.RandomState(101)
    a = rng.normal(0.0, 1.0, size=32).astype(np.float32)
    b = rng.normal(0.0, 1.0, size=32).astype(np.float32)
    alpha = 3.5

    # 1. Vector Add
    c_add = jit_fn.execute_vector_add(a, b)
    expected_add = a + b
    assert np.allclose(c_add, expected_add, rtol=1e-4, atol=1e-4)

    # 2. Vector Scale
    c_scale = jit_fn.execute_vector_scale(a, alpha)
    expected_scale = a * alpha
    assert np.allclose(c_scale, expected_scale, rtol=1e-4, atol=1e-4)

    # 3. Shape mismatch check
    with pytest.raises(ValueError):
        jit_fn.execute_vector_add(a, np.ones(10, dtype=np.float32))

    jit_fn.close()

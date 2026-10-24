"""
tests/unit/test_hd_vsa.py
=========================
Unit tests for Frontier 18.0 Hyperdimensional Vector Symbolic Architecture.
Sprint 26 / Milestone v6.4.0.
"""
from __future__ import annotations

import numpy as np
import pytest

from jarvis.core.hd_vsa import (
    CompoundMacroComposer,
    HD_DIMENSION_BITS,
    HD_UINT64_WORDS,
    HyperVector,
    HyperdimensionalItemMemory,
    bundle_hypervectors,
)


def test_hypervector_creation_and_properties() -> None:
    """Verifies 10,000-bit HyperVector initialization and dimensions."""
    v1 = HyperVector.random(seed=42)
    assert len(v1.words) == HD_UINT64_WORDS
    assert v1.words.dtype == np.uint64

    v_zero = HyperVector.zeros()
    assert np.all(v_zero.words == 0)

    v_one = HyperVector.ones()
    assert v_zero.hamming_distance(v_one) == HD_DIMENSION_BITS


def test_hypervector_orthogonality() -> None:
    """Verifies that two independent random hypervectors are quasi-orthogonal (~5,000 bits)."""
    v1 = HyperVector.random(seed=1)
    v2 = HyperVector.random(seed=2)

    d = v1.hamming_distance(v2)
    # Binomial(10000, 0.5): 3 sigma is 3 * sqrt(10000 * 0.25) = 150 bits -> within [4800, 5200]
    assert 4700 < d < 5300
    cos_sim = v1.cosine_similarity(v2)
    assert abs(cos_sim) < 0.08  # Nearly orthogonal


def test_hypervector_binding_xor() -> None:
    r"""Verifies that binding (\circledast) is self-inverse: A ^ B ^ B == A."""
    a = HyperVector.random(seed=10)
    b = HyperVector.random(seed=20)

    bound = a.bind(b)
    unbound = bound.bind(b)

    assert a.hamming_distance(unbound) == 0
    assert a.cosine_similarity(unbound) == 1.0


def test_hypervector_permutation() -> None:
    """Verifies cyclic shifting (\\rho^k) decorrelates vector for sequence encoding."""
    v = HyperVector.random(seed=55)
    permuted = v.permute(shifts=64)

    assert v.hamming_distance(permuted) > 4000
    assert v.cosine_similarity(permuted) < 0.20


def test_hypervector_bundling_majority() -> None:
    """Verifies bundling preserves similarity to constituent concepts."""
    v1 = HyperVector.from_seed("CLICK")
    v2 = HyperVector.from_seed("BUTTON")
    v3 = HyperVector.from_seed("SYSTEM_OS")

    bundled = bundle_hypervectors([v1, v2, v3])

    # Bundled vector should have positive cosine similarity to all 3 constituents
    assert bundled.cosine_similarity(v1) > 0.25
    assert bundled.cosine_similarity(v2) > 0.25
    assert bundled.cosine_similarity(v3) > 0.25

    # But low similarity to an unrelated concept
    unrelated = HyperVector.from_seed("UNRELATED_CONCEPT_XYZ")
    assert abs(bundled.cosine_similarity(unrelated)) < 0.15


def test_compound_macro_composer() -> None:
    """Tests multi-step desktop workflow encoding and nanosecond similarity search."""
    memory = HyperdimensionalItemMemory()
    composer = CompoundMacroComposer(item_memory=memory)

    # Define Macro A: Open Browser -> Focus URL -> Type
    macro_a_steps = [
        ("LAUNCH_APP", "BUTTON", "BROWSER_MEDIA"),
        ("CLICK", "SEARCH_BOX", "BROWSER_MEDIA"),
        ("TYPE_TEXT", "INPUT_FIELD", "BROWSER_MEDIA"),
    ]
    composer.register_macro("MACRO_BROWSER_NAV", macro_a_steps)

    # Define Macro B: Developer Terminal Git Status
    macro_b_steps = [
        ("LAUNCH_APP", "WINDOW_FRAME", "DEVELOPER_TERMINAL"),
        ("TYPE_TEXT", "INPUT_FIELD", "DEVELOPER_TERMINAL"),
        ("PRESS_KEY", "BUTTON", "DEVELOPER_TERMINAL"),
    ]
    composer.register_macro("MACRO_GIT_STATUS", macro_b_steps)

    # Query with exact steps from Macro A
    query_a = composer.encode_sequence_macro(macro_a_steps)
    best_name, sim, latency_ns = composer.search_nearest_macro(query_a)

    assert best_name == "MACRO_BROWSER_NAV"
    assert sim == 1.0
    assert latency_ns < 1_000_000.0  # Under 1 millisecond (in nanoseconds)


def test_hd_vsa_empty_registry_and_top_k() -> None:
    """Verifies safe empty-state query handling without throwing exceptions."""
    composer = CompoundMacroComposer()
    query = HyperVector.random(seed=99)
    name, sim, latency_ns = composer.search_nearest_macro(query)
    assert name is None
    assert sim == 0.0
    assert latency_ns >= 0.0

    memory = composer.memory
    assert memory.cleanup_search(query, top_k=0) == []
    assert memory.cleanup_search(query, top_k=-5) == []


def test_hd_vsa_empty_steps() -> None:
    """Verifies that an empty macro sequence encodes to all zeros."""
    composer = CompoundMacroComposer()
    zero_macro = composer.encode_sequence_macro([])
    assert np.all(zero_macro.words == 0)


"""
jarvis/core/hd_vsa.py
=====================
Hyperdimensional Vector Symbolic Architecture (HD-VSA) Engine.
Sprint 26 / Milestone v6.4.0 (Argon Frontier 18.0).

Architectural Principles:
  1. 10,000-Bit Binary Hypervectors:
     Represents compositional concepts, semantic bindings, and desktop macro sequences
     in a D = 10,000-bit binary hyperdimensional space (1,250 bytes / 157 uint64 words).
  2. VSA Algebraic Operations:
     - Binding (\\circledast): Bitwise XOR (A ^ B). Invertible, associates role-filler pairs.
     - Bundling (\\oplus): Majority-rule bitwise voting across sets of hypervectors.
     - Permutation (\\rho^k): Circular bit-rotation by k positions to encode temporal sequence.
  3. Microsecond / Nanosecond Compound Macro Search:
     Hardware POPCOUNT and bitwise XOR compute Hamming distance d_H(A, B) across
     thousands of candidate compound macro workflows in microseconds.
  4. Infinite Compositional Desktop Action Space:
     Combines atomic action verbs, target UI controls, application contexts, and step
     indices into single unified hypervector signatures that can be unbundled and queried
     with associative clean-up memory.
  5. 0.00 MiB VRAM Invariant:
     Runs 100% on CPU SIMD with packed uint64 bitwise logic, consuming 0.00 MiB GPU VRAM.
"""
from __future__ import annotations

import collections
import enum
import hashlib
import logging
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger("jarvis.core.hd_vsa")

HD_DIMENSION_BITS = 10000
HD_BYTES = (HD_DIMENSION_BITS + 7) // 8  # 1250 bytes
HD_UINT64_WORDS = (HD_DIMENSION_BITS + 63) // 64  # 157 words of 64-bit unsigned integers


@dataclass
class HyperVector:
    """Represents a 10,000-bit binary hypervector packed into uint64 words."""
    words: np.ndarray  # Shape (157,), dtype=np.uint64

    def __post_init__(self) -> None:
        if self.words.dtype != np.uint64 or len(self.words) != HD_UINT64_WORDS:
            raise ValueError(f"Expected uint64 array of shape ({HD_UINT64_WORDS},), got {self.words.shape}")
        # Mask out unused bits in the highest word
        unused_bits = (HD_UINT64_WORDS * 64) - HD_DIMENSION_BITS  # 157*64 - 10000 = 48 bits
        if unused_bits > 0:
            valid_mask = np.uint64((1 << (64 - unused_bits)) - 1)
            self.words[-1] &= valid_mask

    @classmethod
    def random(cls, seed: Optional[int] = None) -> HyperVector:
        """Generates an independent random binary hypervector."""
        rng = np.random.RandomState(seed)
        # Generate random 64-bit uints using 32-bit halves
        low = rng.randint(0, 0xFFFFFFFF, size=HD_UINT64_WORDS, dtype=np.uint32).astype(np.uint64)
        high = rng.randint(0, 0xFFFFFFFF, size=HD_UINT64_WORDS, dtype=np.uint32).astype(np.uint64)
        words = (high << np.uint64(32)) | low
        return cls(words=words)

    @classmethod
    def from_seed(cls, identifier: str) -> HyperVector:
        """Generates a deterministic hypervector from a string identifier using SHA-256."""
        hasher = hashlib.sha256()
        hasher.update(identifier.encode("utf-8"))
        seed_int = int.from_bytes(hasher.digest()[:4], byteorder="big")
        return cls.random(seed=seed_int)

    @classmethod
    def zeros(cls) -> HyperVector:
        """Creates an all-zeros hypervector."""
        return cls(words=np.zeros(HD_UINT64_WORDS, dtype=np.uint64))

    @classmethod
    def ones(cls) -> HyperVector:
        """Creates an all-ones hypervector."""
        return cls(words=np.full(HD_UINT64_WORDS, 0xFFFFFFFFFFFFFFFF, dtype=np.uint64))

    def bind(self, other: HyperVector) -> HyperVector:
        """
        Binding operation (\\circledast): Bitwise XOR.
        Invertible: A.bind(B).bind(B) == A.
        """
        return HyperVector(words=np.bitwise_xor(self.words, other.words))

    def permute(self, shifts: int = 1) -> HyperVector:
        """
        Cyclic bit-rotation (\\rho^k) over the 10,000 bits.
        Encodes sequence order in temporal macros.
        """
        shifts = shifts % HD_DIMENSION_BITS
        if shifts == 0:
            return HyperVector(words=self.words.copy())

        # Unpack to bits, roll, and repack
        bits = np.unpackbits(self.words.view(np.uint8))[:HD_DIMENSION_BITS]
        rolled_bits = np.roll(bits, shifts)
        # Pad to full byte boundary and repack
        padded = np.pad(rolled_bits, (0, HD_UINT64_WORDS * 64 - HD_DIMENSION_BITS), mode="constant")
        packed_bytes = np.packbits(padded)
        new_words = packed_bytes.view(np.uint64)[:HD_UINT64_WORDS].copy()
        return HyperVector(words=new_words)

    def hamming_distance(self, other: HyperVector) -> int:
        """
        Computes the Hamming distance d_H(A, B) via bitwise XOR and hardware popcount.
        """
        diff = np.bitwise_xor(self.words, other.words)
        # Modern NumPy 2.0+ has np.bitwise_count; fallback to Python popcount loop
        if hasattr(np, "bitwise_count"):
            return int(np.sum(np.bitwise_count(diff)))
        else:
            return sum(int(w).bit_count() for w in diff)

    def cosine_similarity(self, other: HyperVector) -> float:
        """
        Normalized bipolar cosine similarity: 1.0 - 2 * (d_H / D).
        Orthogonal vectors yield ~0.0, identical vectors yield 1.0, inverses yield -1.0.
        """
        d = self.hamming_distance(other)
        return 1.0 - 2.0 * (d / HD_DIMENSION_BITS)

    def normalized_similarity(self, other: HyperVector) -> float:
        """Normalized similarity in [0, 1]: 1.0 - (d_H / D)."""
        d = self.hamming_distance(other)
        return 1.0 - (d / HD_DIMENSION_BITS)


def bundle_hypervectors(vectors: Sequence[HyperVector]) -> HyperVector:
    """
    Bundling operation (\\oplus): Majority-rule bitwise voting.
    Superposes multiple concept vectors into a single hypervector.
    """
    if not vectors:
        raise ValueError("Cannot bundle an empty sequence of HyperVectors")
    if len(vectors) == 1:
        return HyperVector(words=vectors[0].words.copy())

    # Unpack all to bit arrays (N, 10000)
    all_bits = []
    for v in vectors:
        b = np.unpackbits(v.words.view(np.uint8))[:HD_DIMENSION_BITS]
        all_bits.append(b)
    bit_matrix = np.vstack(all_bits)

    # Sum along columns: shape (10000,)
    sums = np.sum(bit_matrix, axis=0)
    threshold = len(vectors) / 2.0

    # Strict majority
    result_bits = (sums > threshold).astype(np.uint8)

    # Break ties deterministically for even lengths
    if len(vectors) % 2 == 0:
        ties = sums == threshold
        if np.any(ties):
            # Deterministic pseudo-random tie-breaker based on position index
            tie_breakers = ((np.arange(HD_DIMENSION_BITS) * 1664525 + 1013904223) & 1).astype(np.uint8)
            result_bits[ties] = tie_breakers[ties]

    padded = np.pad(result_bits, (0, HD_UINT64_WORDS * 64 - HD_DIMENSION_BITS), mode="constant")
    packed_bytes = np.packbits(padded)
    new_words = packed_bytes.view(np.uint64)[:HD_UINT64_WORDS].copy()
    return HyperVector(words=new_words)


class HyperdimensionalItemMemory:
    """
    Associative clean-up memory storing atomic basis symbols and compound macro definitions.
    """

    def __init__(self) -> None:
        self._items: dict[str, HyperVector] = {}
        self._lock = threading.Lock()
        self._init_canonical_basis()

    def _init_canonical_basis(self) -> None:
        """Pre-calibrates canonical basis hypervectors."""
        basis_symbols = [
            # Canonical Roles
            "ROLE_ACTION",
            "ROLE_TARGET",
            "ROLE_MODIFIER",
            "ROLE_DOMAIN",
            "ROLE_STEP",
            # Verbs
            "CLICK",
            "DOUBLE_CLICK",
            "RIGHT_CLICK",
            "TYPE_TEXT",
            "PRESS_KEY",
            "DRAG_DROP",
            "LAUNCH_APP",
            "CLOSE_WINDOW",
            # Targets
            "BUTTON",
            "INPUT_FIELD",
            "SEARCH_BOX",
            "CHECKBOX",
            "DROPDOWN",
            "TAB_HEADER",
            "WINDOW_FRAME",
            # Domains
            "SYSTEM_OS",
            "WINDOW_WORKSPACE",
            "DEVELOPER_TERMINAL",
            "BROWSER_MEDIA",
        ]
        for sym in basis_symbols:
            self._items[sym] = HyperVector.from_seed(sym)

    def register_item(self, key: str, vector: HyperVector) -> None:
        """Registers a new named hypervector in item memory."""
        with self._lock:
            self._items[key] = vector

    def get_item(self, key: str) -> HyperVector:
        """Retrieves a basis or macro vector by key."""
        with self._lock:
            if key not in self._items:
                # Dynamically generate deterministic vector
                self._items[key] = HyperVector.from_seed(key)
            return self._items[key]

    def cleanup_search(self, query: HyperVector, top_k: int = 1) -> list[Tuple[str, float]]:
        """
        Associative clean-up query: finds the nearest registered basis symbols
        ranked by normalized similarity.
        Executes in microseconds.
        """
        if top_k <= 0:
            return []
        with self._lock:
            results: list[Tuple[str, float]] = []
            for name, vec in self._items.items():
                sim = query.normalized_similarity(vec)
                results.append((name, sim))
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k]

    def count(self) -> int:
        """Number of registered hypervectors."""
        with self._lock:
            return len(self._items)


class CompoundMacroComposer:
    """
    Encodes multi-step sequential desktop macro workflows into single 10,000-bit hypervectors.
    """

    def __init__(self, item_memory: Optional[HyperdimensionalItemMemory] = None) -> None:
        self.memory = item_memory or HyperdimensionalItemMemory()
        self._macro_registry: dict[str, HyperVector] = {}
        self._lock = threading.Lock()

    def encode_action_step(
        self,
        verb: str,
        target: str,
        domain: str = "SYSTEM_OS",
    ) -> HyperVector:
        """
        Binds role-filler pairs:
          Step = (ROLE_ACTION ^ Verb) ^ (ROLE_TARGET ^ Target) ^ (ROLE_DOMAIN ^ Domain)
        """
        r_act = self.memory.get_item("ROLE_ACTION")
        v_act = self.memory.get_item(verb)
        act_bind = r_act.bind(v_act)

        r_tgt = self.memory.get_item("ROLE_TARGET")
        v_tgt = self.memory.get_item(target)
        tgt_bind = r_tgt.bind(v_tgt)

        r_dom = self.memory.get_item("ROLE_DOMAIN")
        v_dom = self.memory.get_item(domain)
        dom_bind = r_dom.bind(v_dom)

        return act_bind.bind(tgt_bind).bind(dom_bind)

    def encode_sequence_macro(
        self,
        steps: Sequence[Tuple[str, str, str]],  # (verb, target, domain)
    ) -> HyperVector:
        """
        Encodes an ordered multi-step compound macro:
          H_macro = \\bigoplus_{s=1}^S \\rho^s( Step_s )
        """
        if not steps:
            return HyperVector.zeros()

        step_vectors = []
        for i, (verb, target, domain) in enumerate(steps, start=1):
            step_vec = self.encode_action_step(verb, target, domain)
            permuted = step_vec.permute(shifts=i * 64)
            step_vectors.append(permuted)

        return bundle_hypervectors(step_vectors)

    def register_macro(self, macro_name: str, steps: Sequence[Tuple[str, str, str]]) -> HyperVector:
        """Encodes and registers a named compound macro in memory."""
        vec = self.encode_sequence_macro(steps)
        with self._lock:
            self._macro_registry[macro_name] = vec
        return vec

    def search_nearest_macro(self, query_macro: HyperVector) -> Tuple[Optional[str], float, float]:
        """
        Finds the closest registered macro workflow.
        Returns (macro_name, normalized_similarity, search_latency_ns).
        """
        t0 = time.perf_counter_ns()
        with self._lock:
            if not self._macro_registry:
                t1 = time.perf_counter_ns()
                return (None, 0.0, float(t1 - t0))

            best_name: Optional[str] = None
            best_sim = -1.0
            for name, m_vec in self._macro_registry.items():
                sim = query_macro.normalized_similarity(m_vec)
                if sim > best_sim:
                    best_sim = sim
                    best_name = name
            t1 = time.perf_counter_ns()
            latency_ns = float(t1 - t0)
            return (best_name, best_sim, latency_ns)

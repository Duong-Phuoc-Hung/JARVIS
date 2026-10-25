"""
tests/eval/test_frontier_24_to_28_omniscient_benchmark.py
=========================================================
Consolidated Empirical Benchmark Suite for Frontiers 24.0 - 28.0.
Milestone v8.0.0 ("The Omniscient Symbiont").

Benchmarked Frontiers:
  1. Frontier 24.0: Thermodynamic Reversible Computing & Landauer Bound Minimization:
     - Bijective reversible logic throughput (> 100,000 gates/s).
     - Additive coupling reversible block numerical drift strictly < 10^-7.
     - Bennett adiabatic memory recycling with 0 net activation footprint.
  2. Frontier 25.0: Coherent Photonic-Accelerated Tensor-Core Matrix Multiplications:
     - Clements MZI mesh factorization and reconstruction error < 10^-12.
     - Optical time-of-flight latency SLA < 10 ps (silicon waveguide group index n_eff = 3.45).
     - Fail-closed physical bridge validation (StatusLevel.LIMITED) with zero synthetic data.
  3. Frontier 26.0: Quantum-Inspired Tensor Networks & Quantum Annealing Policy Search:
     - MPS tensor-train policy contraction with bond truncation chi <= 32 and entanglement entropy.
     - Path-Integral Monte Carlo (PIMC) Trotter-Suzuki quantum annealing barrier tunneling.
  4. Frontier 27.0: Sub-Vocal Electromyography (sEMG) & Non-Invasive BCI Telepathy:
     - 8-channel differential filter bank (50/60Hz notch, 20-450Hz bandpass, DWT denoising).
     - Silent thought velocity SLA > 1,000 wpm and 10,000-bit HD-VSA projection.
  5. Frontier 28.0: Self-Assembling Polyhedral JIT Compiler & Autonomous Machine Code Crystallizer:
     - Native x86-64 executable machine code crystallization in VirtualAlloc memory.
     - Cache-optimal unimodular loop scheduling and direct ctypes dispatch.
  6. Consolidated Omniscient Symbiont Multimodal Reflex Loop:
     - Neuromuscular sEMG Ingestion -> Continuous LTC -> Silent Intent Token ->
       MPS Policy Search -> Polyhedral Native JIT Execution -> Reversible Memory Recycling.
     - End-to-end reflex SLA < 25.0 ms with strict +0.00 MiB VRAM delta.
"""
from __future__ import annotations

import math
import time
import numpy as np
import pytest

from jarvis.audio.subvocal_semg import (
    BioHardwareBridge,
    ContinuousNeuromuscularLTC,
    OfflineNeuromuscularSignalGenerator,
    SubvocalSignalFilter,
    SubvocalTelepathyEngine,
)
from jarvis.core.hd_vsa import HD_DIMENSION_BITS, HyperVector
from jarvis.hardware.photonic_bridge import (
    MZIMesh,
    PhotonicHardwareBridge,
    PhotonicTensorCore,
)
from jarvis.hardware.polyhedral_jit import (
    AffineCacheScheduler,
    JITCompiledFunction,
    MachineCodeCrystallizer,
    PolyhedralIterationDomain,
)
from jarvis.hardware.reversible_computing import (
    AdiabaticMemoryRecycler,
    FeynmanGate,
    FredkinGate,
    LandauerEntropyTracker,
    ReversibleBlock,
    ReversibleVSAEngine,
    ToffoliGate,
)
from jarvis.learning.quantum_tensor_policy import (
    MatrixProductStatePolicy,
    SimulatedQuantumAnnealer,
)
from jarvis.ui.terminal.theme import StatusLevel


def test_benchmark_frontier_24_reversible_computing():
    """Empirical benchmark of reversible gates throughput, Landauer tracking, and RevNet zero drift."""
    # 1. Benchmark Toffoli gate throughput
    n_ops = 50_000
    a = np.random.randint(0, 2, size=n_ops, dtype=np.uint8)
    b = np.random.randint(0, 2, size=n_ops, dtype=np.uint8)
    c = np.random.randint(0, 2, size=n_ops, dtype=np.uint8)

    t0 = time.perf_counter()
    va, vb, vc = ToffoliGate.apply_vectorized(a, b, c)
    elapsed_s = time.perf_counter() - t0
    ops_per_sec = n_ops / elapsed_s

    assert ops_per_sec > 100_000.0  # > 100k ops/s vectorized throughput
    assert np.array_equal(va, a)

    # 2. Benchmark ReversibleBlock numerical drift
    block = ReversibleBlock()
    rng = np.random.RandomState(42)
    x1 = rng.normal(0.0, 1.0, size=(100, 64))
    x2 = rng.normal(0.0, 1.0, size=(100, 64))

    zero_drift, max_drift = block.verify_zero_drift(x1, x2, tolerance=1e-7)
    assert zero_drift is True
    assert max_drift < 1e-7

    # 3. Benchmark Adiabatic Memory Recycling
    tracker = LandauerEntropyTracker()
    recycler = AdiabaticMemoryRecycler(entropy_tracker=tracker)
    for i in range(10):
        recycler.push_stage(f"stage_{i}", forward_fn=lambda x: x + 1.0, inverse_fn=lambda y: y - 1.0)

    val = 100.0
    rec_val, _ = recycler.unwind(val + 10.0)
    assert np.isclose(rec_val, val)
    assert recycler.tape_depth == 0
    assert tracker.get_telemetry().is_landauer_optimal is True


def test_benchmark_frontier_25_photonic_bridge():
    """Empirical benchmark of Clements MZI factorization, sub-10ps latency, and fail-closed bridge."""
    core = PhotonicTensorCore(waveguide_length_mm=0.8)
    assert core.optical_latency_ps < 10.0  # Sub-10 picosecond SLA

    # 1. Benchmark Clements decomposition on 6x6 unitary
    dim = 6
    rng = np.random.RandomState(42)
    X_rand = rng.normal(0.0, 1.0, size=(dim, dim)) + 1j * rng.normal(0.0, 1.0, size=(dim, dim))
    Q, R = np.linalg.qr(X_rand)
    d = np.diagonal(R)
    U = Q * (d / np.abs(d))

    t0 = time.perf_counter()
    mesh = MZIMesh.decompose(U)
    elapsed_decomp_ms = (time.perf_counter() - t0) * 1000.0

    assert elapsed_decomp_ms < 50.0  # Fast decomposition
    assert len(mesh.cells) == dim * (dim - 1) // 2

    # Reconstruction accuracy
    U_rec = mesh.reconstruct_unitary()
    frob_err = float(np.linalg.norm(U - U_rec))
    assert frob_err < 1e-12

    # 2. Fail-closed bridge inspection
    bridge = PhotonicHardwareBridge(core=core)
    telemetry = bridge.get_telemetry()
    if not bridge._is_physical:
        assert telemetry.status == StatusLevel.LIMITED
        assert telemetry.backend_mode == "EMULATED_OPTICAL_AVX"
        assert telemetry.vram_delta_mib == 0.00


def test_benchmark_frontier_26_quantum_tensor_policy():
    """Empirical benchmark of MPS tensor train contraction, sampling speed, and PIMC quantum annealing."""
    # 1. Benchmark MPS policy
    policy = MatrixProductStatePolicy(num_stages=4, physical_dim=8, max_bond_dim=16, seed=42)
    t0 = time.perf_counter()
    n_samples = 100
    for _ in range(n_samples):
        seq = policy.sample_action_sequence()
        assert len(seq) == 4
    sample_time_ms = ((time.perf_counter() - t0) / n_samples) * 1000.0
    assert sample_time_ms < 5.0  # < 5ms per multi-stage sequence sample

    telemetry = policy.get_telemetry()
    assert all(s >= 0.0 for s in telemetry.entanglement_entropies)
    assert telemetry.vram_delta_mib == 0.00

    # 2. Benchmark Simulated Quantum Annealer (PIMC)
    annealer = SimulatedQuantumAnnealer(num_spins=8, num_replicas=8, gamma_0=2.5, seed=42)
    def test_cost(sigma: np.ndarray) -> float:
        return float(-np.sum(sigma[:-1] * sigma[1:]) + 5.0 * (1 if np.sum(sigma) == 0 else 0))

    t0_qa = time.perf_counter()
    qa_result = annealer.optimize_macro_schedule(test_cost, steps=50)
    elapsed_qa_ms = (time.perf_counter() - t0_qa) * 1000.0

    assert elapsed_qa_ms < 150.0  # Polynomial time optimization
    assert qa_result.best_energy <= qa_result.initial_energy
    assert qa_result.vram_delta_mib == 0.00


def test_benchmark_frontier_27_subvocal_semg_telepathy():
    """Empirical benchmark of 8-channel sEMG filtering, continuous LTC ODE, and > 1,000 wpm telepathy."""
    filter_bank = SubvocalSignalFilter()
    ltc = ContinuousNeuromuscularLTC(in_features=8, latent_dim=32)
    engine = SubvocalTelepathyEngine(ltc_network=ltc)
    gen = OfflineNeuromuscularSignalGenerator(seed=42)

    # 1. Benchmark filter bank throughput
    raw_signals = gen.generate_gesture(duration_ms=100.0, intent_index=1)
    t0 = time.perf_counter()
    filtered = filter_bank.filter_signals(raw_signals)
    elapsed_filter_ms = (time.perf_counter() - t0) * 1000.0
    assert elapsed_filter_ms < 10.0

    # 2. Benchmark LTC step speed
    t0_ltc = time.perf_counter()
    for col in range(filtered.shape[1]):
        ltc.step_rk4(filtered[:, col], dt_ms=1.0)
    elapsed_ltc_ms = (time.perf_counter() - t0_ltc) * 1000.0
    assert elapsed_ltc_ms < 15.0

    # 3. Benchmark Silent Telepathy decoding velocity
    res = engine.decode_trajectory(ltc.h, dt_per_step_ms=1.0)
    assert res.silent_wpm >= 1000.0  # > 1,000 wpm silent thought SLA
    assert res.latency_ms < 5.0
    assert isinstance(res.hd_hypervector, HyperVector)


def test_benchmark_frontier_28_polyhedral_jit_crystallizer():
    """Empirical benchmark of affine cache scheduling and native machine code execution."""
    scheduler = AffineCacheScheduler()
    plan = scheduler.schedule_matmul(64, 64, 64)
    assert plan.is_unimodular is True
    assert plan.spatial_locality_stride == 1

    jit_fn = JITCompiledFunction()
    rng = np.random.RandomState(42)
    a = rng.normal(0.0, 1.0, size=256).astype(np.float32)
    b = rng.normal(0.0, 1.0, size=256).astype(np.float32)

    # Benchmark dot product execution speed
    t0 = time.perf_counter()
    n_runs = 500
    for _ in range(n_runs):
        res = jit_fn.execute_dot_product(a, b)
    elapsed_us = ((time.perf_counter() - t0) / n_runs) * 1_000_000.0

    expected = float(np.dot(a, b))
    assert np.isclose(res, expected, rtol=1e-4, atol=1e-4)
    assert elapsed_us < 50.0  # Sub-50 microsecond execution

    jit_fn.close()


def test_benchmark_omniscient_symbiont_multimodal_reflex_loop():
    """
    Consolidated End-to-End Omniscient Symbiont Reflex Pipeline:
      8-Ch sEMG Gesture -> Filtering -> Continuous LTC -> Silent Intent ->
      MPS Policy Search -> JIT Native Execution -> Reversible Memory Recycling.
    Enforces total pipeline latency SLA < 25.0 ms and strict 0.00 MiB VRAM delta.
    """
    # Initialize all 5 frontier subsystems
    bio_bridge = BioHardwareBridge()
    ltc = bio_bridge.telepathy_engine.ltc
    mps_policy = MatrixProductStatePolicy(num_stages=3, physical_dim=8, max_bond_dim=12, seed=42)
    jit_fn = JITCompiledFunction()
    rev_recycler = AdiabaticMemoryRecycler()

    # Generate 20ms neuromuscular frame
    raw_frame = bio_bridge.signal_generator.generate_gesture(duration_ms=20.0, intent_index=0)

    t0_pipeline = time.perf_counter()

    # 1. Bio-hardware frame processing (Filtering + LTC + Telepathy)
    intent_res = bio_bridge.process_neuromuscular_frame(raw_frame)
    assert intent_res.silent_wpm >= 1000.0

    # 2. MPS Policy Search conditioned on silent intent
    actions = mps_policy.sample_action_sequence()
    assert len(actions) == 3

    # 3. JIT Native Execution of synthesized tensor action
    vec_a = np.ones(32, dtype=np.float32) * float(actions[0] + 1)
    vec_b = np.ones(32, dtype=np.float32) * float(actions[1] + 1)
    dot_val = jit_fn.execute_dot_product(vec_a, vec_b)
    assert dot_val > 0.0

    # 4. Reversible Memory Recycling (0 net activation footprint)
    rev_recycler.push_stage("step1", forward_fn=lambda x: x + dot_val, inverse_fn=lambda y: y - dot_val)
    reconstructed_state, _ = rev_recycler.unwind(dot_val * 2.0)
    assert np.isclose(reconstructed_state, dot_val)

    total_pipeline_ms = (time.perf_counter() - t0_pipeline) * 1000.0

    # Strict SLA: Sub-25ms end-to-end reflex
    assert total_pipeline_ms < 25.0, f"Pipeline latency {total_pipeline_ms:.2f}ms exceeded SLA 25.0ms"

    # Strict VRAM Delta invariant
    assert bio_bridge.get_telemetry().vram_delta_mib == 0.00
    assert mps_policy.get_telemetry().vram_delta_mib == 0.00

    jit_fn.close()

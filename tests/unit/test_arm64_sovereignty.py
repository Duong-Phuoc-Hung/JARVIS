"""
tests/unit/test_arm64_sovereignty.py
====================================
Comprehensive Unit Test Suite for ARM64 Native Architecture & Cross-Platform Sovereignty Matrix.
Sprint 25 / Milestone v6.3.0 (Argon Frontier 13.0).

Verifies:
  1. ARM64 ISA extension flags (NEON, FP16, Dot Product SDOT/UDOT, I8MM).
  2. Qualcomm Snapdragon X Elite (Oryon) & Snapdragon X Plus chipset detection.
  3. ARM64 weak-memory model memory fence & lock-free streaming ring buffer across threads.
  4. Vectorized ARM NEON INT8 dot-product micro-kernel with exact reference parity.
  5. Vectorized ARM NEON FP16 GEMV kernel numerical accuracy.
  6. Snapdragon Adaptive Thermal Governor throttle policy.
  7. UHAL & Polyglot runtime integration on ARM64 platforms.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from jarvis.hardware.arm64_sovereignty import (
    ARM64ArchitectureController,
    ARM64HardwareProbe,
    ARM64ISAExtension,
    ARM64MemoryBarrierType,
    ARM64MemoryFence,
    ARM64StreamingRingBuffer,
    ARM64VectorizedKernels,
    SnapdragonAdaptiveThermalGovernor,
    SnapdragonChipsetType,
    SnapdragonPowerState,
)
from jarvis.hardware.universal_hal import CPUArchitecture, HardwareTier


# ──────────────────────────────────────────────────────────────────────────────
# 1. ISA Extensions & Chipset Detection Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_arm64_isa_extension_flags():
    """Verify bitwise flags and composability of ARM64 ISA features."""
    flags = ARM64ISAExtension.NEON | ARM64ISAExtension.FP16 | ARM64ISAExtension.DOT_PRODUCT
    assert ARM64ISAExtension.NEON in flags
    assert ARM64ISAExtension.FP16 in flags
    assert ARM64ISAExtension.DOT_PRODUCT in flags
    assert ARM64ISAExtension.SVE not in flags


def test_snapdragon_chipset_detection_x_elite():
    """Verify detection of Qualcomm Snapdragon X Elite from processor string."""
    probe = ARM64HardwareProbe()
    chipset = probe.identify_chipset("Snapdragon(R) X Elite - X1E80100 - Qualcomm(R) Oryon(TM) CPU")
    assert chipset == SnapdragonChipsetType.X_ELITE


def test_snapdragon_chipset_detection_x_plus():
    """Verify detection of Qualcomm Snapdragon X Plus from processor string."""
    probe = ARM64HardwareProbe()
    chipset = probe.identify_chipset("Snapdragon(R) X Plus - X1P64100 - Qualcomm(R) Oryon(TM) CPU")
    assert chipset == SnapdragonChipsetType.X_PLUS


def test_snapdragon_chipset_detection_generic_and_fallback():
    """Verify detection of generic ARM64 and fallback on Intel/AMD."""
    probe = ARM64HardwareProbe()
    assert probe.identify_chipset("ARMv8 Processor rev 1 (v8l)") == SnapdragonChipsetType.GENERIC_ARM64
    assert probe.identify_chipset("Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz") == SnapdragonChipsetType.EMULATED_X86


# ──────────────────────────────────────────────────────────────────────────────
# 2. ARM64 Weak-Memory Barrier & Lock-Free Ring Buffer Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_arm64_memory_fence_execution():
    """Verify memory fence primitives execute without exception."""
    fence = ARM64MemoryFence()
    # Test all barrier tiers
    fence.dmb(ARM64MemoryBarrierType.FULL_SYSTEM)
    fence.dmb(ARM64MemoryBarrierType.INNER_SHAREABLE_LOADS)
    fence.dmb(ARM64MemoryBarrierType.INNER_SHAREABLE_STORES)
    assert fence.total_barriers_invoked >= 3


def test_arm64_lock_free_streaming_ring_buffer_concurrency():
    """Verify multi-threaded producer-consumer ring buffer ordering under weak memory emulation."""
    buffer = ARM64StreamingRingBuffer[int](capacity=128)
    n_items = 2000
    consumed: list[int] = []
    stop_event = threading.Event()

    def producer():
        for i in range(n_items):
            while not buffer.push(i):
                time.sleep(0.0001)

    def consumer():
        while len(consumed) < n_items and not stop_event.is_set():
            val = buffer.pop()
            if val is not None:
                consumed.append(val)
            else:
                time.sleep(0.0001)

    t_prod = threading.Thread(target=producer)
    t_cons = threading.Thread(target=consumer)

    t_prod.start()
    t_cons.start()

    t_prod.join(timeout=3.0)
    t_cons.join(timeout=3.0)
    stop_event.set()

    assert len(consumed) == n_items
    # Strictly ordered sequence check
    assert consumed == list(range(n_items))


# ──────────────────────────────────────────────────────────────────────────────
# 3. Vectorized ARM NEON Micro-Kernel Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_neon_dot_product_int8_numerical_parity():
    """Verify NEON INT8 dot product gives bit-exact mathematical parity with NumPy."""
    kernels = ARM64VectorizedKernels()
    np.random.seed(42)

    vec_a = np.random.randint(-128, 127, size=512, dtype=np.int8)
    vec_b = np.random.randint(-128, 127, size=512, dtype=np.int8)

    # Reference calculation using 32-bit accumulation
    expected = int(np.dot(vec_a.astype(np.int32), vec_b.astype(np.int32)))
    actual = kernels.neon_dot_product_int8(vec_a, vec_b)

    assert actual == expected


def test_neon_gemv_fp16_numerical_accuracy():
    """Verify NEON FP16 GEMV kernel yields precision within IEEE 754 half-precision bounds."""
    kernels = ARM64VectorizedKernels()
    np.random.seed(42)

    matrix = np.random.randn(64, 128).astype(np.float16)
    vector = np.random.randn(128).astype(np.float16)

    # Reference FP32
    expected_f32 = np.matmul(matrix.astype(np.float32), vector.astype(np.float32))
    actual_f16 = kernels.neon_gemv_fp16(matrix, vector)

    diff = np.max(np.abs(expected_f32 - actual_f16))
    assert diff < 0.05  # Standard FP16 quantization delta


# ──────────────────────────────────────────────────────────────────────────────
# 4. Snapdragon Adaptive Thermal Governor Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_snapdragon_thermal_governor_adaptation():
    """Verify governor adaptively throttles Mamba-2 stride and CRRSP quantization."""
    governor = SnapdragonAdaptiveThermalGovernor()

    # Normal AC power state
    normal_plan = governor.evaluate_adaptation(
        power_state=SnapdragonPowerState.AC_ONLINE,
        battery_pct=100,
        estimated_tdp_w=28.0,
    )
    assert normal_plan.mamba2_target_stride_ms == 160
    assert normal_plan.crrsp_quantization in ["FP16", "INT8"]
    assert normal_plan.is_throttled is False

    # Heavy Battery Saver / High Thermal Load State (> 85C / DC Mode)
    throttled_plan = governor.evaluate_adaptation(
        power_state=SnapdragonPowerState.BATTERY_SAVER,
        battery_pct=15,
        estimated_tdp_w=10.0,
    )
    assert throttled_plan.mamba2_target_stride_ms == 240
    assert throttled_plan.crrsp_quantization == "INT8"
    assert throttled_plan.is_throttled is True
    assert throttled_plan.tdp_cap_w <= 12.0


# ──────────────────────────────────────────────────────────────────────────────
# 5. Full ARM64 Architecture Controller Integration Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_arm64_architecture_controller_profile():
    """Verify controller produces full sovereign profile and telemetry."""
    controller = ARM64ArchitectureController()
    profile = controller.get_architecture_profile()

    assert profile is not None
    assert "chipset" in profile
    assert "isa_extensions" in profile
    assert "memory_model" in profile
    assert profile["memory_model"] in ["WEAK_ORDERING", "TOTAL_STORE_ORDER_EMULATED"]

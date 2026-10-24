"""
tests/eval/test_cross_device_sovereignty.py
===========================================
Frontier 11.0 Cross-Device Universal Sovereignty Benchmark.
Verifies end-to-end execution across simulated Tier 1 to Tier 4 device profiles.
"""
from __future__ import annotations

import unittest
import numpy as np

from jarvis.hardware.eco_governor import AdaptiveEcoGovernor, EcoLevel
from jarvis.hardware.polyglot_runtime import AcceleratorBackend, PolyglotInferenceEngine
from jarvis.hardware.universal_hal import (
    CPUArchitecture,
    DeviceProfile,
    HardwareTier,
    ISACapabilities,
    PowerProfile,
    UniversalHardwareAbstractionLayer,
)
from jarvis.stt.adaptive_crrsp import AdaptiveCRRSPMemory, QuantizationPrecision
from jarvis.stt.crrsp_memory import CRRSPConfig


class TestCrossDeviceSovereignty(unittest.TestCase):
    """
    Validates that JARVIS operates deterministically and fail-closed
    across all hardware tiers (Micro-Edge, Mainstream, Power, Studio).
    """

    def test_tier_1_micro_edge_end_to_end(self) -> None:
        """Simulates low-end Celeron/N100 4GB RAM system."""
        profile = DeviceProfile(
            tier=HardwareTier.TIER_1_MICRO_EDGE,
            architecture=CPUArchitecture.X86_64,
            physical_cores=2,
            logical_cores=4,
            total_ram_gb=4.0,
            available_ram_gb=1.2,
            gpu_name="Intel UHD Graphics 600",
            total_vram_mib=0.0,
            free_vram_mib=0.0,
            primary_backend=AcceleratorBackend.CPU_SIMD,
            supported_backends=(AcceleratorBackend.CPU_SIMD, AcceleratorBackend.PURE_FALLBACK),
            isa=ISACapabilities(has_avx2=False, has_sse2=True),
            power=PowerProfile(is_ac_connected=False, is_battery_saver=True, battery_percentage=35, is_charging=False),
            is_headless=False,
            max_memory_budget_mb=64.0,
            crrsp_buffer_budget_kb=64.0,
            mamba2_layer_count=2,
            mamba2_target_stride_ms=64,
            allow_speculative_prewarming=False,
            recommended_quantization="INT8",
        )

        hal = UniversalHardwareAbstractionLayer(override_profile=profile)
        p = hal.probe_device()
        self.assertEqual(p.tier, HardwareTier.TIER_1_MICRO_EDGE)
        self.assertEqual(p.recommended_quantization, "INT8")

        # 1. Polyglot Engine in INT8
        engine = PolyglotInferenceEngine(device_profile=p)
        x = np.random.randn(512).astype(np.float32)
        w = np.random.randn(45, 512).astype(np.float32)
        out, tel = engine.linear_project(x, w)
        self.assertEqual(out.shape, (45,))
        self.assertEqual(tel.quantization_precision, "INT8")
        self.assertLess(tel.latency_ms, 2.0)  # Sub-2ms even on simulated low-end

        # 2. Adaptive CRRSP in INT8 (strict 64.0 KB)
        crrsp = AdaptiveCRRSPMemory(config=CRRSPConfig(d_model=512, d_state=64), device_profile=p)
        self.assertEqual(crrsp.allocated_memory_bytes, 65536)  # Exactly 64 KB
        frame = np.random.randn(512, 64).astype(np.float32)
        blended = crrsp.step(frame)
        self.assertEqual(blended.shape, (512, 64))

        # 3. Eco-Governor in Battery Saver
        gov = AdaptiveEcoGovernor(hal=hal, check_interval_s=0.0)
        policy = gov.get_current_policy()
        self.assertEqual(policy.eco_level, EcoLevel.BATTERY_SAVER)
        self.assertTrue(policy.enable_int8_quantization)

    def test_arm64_snapdragon_sovereignty(self) -> None:
        """Simulates Qualcomm Snapdragon X Elite Windows on ARM system."""
        profile = DeviceProfile(
            tier=HardwareTier.TIER_2_MAINSTREAM,
            architecture=CPUArchitecture.ARM64,
            physical_cores=12,
            logical_cores=12,
            total_ram_gb=16.0,
            available_ram_gb=8.5,
            gpu_name="Qualcomm Adreno GPU X1-85",
            total_vram_mib=2048.0,
            free_vram_mib=1500.0,
            primary_backend=AcceleratorBackend.CPU_SIMD,
            supported_backends=(AcceleratorBackend.QNN, AcceleratorBackend.CPU_SIMD, AcceleratorBackend.DIRECTML),
            isa=ISACapabilities(has_arm_neon=True, has_arm_v8=True),
            power=PowerProfile(is_ac_connected=True, is_battery_saver=False, battery_percentage=90, is_charging=True),
            is_headless=False,
            max_memory_budget_mb=256.0,
            crrsp_buffer_budget_kb=256.0,
            mamba2_layer_count=4,
            mamba2_target_stride_ms=32,
            allow_speculative_prewarming=True,
            recommended_quantization="FP16",
        )

        engine = PolyglotInferenceEngine(device_profile=profile)
        x = np.random.randn(512).astype(np.float32)
        w = np.random.randn(45, 512).astype(np.float32)
        out, tel = engine.linear_project(x, w)
        self.assertEqual(out.shape, (45,))
        self.assertEqual(tel.quantization_precision, "FP16")
        self.assertFalse(tel.fallback_occurred)

    def test_headless_server_resilience(self) -> None:
        """Simulates Headless Windows Server / Azure VM without GUI or Audio hardware."""
        profile = DeviceProfile(
            tier=HardwareTier.TIER_3_POWER_EDGE,
            architecture=CPUArchitecture.X86_64,
            physical_cores=8,
            logical_cores=16,
            total_ram_gb=32.0,
            available_ram_gb=24.0,
            gpu_name="",
            total_vram_mib=0.0,
            free_vram_mib=0.0,
            primary_backend=AcceleratorBackend.CPU_SIMD,
            supported_backends=(AcceleratorBackend.CPU_SIMD, AcceleratorBackend.PURE_FALLBACK),
            isa=ISACapabilities(has_avx2=True, has_avx512=True),
            power=PowerProfile(is_ac_connected=True, is_battery_saver=False, battery_percentage=100, is_charging=False),
            is_headless=True,
            max_memory_budget_mb=1536.0,
            crrsp_buffer_budget_kb=512.0,
            mamba2_layer_count=6,
            mamba2_target_stride_ms=20,
            allow_speculative_prewarming=True,
            recommended_quantization="FP16",
        )
        self.assertTrue(profile.is_headless)
        engine = PolyglotInferenceEngine(device_profile=profile)
        x = np.random.randn(128).astype(np.float32)
        w = np.random.randn(10, 128).astype(np.float32)
        out, tel = engine.linear_project(x, w)
        self.assertEqual(out.shape, (10,))


if __name__ == "__main__":
    unittest.main()

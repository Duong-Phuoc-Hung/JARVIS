"""
tests/unit/test_universal_hal.py
================================
Unit tests for Universal Hardware Abstraction Layer (UHAL) & Dynamic Device Tiering.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from jarvis.hardware.universal_hal import (
    AcceleratorBackend,
    CPUArchitecture,
    DeviceProfile,
    HardwareTier,
    ISACapabilities,
    PowerProfile,
    UniversalHardwareAbstractionLayer,
    get_universal_hal,
)


class TestUniversalHardwareAbstractionLayer(unittest.TestCase):
    """Verifies UHAL probing, ISA detection, and tier classification."""

    def setUp(self) -> None:
        self.hal = UniversalHardwareAbstractionLayer()

    def test_live_probe_device_returns_valid_profile(self) -> None:
        profile = self.hal.probe_device()
        self.assertIsInstance(profile, DeviceProfile)
        self.assertIn(profile.tier, list(HardwareTier))
        self.assertIn(profile.architecture, list(CPUArchitecture))
        self.assertGreater(profile.total_ram_gb, 0.0)
        self.assertGreater(profile.available_ram_gb, 0.0)
        self.assertGreaterEqual(profile.physical_cores, 1)
        self.assertGreaterEqual(profile.logical_cores, 1)
        self.assertIn(profile.recommended_quantization, ["INT8", "FP16", "FP32"])
        self.assertGreater(profile.max_memory_budget_mb, 0.0)

    def test_tier_classification_micro_edge(self) -> None:
        # Celeron / N100 profile: 4GB RAM, 2 cores, no dGPU
        tier = self.hal._classify_hardware_tier(
            total_ram_gb=4.0,
            avail_ram_gb=1.5,
            physical_cores=2,
            total_vram_mib=0.0,
            is_battery_saver=False,
        )
        self.assertEqual(tier, HardwareTier.TIER_1_MICRO_EDGE)

        budgets = self.hal._calculate_adaptive_budgets(
            tier, PowerProfile(True, False, 100, False)
        )
        self.assertEqual(budgets["quantization"], "INT8")
        self.assertEqual(budgets["crrsp_buffer_kb"], 64.0)
        self.assertEqual(budgets["mamba2_layers"], 2)
        self.assertFalse(budgets["allow_prewarming"])

    def test_tier_classification_mainstream(self) -> None:
        # Standard developer laptop: 16GB RAM, 6 cores, 4GB VRAM
        tier = self.hal._classify_hardware_tier(
            total_ram_gb=15.8,
            avail_ram_gb=3.5,
            physical_cores=6,
            total_vram_mib=4096.0,
            is_battery_saver=False,
        )
        self.assertEqual(tier, HardwareTier.TIER_2_MAINSTREAM)

        budgets = self.hal._calculate_adaptive_budgets(
            tier, PowerProfile(True, False, 100, False)
        )
        self.assertEqual(budgets["quantization"], "FP16")
        self.assertEqual(budgets["crrsp_buffer_kb"], 256.0)
        self.assertEqual(budgets["mamba2_layers"], 4)
        self.assertTrue(budgets["allow_prewarming"])

    def test_tier_classification_power_edge(self) -> None:
        # High-end gaming PC: 32GB RAM, 8 cores, 8GB VRAM
        tier = self.hal._classify_hardware_tier(
            total_ram_gb=31.8,
            avail_ram_gb=18.0,
            physical_cores=8,
            total_vram_mib=8192.0,
            is_battery_saver=False,
        )
        self.assertEqual(tier, HardwareTier.TIER_3_POWER_EDGE)

        budgets = self.hal._calculate_adaptive_budgets(
            tier, PowerProfile(True, False, 100, False)
        )
        self.assertEqual(budgets["quantization"], "FP16")
        self.assertEqual(budgets["crrsp_buffer_kb"], 512.0)
        self.assertEqual(budgets["mamba2_layers"], 6)

    def test_tier_classification_sovereign_studio(self) -> None:
        # Workstation: 64GB RAM, 16 cores, 24GB VRAM (RTX 4090)
        tier = self.hal._classify_hardware_tier(
            total_ram_gb=63.8,
            avail_ram_gb=40.0,
            physical_cores=16,
            total_vram_mib=24576.0,
            is_battery_saver=False,
        )
        self.assertEqual(tier, HardwareTier.TIER_4_SOVEREIGN_STUDIO)

        budgets = self.hal._calculate_adaptive_budgets(
            tier, PowerProfile(True, False, 100, False)
        )
        self.assertEqual(budgets["quantization"], "FP32")
        self.assertEqual(budgets["crrsp_buffer_kb"], 1024.0)
        self.assertEqual(budgets["mamba2_layers"], 8)

    def test_battery_saver_downgrades_constrained_device(self) -> None:
        # Device with 8GB RAM but in battery saver with low RAM left
        tier = self.hal._classify_hardware_tier(
            total_ram_gb=8.0,
            avail_ram_gb=1.8,
            physical_cores=4,
            total_vram_mib=0.0,
            is_battery_saver=True,
        )
        self.assertEqual(tier, HardwareTier.TIER_1_MICRO_EDGE)

    def test_singleton_get_universal_hal(self) -> None:
        instance1 = get_universal_hal()
        instance2 = get_universal_hal()
        self.assertIs(instance1, instance2)


if __name__ == "__main__":
    unittest.main()

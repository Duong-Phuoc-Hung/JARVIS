"""
tests/unit/test_eco_governor.py
===============================
Unit tests for Adaptive Thermal & Battery Eco-Governor (ATBEG).
"""
from __future__ import annotations

import unittest

from jarvis.hardware.eco_governor import (
    AdaptiveEcoGovernor,
    EcoLevel,
    GovernancePolicy,
)
from jarvis.hardware.universal_hal import PowerProfile


class TestAdaptiveEcoGovernor(unittest.TestCase):
    """Verifies dynamic governance levels and thermal throttling."""

    def setUp(self) -> None:
        self.gov = AdaptiveEcoGovernor(check_interval_s=0.0)

    def test_max_performance_on_ac(self) -> None:
        power = PowerProfile(is_ac_connected=True, is_battery_saver=False, battery_percentage=95, is_charging=False)
        policy = self.gov.evaluate_governance(cpu_temp_c=60.0, override_power=power, force=True)
        self.assertEqual(policy.eco_level, EcoLevel.MAX_PERFORMANCE)
        self.assertTrue(policy.allow_speculative_cloud)
        self.assertFalse(policy.enable_int8_quantization)
        self.assertEqual(policy.estimated_power_saving_pct, 0.0)

    def test_balanced_on_moderate_temp(self) -> None:
        power = PowerProfile(is_ac_connected=True, is_battery_saver=False, battery_percentage=80, is_charging=False)
        policy = self.gov.evaluate_governance(cpu_temp_c=78.0, override_power=power, force=True)
        self.assertEqual(policy.eco_level, EcoLevel.BALANCED)
        self.assertEqual(policy.speech_frame_stride_ms, 25)

    def test_battery_saver_on_dc_or_flag(self) -> None:
        # Battery at 25% or battery saver flag on
        power = PowerProfile(is_ac_connected=False, is_battery_saver=True, battery_percentage=30, is_charging=False)
        policy = self.gov.evaluate_governance(cpu_temp_c=65.0, override_power=power, force=True)
        self.assertEqual(policy.eco_level, EcoLevel.BATTERY_SAVER)
        self.assertFalse(policy.allow_speculative_cloud)
        self.assertTrue(policy.enable_int8_quantization)
        self.assertGreaterEqual(policy.estimated_power_saving_pct, 50.0)

    def test_thermal_critical_at_90c(self) -> None:
        power = PowerProfile(is_ac_connected=True, is_battery_saver=False, battery_percentage=100, is_charging=False)
        policy = self.gov.evaluate_governance(cpu_temp_c=92.0, override_power=power, force=True)
        self.assertEqual(policy.eco_level, EcoLevel.THERMAL_CRITICAL)
        self.assertEqual(policy.speech_frame_stride_ms, 64)
        self.assertGreaterEqual(policy.estimated_power_saving_pct, 70.0)


if __name__ == "__main__":
    unittest.main()

"""
tests/unit/test_adaptive_crrsp.py
=================================
Unit tests for Adaptive Multi-Precision CRRSP Memory.
"""
from __future__ import annotations

import unittest
import numpy as np

from jarvis.stt.adaptive_crrsp import (
    AdaptiveCRRSPMemory,
    AdaptiveCRRSPTelemetry,
    QuantizationPrecision,
)
from jarvis.stt.crrsp_memory import CRRSPConfig


class TestAdaptiveCRRSPMemory(unittest.TestCase):
    """Verifies adaptive quantization, multi-turn decay, and memory allocation bounds."""

    def setUp(self) -> None:
        self.config = CRRSPConfig(d_model=64, d_state=16)  # Small config for unit testing
        self.rng = np.random.RandomState(42)

    def test_memory_allocation_bounds(self) -> None:
        # INT8: 2 * 64 * 16 * 1 byte = 2048 bytes = 2.0 KB
        mem_int8 = AdaptiveCRRSPMemory(config=self.config, force_precision=QuantizationPrecision.INT8)
        self.assertEqual(mem_int8.allocated_memory_bytes, 2048)

        # FP16: 2 * 64 * 16 * 2 bytes = 4096 bytes = 4.0 KB
        mem_fp16 = AdaptiveCRRSPMemory(config=self.config, force_precision=QuantizationPrecision.FP16)
        self.assertEqual(mem_fp16.allocated_memory_bytes, 4096)

        # FP32: 2 * 64 * 16 * 4 bytes = 8192 bytes = 8.0 KB
        mem_fp32 = AdaptiveCRRSPMemory(config=self.config, force_precision=QuantizationPrecision.FP32)
        self.assertEqual(mem_fp32.allocated_memory_bytes, 8192)

    def test_int8_quantization_fidelity(self) -> None:
        mem_int8 = AdaptiveCRRSPMemory(config=self.config, force_precision=QuantizationPrecision.INT8)
        mem_fp32 = AdaptiveCRRSPMemory(config=self.config, force_precision=QuantizationPrecision.FP32)

        # Feed identical frames
        for _ in range(5):
            frame = self.rng.randn(self.config.d_model, self.config.d_state).astype(np.float32)
            out_int8 = mem_int8.step(frame, current_f0_hz=155.0)
            out_fp32 = mem_fp32.step(frame, current_f0_hz=155.0)

        # Telemetry check
        tel = mem_int8.get_telemetry()
        self.assertIsInstance(tel, AdaptiveCRRSPTelemetry)
        self.assertEqual(tel.precision, "INT8")
        self.assertGreaterEqual(tel.cosine_fidelity, 0.990)

    def test_turn_finalization_decay(self) -> None:
        mem = AdaptiveCRRSPMemory(config=self.config, force_precision=QuantizationPrecision.INT8)
        for _ in range(3):
            frame = self.rng.randn(self.config.d_model, self.config.d_state).astype(np.float32)
            mem.step(frame)

        tel_before = mem.get_telemetry()
        fast_before = tel_before.fast_norm

        mem.finalize_turn(is_glottal_stop=False)
        tel_after = mem.get_telemetry()

        # Fast substate should decay significantly
        self.assertLess(tel_after.fast_norm, fast_before)
        # Turns accumulated should increment
        self.assertEqual(tel_after.turns_accumulated, 1)

    def test_reset_clears_substates(self) -> None:
        mem = AdaptiveCRRSPMemory(config=self.config, force_precision=QuantizationPrecision.INT8)
        frame = self.rng.randn(self.config.d_model, self.config.d_state).astype(np.float32)
        mem.step(frame)

        mem.reset()
        tel = mem.get_telemetry()
        self.assertEqual(tel.fast_norm, 0.0)
        self.assertEqual(tel.slow_norm, 0.0)
        self.assertEqual(tel.turns_accumulated, 0)


if __name__ == "__main__":
    unittest.main()

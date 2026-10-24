"""
tests/unit/test_polyglot_runtime.py
===================================
Unit tests for Polyglot Inference Runtime across heterogeneous backends and quantizations.
"""
from __future__ import annotations

import unittest
import numpy as np

from jarvis.hardware.polyglot_runtime import (
    AcceleratorBackend,
    ExecutionTelemetry,
    PolyglotInferenceEngine,
)
from jarvis.hardware.universal_hal import (
    CPUArchitecture,
    DeviceProfile,
    HardwareTier,
    ISACapabilities,
    PowerProfile,
)


class TestPolyglotInferenceEngine(unittest.TestCase):
    """Verifies polyglot linear projection, precision modes, and fallback resilience."""

    def setUp(self) -> None:
        self.rng = np.random.RandomState(42)
        self.in_dim = 128
        self.out_dim = 16
        self.x = self.rng.randn(self.in_dim).astype(np.float32)
        self.w = self.rng.randn(self.out_dim, self.in_dim).astype(np.float32)
        self.b = self.rng.randn(self.out_dim).astype(np.float32)

    def test_cpu_simd_fp32_execution(self) -> None:
        engine = PolyglotInferenceEngine(force_backend=AcceleratorBackend.CPU_SIMD)
        engine.quantization = "FP32"

        out, tel = engine.linear_project(self.x, self.w, self.b)
        self.assertEqual(out.shape, (self.out_dim,))
        self.assertIsInstance(tel, ExecutionTelemetry)
        self.assertEqual(tel.backend_used, AcceleratorBackend.CPU_SIMD)
        self.assertEqual(tel.quantization_precision, "FP32")
        self.assertFalse(tel.fallback_occurred)

        # Numerical check against standard numpy
        expected = np.matmul(self.x, self.w.T) + self.b
        np.testing.assert_allclose(out, expected, rtol=1e-5, atol=1e-5)

    def test_cpu_simd_fp16_execution(self) -> None:
        engine = PolyglotInferenceEngine(force_backend=AcceleratorBackend.CPU_SIMD)
        engine.quantization = "FP16"

        out, tel = engine.linear_project(self.x, self.w, self.b)
        self.assertEqual(out.shape, (self.out_dim,))
        self.assertEqual(tel.quantization_precision, "FP16")

        expected = np.matmul(self.x.astype(np.float16), self.w.astype(np.float16).T) + self.b.astype(np.float16)
        np.testing.assert_allclose(out, expected.astype(np.float32), rtol=1e-2, atol=1e-2)

    def test_cpu_simd_int8_quantization_fidelity(self) -> None:
        engine = PolyglotInferenceEngine(force_backend=AcceleratorBackend.CPU_SIMD)
        engine.quantization = "INT8"

        out_int8, tel = engine.linear_project(self.x, self.w, self.b)
        self.assertEqual(out_int8.shape, (self.out_dim,))
        self.assertEqual(tel.quantization_precision, "INT8")

        # Compare cosine similarity of INT8 result vs FP32 ground truth
        out_fp32 = np.matmul(self.x, self.w.T) + self.b
        cos_sim = float(np.dot(out_int8, out_fp32) / (np.linalg.norm(out_int8) * np.linalg.norm(out_fp32)))
        self.assertGreater(cos_sim, 0.995, f"INT8 cosine similarity {cos_sim} too low!")

    def test_pure_fallback_numerical_equivalence(self) -> None:
        engine = PolyglotInferenceEngine(force_backend=AcceleratorBackend.PURE_FALLBACK)
        out, tel = engine.linear_project(self.x, self.w, self.b)
        self.assertEqual(tel.backend_used, AcceleratorBackend.PURE_FALLBACK)

        expected = np.matmul(self.x, self.w.T) + self.b
        np.testing.assert_allclose(out, expected, rtol=1e-5, atol=1e-5)

    def test_auto_degradation_on_backend_exception(self) -> None:
        # Force a broken backend method to verify graceful fallback
        engine = PolyglotInferenceEngine(force_backend=AcceleratorBackend.CUDA)
        engine.quantization = "FP32"
        # Monkey patch _exec_cuda_or_simd to raise an exception
        def _broken(*args, **kwargs):
            raise RuntimeError("Simulated CUDA device loss or out of memory")
        engine._exec_cuda_or_simd = _broken

        out, tel = engine.linear_project(self.x, self.w, self.b)
        self.assertTrue(tel.fallback_occurred)
        self.assertEqual(tel.backend_used, AcceleratorBackend.CPU_SIMD)
        self.assertEqual(engine.total_fallbacks, 1)

        expected = np.matmul(self.x, self.w.T) + self.b
        np.testing.assert_allclose(out, expected, rtol=1e-4, atol=1e-4)


if __name__ == "__main__":
    unittest.main()

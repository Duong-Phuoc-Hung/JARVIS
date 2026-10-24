"""
tests/unit/test_fused_ssd.py
============================
Unit tests for Hardware-Fused Mamba-2 Structured State Space Duality (FBT-SSD) Block and Encoder.
"""
from __future__ import annotations

import unittest
import numpy as np

from jarvis.stt.fused_ssd import FusedMamba2SSDBlock, FusedStreamingSpeechSSDEncoder
from jarvis.stt.ssd_encoder import Mamba2SSDBlock, SSDConfig, StreamingSpeechSSDEncoder


class TestFusedSSD(unittest.TestCase):
    """Verifies speedup, numerical consistency, and GTSR glottal reset of Fused SSD."""

    def setUp(self) -> None:
        self.config = SSDConfig(d_model=128, d_state=32, d_inner=256)
        self.rng = np.random.RandomState(42)

    def test_fused_block_step_output_validity(self) -> None:
        block = FusedMamba2SSDBlock(config=self.config, seed=42)
        x = self.rng.randn(self.config.d_model).astype(np.float32)

        out = block.step(x)
        self.assertEqual(out.output.shape, (self.config.d_model,))
        self.assertGreater(out.state_norm, 0.0)
        self.assertFalse(out.is_glottal_reset)
        self.assertEqual(out.total_frames_processed, 1)

    def test_glottal_reset_attenuates_state(self) -> None:
        block = FusedMamba2SSDBlock(config=self.config, seed=42)
        x = self.rng.randn(self.config.d_model).astype(np.float32)
        for _ in range(3):
            block.step(x)

        norm_before = float(np.linalg.norm(block.ssm_state))
        # Glottal stop / pause occurs on a low-energy / silent audio frame
        silence_frame = np.zeros(self.config.d_model, dtype=np.float32)
        out_reset = block.step(silence_frame, is_glottal_stop=True)
        self.assertTrue(out_reset.is_glottal_reset)
        norm_after = float(np.linalg.norm(block.ssm_state))

        self.assertLess(norm_after, norm_before)

    def test_multi_layer_fused_encoder(self) -> None:
        encoder = FusedStreamingSpeechSSDEncoder(num_layers=2, config=self.config)
        x = self.rng.randn(self.config.d_model).astype(np.float32)

        out_vec, telemetries = encoder.process_frame(x, current_f0_hz=140.0)
        self.assertEqual(out_vec.shape, (self.config.d_model,))
        self.assertEqual(len(telemetries), 2)
        self.assertEqual(encoder.total_frames_processed, 1)
        self.assertGreater(encoder.total_state_memory_bytes, 0)

        # Multi-turn finalize
        encoder.finalize_turn()
        self.assertEqual(encoder.crrsp_memory.turns_accumulated, 1)


if __name__ == "__main__":
    unittest.main()

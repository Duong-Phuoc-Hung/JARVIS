"""
tests/unit/test_mose_head.py
============================
Unit tests for Mixture of Sparse Acoustic Experts (MoSE-ADAP) Projection Head.
"""
from __future__ import annotations

import unittest
from pathlib import Path
import numpy as np

from jarvis.audio.mose_head import (
    ACTIONS_PER_EXPERT,
    CANONICAL_180_ACTIONS,
    NUM_EXPERTS,
    TOTAL_MOSE_ACTIONS,
    MoSEPrediction,
    MoSEProjectionHead,
)


class TestMoSEProjectionHead(unittest.TestCase):
    """Verifies MoSE sparse gating, 180 action catalog, SGD adaptation, and atomic persistence."""

    def setUp(self) -> None:
        self.d_model = 128
        self.head = MoSEProjectionHead(
            d_model=self.d_model,
            num_experts=NUM_EXPERTS,
            actions_per_expert=ACTIONS_PER_EXPERT,
            temperature=0.5,
            confidence_threshold=0.80,
            gating_threshold=0.70,
            margin_threshold=0.15,
            seed=42,
        )
        self.rng = np.random.RandomState(42)

    def test_canonical_action_catalog_integrity(self) -> None:
        self.assertEqual(len(CANONICAL_180_ACTIONS), 180)
        self.assertEqual(self.head.total_actions, 180)
        # Verify unique IDs and non-empty intents
        ids = [a.action_id for a in CANONICAL_180_ACTIONS]
        self.assertEqual(len(set(ids)), 180)
        self.assertEqual(min(ids), 0)
        self.assertEqual(max(ids), 179)

    def test_predict_returns_valid_prediction_structure(self) -> None:
        h = self.rng.randn(self.d_model).astype(np.float32)
        pred = self.head.predict(h)
        self.assertIsInstance(pred, MoSEPrediction)
        self.assertIn(pred.expert_id, [0, 1, 2, 3])
        self.assertTrue(0 <= pred.action_id < 180)
        self.assertGreaterEqual(pred.total_confidence, 0.0)
        self.assertLessEqual(pred.total_confidence, 1.0)
        self.assertGreater(pred.latency_ms, 0.0)
        self.assertLess(pred.latency_ms, 1.5)  # Sub-1.5ms on CPU

    def test_sgd_adaptation_converges_on_target_action(self) -> None:
        h = self.rng.randn(self.d_model).astype(np.float32)
        target_action = 112  # Developer action in expert 2

        # Initial prediction
        pred_before = self.head.predict(h)

        # Apply 25 gradient steps
        for _ in range(25):
            self.head.adapt_sgd(h, target_action_id=target_action, learning_rate=0.15)

        pred_after = self.head.predict(h)
        self.assertEqual(pred_after.action_id, target_action)
        self.assertEqual(pred_after.expert_id, 2)
        self.assertTrue(pred_after.is_confirmed)
        self.assertGreater(pred_after.expert_confidence, 0.85)

    def test_atomic_persistence_save_and_load(self, tmp_path=None) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test_mose.npz"
            # Train on an action
            h = self.rng.randn(self.d_model).astype(np.float32)
            self.head.adapt_sgd(h, target_action_id=45, learning_rate=0.10)
            self.head.save_weights(path)
            self.assertTrue(path.exists())

            # Load into fresh head
            new_head = MoSEProjectionHead(d_model=self.d_model, seed=999)
            success = new_head.load_weights(path)
            self.assertTrue(success)

            pred_orig = self.head.predict(h)
            pred_loaded = new_head.predict(h)
            self.assertEqual(pred_orig.action_id, pred_loaded.action_id)
            self.assertEqual(pred_orig.expert_id, pred_loaded.expert_id)
            self.assertAlmostEqual(pred_orig.total_confidence, pred_loaded.total_confidence, places=4)


if __name__ == "__main__":
    unittest.main()

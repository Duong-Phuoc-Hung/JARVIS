"""
tests/unit/test_adap_head.py
============================
Unit test suite for Acoustic Direct-to-Action Projection (ADAP) Linear Head.
Validates sub-15ms inference SLA, 92KB memory budget, fail-closed gating,
and Windows Atomic Persistence in Argon Frontier 10.0.
"""
import os
import tempfile
import time
from pathlib import Path

import numpy as np
import pytest

from jarvis.audio.adap_head import (
    DEFAULT_REFLEX_ACTIONS,
    ADAPConfig,
    ADAPPrediction,
    ADAPProjectionHead,
    ReflexActionDefinition,
)


class TestADAPProjectionHead:
    """Comprehensive test harness for ADAPProjectionHead."""

    def test_adap_head_initialization_and_memory_invariant(self) -> None:
        """Verifies dimension shapes and strictly bounded memory footprint (<= 92.5 KB)."""
        head = ADAPProjectionHead()
        assert head.num_actions == 45
        assert len(head.actions) == 45
        assert head.w_adap.shape == (45, 512)
        assert head.b_adap.shape == (45,)
        assert head.w_adap.dtype == np.float32

        # Memory footprint calculation: (45*512 + 45) * 4 bytes = 92,340 bytes (~90.18 KB)
        memory_bytes = head.parameter_bytes
        memory_kb = memory_bytes / 1024.0
        assert memory_kb <= 92.5, f"ADAP parameter size {memory_kb:.2f} KB exceeds 92.5 KB limit"

    def test_adap_head_sub_15ms_reflex_prediction(self) -> None:
        """Verifies sub-15ms deterministic speech-to-action routing for reflex intents."""
        head = ADAPProjectionHead()

        # Extract target prototype for action 0: system_volume_mute
        target_prototype = head.w_adap[0].copy()
        target_prototype /= np.linalg.norm(target_prototype)

        # Scale embedding into high-confidence range
        acoustic_latent = target_prototype * 5.0

        pred = head.predict(acoustic_latent)

        assert isinstance(pred, ADAPPrediction)
        assert pred.is_reflex is True
        assert pred.action is not None
        assert pred.action.action_id == 0
        assert pred.action.intent == "system_volume_mute"
        assert pred.action.domain == "system"
        assert pred.confidence >= 0.82
        assert pred.margin >= 0.15
        assert pred.latency_ms < 15.0, f"ADAP latency {pred.latency_ms:.3f}ms exceeded 15.0ms SLA"

    def test_adap_head_temporal_sequence_pooling(self) -> None:
        """Verifies 2D temporal sequence pooling over multi-frame acoustic inputs."""
        head = ADAPProjectionHead(config=ADAPConfig(pooling_mode="terminal"))

        # Create temporal sequence (T=16 frames, d_model=512)
        target_prototype = head.w_adap[2].copy()  # system_volume_up
        target_prototype /= np.linalg.norm(target_prototype)

        frames = np.zeros((16, 512), dtype=np.float32)
        # Terminal frame contains high-energy target signal
        frames[-1] = target_prototype * 6.0

        pred = head.predict(frames)
        assert pred.is_reflex is True
        assert pred.action is not None
        assert pred.action.action_id == 2
        assert pred.action.intent == "system_volume_up"

    def test_adap_head_fail_closed_on_low_confidence(self) -> None:
        """Verifies fail-closed deferral when acoustic signal is ambiguous or OOD."""
        head = ADAPProjectionHead()

        # Noisy uniform/random acoustic latent vector
        rng = np.random.default_rng(999)
        noise_latent = rng.normal(0.0, 0.01, 512).astype(np.float32)

        pred = head.predict(noise_latent)

        assert pred.is_reflex is False
        assert pred.action is None
        assert pred.fallback_reason is not None
        assert "BELOW_THRESHOLD" in pred.fallback_reason

    def test_adap_head_online_calibration(self) -> None:
        """Verifies in-situ gradient calibration reinforces target action probability."""
        head = ADAPProjectionHead()
        target_action_id = 10  # window_minimize

        rng = np.random.default_rng(123)
        user_embedding = rng.normal(0.0, 1.0, 512).astype(np.float32)

        # Measure initial loss
        loss_before = head.calibrate_action(user_embedding, target_action_id=target_action_id, learning_rate=0.1)

        # Calibrate multiple steps
        for _ in range(5):
            loss_after = head.calibrate_action(user_embedding, target_action_id=target_action_id, learning_rate=0.2)

        assert loss_after < loss_before

    def test_adap_head_windows_atomic_persistence(self) -> None:
        """Verifies atomic save and load of weights adhering to Rule 3 of AGENTS.md."""
        head = ADAPProjectionHead(seed=777)

        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = Path(tmp_dir) / "adap_weights.npz"

            # Modify weights slightly
            head.b_adap[0] = 1.234

            # Save
            head.save_weights(save_path)
            assert save_path.exists()

            # Load into fresh instance
            fresh_head = ADAPProjectionHead(seed=1)
            assert fresh_head.b_adap[0] != 1.234
            fresh_head.load_weights(save_path)
            assert np.isclose(fresh_head.b_adap[0], 1.234)
            np.testing.assert_allclose(fresh_head.w_adap, head.w_adap)

"""
tests/unit/test_grpo_engine.py
==============================
Unit tests for In-Situ Test-Time GRPO Policy Engine.
"""
from __future__ import annotations

import numpy as np
import pytest

from jarvis.core.models import ActionResult, ActionStatus
from jarvis.learning.grpo_engine import GRPOConfig, InSituGRPOEngine, LoRAPolicyHead
from jarvis.learning.win32_oracle import Win32ExecutionRewardOracle


def test_lora_policy_head_shapes_and_forward():
    """Verifies LoRA rank-4 policy head initialization and forward passes."""
    head = LoRAPolicyHead(d_in=32, d_out=16, rank=4, alpha=8.0)

    assert head.lora_a.shape == (32, 4)
    assert head.lora_b.shape == (4, 16)
    assert head.total_trainable_bytes < 5000  # Less than 5 KB

    x = np.ones(32, dtype=np.float32)
    logits_curr = head.forward(x)
    logits_ref = head.forward_ref(x)

    assert logits_curr.shape == (16,)
    assert logits_ref.shape == (16,)
    # At initialization, lora_b is zero, so logits_curr == logits_ref
    np.testing.assert_allclose(logits_curr, logits_ref, atol=1e-5)


def test_lora_policy_head_snapshot_and_rollback():
    """Verifies snapshot and rollback mechanism for atomic safety."""
    head = LoRAPolicyHead(d_in=32, d_out=16, rank=4, alpha=8.0)
    head.snapshot()

    # Modify weights
    head.lora_b += 0.5
    assert np.any(head.lora_b != 0.0)

    # Rollback
    head.rollback()
    np.testing.assert_allclose(head.lora_b, 0.0, atol=1e-7)


def test_grpo_engine_step_optimization():
    """Verifies full GRPO group advantage calculation and policy step."""
    engine = InSituGRPOEngine(config=GRPOConfig(d_input=32, d_output=16, group_size=4))

    context_x = np.ones(32, dtype=np.float32)
    candidates = [
        ("system_volume", {"level": 80}),
        ("spotify_play", {"query": "Sơn Tùng"}),
        ("screen_brightness", {"level": 50}),
        ("format_disk", {"drive": "C"}),  # Destructive candidate, will be penalized
    ]

    def mock_eval(intent: str, params: dict) -> ActionResult:
        if intent == "format_disk":
            return ActionResult(action_name=intent, status=ActionStatus.BLOCKED)
        return ActionResult(action_name=intent, status=ActionStatus.SUCCESS)

    result = engine.optimize_step(context_x, candidates, mock_eval)

    assert result.group_size == 4
    assert len(result.candidates) == 4
    # The destructive candidate should have lowest advantage
    format_cand = [c for c in result.candidates if c.intent == "format_disk"][0]
    best_cand = [c for c in result.candidates if c.intent == result.selected_intent][0]

    assert format_cand.advantage < best_cand.advantage
    assert result.step_latency_ms > 0.0
    assert result.kl_divergence >= 0.0


def test_grpo_engine_kl_safety_rollback():
    """Verifies that exceeding the KL divergence ceiling triggers automatic rollback."""
    # Set ceiling very low (1e-4) so rollback is guaranteed to trigger on non-zero divergence
    engine = InSituGRPOEngine(
        config=GRPOConfig(d_input=32, d_output=16, group_size=4, max_kl_ceiling=1e-4)
    )

    # Force a substantial non-uniform KL divergence by modifying lora_b
    engine.policy_head.lora_b[0, 0] += 5.0

    context_x = np.ones(32, dtype=np.float32)
    candidates = [
        ("system_volume", {"level": 80}),
        ("spotify_play", {"query": "test"}),
    ]

    def mock_eval(intent: str, params: dict) -> ActionResult:
        return ActionResult(action_name=intent, status=ActionStatus.SUCCESS)

    result = engine.optimize_step(context_x, candidates, mock_eval)

    # Rollback must be triggered
    assert result.is_rolled_back
    assert not result.is_updated

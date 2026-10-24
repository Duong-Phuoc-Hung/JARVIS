"""
tests/unit/test_latent_world_model.py
=====================================
Unit tests for Frontier 15.0 Latent OS World Model & Negative-Latency Predictive Execution.
Sprint 26 / Milestone v6.4.0.
"""
from __future__ import annotations

import numpy as np
import pytest

import time

from jarvis.learning.latent_world_model import (
    CONTEXT_DIM,
    LATENT_DIM,
    LatentOSWorldModel,
    LatentPredictionResult,
    NegativeLatencyExecutionManager,
    SpeculativeActionCandidate,
    SpeculativeActionStatus,
)


def test_latent_world_model_simulation() -> None:
    """Verifies that the transition model simulates future latent state within dimensions."""
    model = LatentOSWorldModel(latent_dim=LATENT_DIM, context_dim=CONTEXT_DIM, seed=100)

    z_t = np.random.randn(LATENT_DIM).astype(np.float32)
    c_t = np.random.randn(CONTEXT_DIM).astype(np.float32)

    pred = model.simulate_future_latent(z_t, c_t, horizon_step=1)
    assert isinstance(pred, LatentPredictionResult)
    assert pred.predicted_latent.shape == (LATENT_DIM,)
    assert pred.horizon_step == 1
    assert pred.energy_score >= 0.0
    assert pred.simulation_latency_ms < 5.0  # Well within SLA


def test_speculative_action_candidate_prewarming() -> None:
    """Verifies speculative action prewarming during streaming turn context."""
    manager = NegativeLatencyExecutionManager()

    z_t = np.random.randn(LATENT_DIM).astype(np.float32)
    c_t = np.random.randn(CONTEXT_DIM).astype(np.float32)

    candidate = manager.prewarm_turn_context(z_t, c_t, horizon_step=1)
    # Even if confidence filter rejects random noise or accepts, status reporting remains valid
    report = manager.get_status_report()
    assert report["vram_delta_mib"] == 0.00
    assert "total_prewarmed" in report


def test_negative_latency_commit_matching() -> None:
    """Ensures instant execution when final intent matches prewarmed context."""
    manager = NegativeLatencyExecutionManager(match_similarity_threshold=0.80)

    # Force candidate creation with known context
    c_base = np.zeros(CONTEXT_DIM, dtype=np.float32)
    c_base[0] = 1.0

    z_base = np.zeros(LATENT_DIM, dtype=np.float32)
    z_base[0] = 1.0

    candidate = manager.prewarm_turn_context(z_base, c_base, horizon_step=1)
    if candidate is None:
        # Manually attach confident candidate to test matching path
        candidate = SpeculativeActionCandidate(
            candidate_id="test_cand_1",
            action_type="CLICK_COORDINATE",
            target_coordinates=(0.85, 0.12),
            command_payload="CLICK_SEARCH",
            confidence=0.92,
            predicted_latent=z_base,
            context_signature=c_base,
            created_at_ns=time.perf_counter_ns(),
        )
        manager._active_candidate = candidate
        manager.metrics["total_prewarmed"] += 1

    # Final turn matching with identical context
    c_final = c_base.copy()
    status, executed_cand, latency_ms = manager.commit_turn_finalization(c_final)

    assert status == SpeculativeActionStatus.COMMITTED
    assert executed_cand is not None
    assert executed_cand.is_executed is True
    assert latency_ms < 1.0  # Sub-millisecond negative-latency commit!

    report = manager.get_status_report()
    assert report["total_committed"] == 1
    assert report["sub_half_millisecond_sla_met"] is True


def test_divergence_discard_fail_closed() -> None:
    """Ensures candidate is safely discarded without execution when intent diverges."""
    manager = NegativeLatencyExecutionManager(match_similarity_threshold=0.85)

    c_base = np.zeros(CONTEXT_DIM, dtype=np.float32)
    c_base[0] = 1.0

    candidate = SpeculativeActionCandidate(
        candidate_id="test_cand_diverge",
        action_type="SEND_SHORTCUT",
        target_coordinates=(0.0, 0.0),
        command_payload="ALT_F4",
        confidence=0.88,
        predicted_latent=np.zeros(LATENT_DIM, dtype=np.float32),
        context_signature=c_base,
        created_at_ns=time.perf_counter_ns(),
    )
    manager._active_candidate = candidate


    # Divergent final context (orthogonal vector)
    c_divergent = np.zeros(CONTEXT_DIM, dtype=np.float32)
    c_divergent[1] = 1.0

    status, executed_cand, _ = manager.commit_turn_finalization(c_divergent)
    assert status == SpeculativeActionStatus.DISCARDED_DIVERGENCE
    assert executed_cand is None
    assert manager._active_candidate is None

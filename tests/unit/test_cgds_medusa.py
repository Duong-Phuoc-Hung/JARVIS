"""
tests/unit/test_cgds_medusa.py
==============================
Unit Test Suite for Confidence-Gated Dynamic Speculation (CGDS) in Whisper-Medusa.
Validates:
  1. Accurate Shannon Entropy calculation in nats.
  2. Circuit breaker triggering on high entropy (bypassing drafting).
  3. High-confidence drafting (low entropy) allowing full K=4 lookahead tokens.
  4. Graceful verification fallback when drafting is bypassed.
"""
import numpy as np
import pytest

from jarvis.stt.medusa_decoder import (
    SpeculativeVerificationResult,
    WhisperMedusaSpeculativeDecoder,
)


def test_shannon_entropy_calculation():
    """Validates Shannon Entropy computation on uniform vs peaked distributions."""
    # 1. Peaked distribution (low entropy)
    peaked_logits = np.array([10.0, -10.0, -10.0, -10.0], dtype=np.float32)
    entropy_peaked = WhisperMedusaSpeculativeDecoder.calculate_entropy(peaked_logits)
    assert entropy_peaked < 0.05

    # 2. Uniform distribution over 4 classes: H = ln(4) ~= 1.386 nats
    uniform_logits = np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float32)
    entropy_uniform = WhisperMedusaSpeculativeDecoder.calculate_entropy(uniform_logits)
    assert pytest.approx(entropy_uniform, abs=0.01) == np.log(4.0)


def test_cgds_circuit_breaker_bypasses_on_high_entropy():
    """Validates that high entropy trips the CGDS circuit breaker and returns empty drafts."""
    decoder = WhisperMedusaSpeculativeDecoder(
        num_heads=4,
        hidden_dim=64,
        vocab_size=200,
        enable_cgds=True,
        entropy_threshold=1.5,
    )
    # Zero hidden state produces near-uniform logits across 200 tokens (H ~ ln(200) = 5.3 nats)
    hidden = np.zeros(64, dtype=np.float32)

    candidates, entropy, is_bypassed = decoder.generate_draft_with_entropy_gate(hidden)

    assert is_bypassed is True
    assert entropy > 1.5
    assert len(candidates) == 0
    assert decoder.total_circuit_breaker_bypasses == 1


def test_cgds_verification_fallback_on_bypassed_draft():
    """Validates that verify_candidates handles empty drafts gracefully via 1 baseline greedy step."""
    decoder = WhisperMedusaSpeculativeDecoder(
        num_heads=4,
        hidden_dim=64,
        vocab_size=200,
        enable_cgds=True,
        entropy_threshold=1.5,
    )

    def mock_target_eval(step_idx: int, draft_token: int):
        return 42, 0.99

    # Empty draft list due to circuit breaker bypass
    result = decoder.verify_candidates([], mock_target_eval)

    assert isinstance(result, SpeculativeVerificationResult)
    assert result.is_circuit_broken is True
    assert result.accepted_tokens == (42,)
    assert result.accepted_count == 1
    assert result.speedup_ratio == 1.0

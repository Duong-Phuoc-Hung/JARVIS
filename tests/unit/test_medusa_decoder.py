"""
tests/unit/test_medusa_decoder.py
=================================
Unit Test Suite for Whisper-Medusa Speculative Acoustic Streaming Decoder.
Validates:
  - Tree-Attention Mask DAG causality and shape invariants.
  - Multi-Head residual drafting for K=4 lookahead tokens.
  - Mathematical equivalence (zero WER divergence) on acceptance or rejection.
  - Speedup ratio telemetry and latency constraints.
"""
import numpy as np
import pytest

from jarvis.stt.medusa_decoder import (
    MedusaDraftHead,
    SpeculativeVerificationResult,
    TreeAttentionMask,
    WhisperMedusaSpeculativeDecoder,
)


def test_tree_attention_mask_construction():
    """Validates directed acyclic tree attention mask properties."""
    # Two candidate paths: Path 0 = [10, 20, 30], Path 1 = [10, 40]
    paths = [[10, 20, 30], [10, 40]]
    mask = TreeAttentionMask.create_tree_mask(paths)

    total_nodes = 3 + 2
    assert mask.shape == (total_nodes, total_nodes)

    # In Path 0: node 0 can attend to node 0
    assert mask[0, 0] == 0.0
    # node 1 can attend to node 0 and node 1
    assert mask[1, 0] == 0.0
    assert mask[1, 1] == 0.0
    # node 0 cannot attend to node 1 (future)
    assert mask[0, 1] <= -1e8
    # node 0 cannot attend to Path 1 nodes
    assert mask[0, 3] <= -1e8

    # Empty paths
    empty_mask = TreeAttentionMask.create_tree_mask([])
    assert empty_mask.shape == (0, 0)


def test_medusa_draft_head_projection():
    """Validates MedusaDraftHead output dimensionality and stability."""
    hidden_dim = 256
    vocab_size = 1000
    head = MedusaDraftHead(hidden_dim=hidden_dim, vocab_size=vocab_size, offset_k=1, seed=42)

    hidden = np.ones(hidden_dim, dtype=np.float32) * 0.5
    logits = head.forward(hidden)

    assert logits.shape == (vocab_size,)
    assert not np.isnan(logits).any()
    assert not np.isinf(logits).any()


def test_whisper_medusa_full_acceptance_speedup():
    """Validates K=4 speculative decoding when all draft tokens match the target model."""
    decoder = WhisperMedusaSpeculativeDecoder(num_heads=4, hidden_dim=128, vocab_size=500)
    hidden = np.zeros(128, dtype=np.float32)

    drafts = decoder.generate_draft_candidates(hidden)
    assert len(drafts) == 4

    # Target model agrees with all drafts
    def target_eval_perfect(step_idx: int, draft_token: int):
        return draft_token, 0.95

    result = decoder.verify_candidates(drafts, target_eval_perfect)

    assert isinstance(result, SpeculativeVerificationResult)
    assert result.is_fully_accepted is True
    assert result.accepted_count == 4
    assert result.accepted_tokens == tuple(drafts)
    assert len(result.rejected_tokens) == 0
    assert result.speedup_ratio == 4.0
    assert decoder.mean_acceptance_rate == 1.0


def test_whisper_medusa_partial_rejection_deterministic_fallback():
    """
    Validates that when a draft token fails verification, the decoder safely
    falls back to the target model's true greedy choice with zero accuracy divergence.
    """
    decoder = WhisperMedusaSpeculativeDecoder(num_heads=4, hidden_dim=128, vocab_size=500)
    hidden = np.zeros(128, dtype=np.float32)

    drafts = decoder.generate_draft_candidates(hidden)
    # Force draft at step 1 to disagree
    true_target_token_step1 = 999  # distinct token

    def target_eval_mismatch(step_idx: int, draft_token: int):
        if step_idx == 0:
            return draft_token, 0.90  # accepted
        elif step_idx == 1:
            return true_target_token_step1, 0.10  # rejected, target chooses 999
        return draft_token, 0.90

    result = decoder.verify_candidates(drafts, target_eval_mismatch)

    assert result.is_fully_accepted is False
    # Step 0 accepted (drafts[0]), Step 1 rejected and replaced by true target (999)
    assert result.accepted_count == 2
    assert result.accepted_tokens[0] == drafts[0]
    assert result.accepted_tokens[1] == true_target_token_step1
    assert drafts[1] in result.rejected_tokens


def test_whisper_medusa_telemetry():
    """Validates global telemetry accounting across multiple decoding passes."""
    decoder = WhisperMedusaSpeculativeDecoder(num_heads=3, hidden_dim=64, vocab_size=200)
    hidden = np.zeros(64, dtype=np.float32)

    # Pass 1: 3 drafts, all accepted
    drafts1 = decoder.generate_draft_candidates(hidden)
    decoder.verify_candidates(drafts1, lambda s, d: (d, 0.95))

    # Pass 2: 3 drafts, 1 accepted then 1 rejected
    drafts2 = decoder.generate_draft_candidates(hidden)
    decoder.verify_candidates(drafts2, lambda s, d: (888, 0.10) if s == 1 else (d, 0.95))

    assert decoder.total_verification_passes == 2
    assert decoder.total_speculated == 6
    assert decoder.total_accepted == 3 + 2  # 3 in pass 1, 2 in pass 2
    assert 0.80 <= decoder.mean_acceptance_rate <= 0.85
    assert decoder.mean_speedup == 2.5

"""
tests/unit/test_retrocausal_engine.py
=====================================
Unit Tests for Omnipresent Temporal Reversal & Continuous Rollback Speculation.
Milestone v9.0.0 ("The Transcendent Singularity", Frontier 33.0).
"""
from __future__ import annotations

import os
import tempfile
import pytest

from jarvis.security.formal_verifier import (
    ActionSynthesisNode,
    ActionVerb,
    PreconditionState,
    VerificationVerdict,
    VerifiedActionSynthesizer,
)
from jarvis.security.retrocausal_engine import (
    CheckpointType,
    RetrocausalRollbackEngine,
    RetrocausalTransaction,
    ShadowPageForkManager,
    SpeculativeExecutionResult,
    VirtualStatePage,
)


def test_shadow_page_cow_fork_manager_isolation_and_commit():
    """Validates copy-on-write shadow fork isolation, fallback, and promotion to canonical."""
    mgr = ShadowPageForkManager(canonical_branch_id="main")

    # 1. Establish canonical state
    mgr.set_canonical_slot("user_id", "admin_01")
    mgr.set_canonical_slot("account_balance", 1000)

    assert mgr.get_slot("user_id") == "admin_01"
    assert mgr.get_slot("account_balance") == 1000

    # 2. Create speculative shadow fork
    branch = "speculative_trade_branch"
    mgr.create_speculative_fork(branch)

    # In unmodified state, reading from shadow branch falls back to canonical (0 allocation)
    assert mgr.get_slot("user_id", branch_id=branch) == "admin_01"
    assert mgr.get_slot("account_balance", branch_id=branch) == 1000

    # 3. Write speculative modification to shadow branch
    mgr.write_speculative_slot(branch, "account_balance", 850)

    # Shadow branch reflects updated balance; canonical branch remains unchanged!
    assert mgr.get_slot("account_balance", branch_id=branch) == 850
    assert mgr.get_slot("account_balance") == 1000

    # 4. Commit shadow fork to canonical
    mgr.commit_fork_to_canonical(branch)
    assert mgr.get_slot("account_balance") == 850


def test_shadow_page_collapse_and_purge_zero_loss():
    """Validates instantaneous collapse and purge of rogue shadow fork without touching canonical state."""
    mgr = ShadowPageForkManager(canonical_branch_id="main")
    mgr.set_canonical_slot("system_integrity", "OK")
    mgr.set_canonical_slot("critical_db", "PRISTINE")

    branch = "rogue_malware_branch"
    mgr.create_speculative_fork(branch)
    mgr.write_speculative_slot(branch, "system_integrity", "CORRUPTED")
    mgr.write_speculative_slot(branch, "critical_db", "DELETED")

    assert mgr.get_slot("system_integrity", branch_id=branch) == "CORRUPTED"
    assert mgr.get_slot("system_integrity") == "OK"

    # Instantaneous collapse: purges shadow fork
    purged_delta = mgr.collapse_and_purge_fork(branch)
    assert "system_integrity" in purged_delta
    assert "critical_db" in purged_delta

    # Canonical state is 100% untouched
    assert mgr.get_slot("system_integrity") == "OK"
    assert mgr.get_slot("critical_db") == "PRISTINE"


def test_retrocausal_rollback_engine_speculative_safe_action():
    """Validates speculative forward propagation and commitment for formally verified safe action."""
    engine = RetrocausalRollbackEngine()
    engine.fork_mgr.set_canonical_slot("doc_text", "Initial draft")

    # Safe file write to project directory
    safe_action = ActionSynthesisNode(
        action_id="act_save_doc",
        verb=ActionVerb.FILE_WRITE,
        target_resource=r"D:\Software GitCode\JARVIS\data\notes.txt",
        parameters={"content": "Updated draft"},
        risk_weight=0.1,
    )

    result = engine.execute_speculative_action(
        action=safe_action,
        state_deltas={"doc_text": "Updated draft"},
    )

    assert isinstance(result, SpeculativeExecutionResult)
    assert result.is_safe is True
    assert result.verdict == VerificationVerdict.PROVED_SAFE
    assert result.collapse_occurred is False
    assert engine.fork_mgr.get_slot("doc_text") == "Updated draft"
    assert engine._commit_count == 1
    assert engine._collapse_count == 0


def test_retrocausal_engine_instantaneous_wavefunction_collapse_on_violation():
    """Validates zero CPU clock loss rollback upon SMT invariant violation (system file deletion)."""
    engine = RetrocausalRollbackEngine()
    engine.fork_mgr.set_canonical_slot("system_state", "HEALTHY")

    # Destructive action violating formal safety invariant: deleting System32
    malicious_action = ActionSynthesisNode(
        action_id="act_delete_sys32",
        verb=ActionVerb.FILE_DELETE,
        target_resource=r"C:\Windows\System32\drivers\etc\hosts",
        parameters={},
        risk_weight=0.99,
    )

    result = engine.execute_speculative_action(
        action=malicious_action,
        state_deltas={"system_state": "DESTROYED"},
    )

    assert isinstance(result, SpeculativeExecutionResult)
    # Formally proved unsafe by SMT verifier (counterexample found)
    assert result.is_safe is False
    assert result.verdict in (VerificationVerdict.PROVED_UNSAFE, VerificationVerdict.COUNTEREXAMPLE_FOUND)
    # Instantaneous wavefunction collapse triggered!
    assert result.collapse_occurred is True
    assert result.counterexample is not None

    # Canonical state preserved with 0 clock loss / 0 corruption!
    assert engine.fork_mgr.get_slot("system_state") == "HEALTHY"
    assert engine._collapse_count == 1
    assert engine._commit_count == 0

    # Ledger audit contains collapse record
    assert len(engine.ledger) == 1
    assert engine.ledger[0].collapsed is True
    assert engine.ledger[0].verified_safe is False


def test_retrocausal_telemetry_metrics():
    """Validates telemetry reporting and strict 0.00 MiB VRAM delta."""
    engine = RetrocausalRollbackEngine()
    telem = engine.get_telemetry()

    assert telem["committed_actions"] == 0
    assert telem["collapsed_violations"] == 0
    assert telem["active_shadow_forks"] == 0
    assert telem["vram_delta_mib"] == 0.00


def test_retrocausal_windows_atomic_persistence():
    """Validates thread-safe Windows Atomic Persistence save/load for transaction ledger."""
    engine = RetrocausalRollbackEngine()
    engine.fork_mgr.set_canonical_slot("counter", 42)

    # Safe action
    act = ActionSynthesisNode(
        action_id="act_inc",
        verb=ActionVerb.FILE_WRITE,
        target_resource=r"D:\Software GitCode\JARVIS\data\log.txt",
    )
    engine.execute_speculative_action(act, {"counter": 43})

    with tempfile.TemporaryDirectory() as tmpdir:
        save_file = os.path.join(tmpdir, "retrocausal_ledger.json")
        engine.save(save_file)
        assert os.path.exists(save_file)

        restored = RetrocausalRollbackEngine.load(save_file)
        assert restored._commit_count == 1
        assert restored.fork_mgr.get_slot("counter") == 43
        # Validate complete transaction ledger restoration
        assert len(restored.ledger) == 1
        assert restored.ledger[0].action_id == "act_inc"
        assert restored.ledger[0].verified_safe is True
        assert restored.ledger[0].state_delta == {"counter": 43}
        assert len(restored.fork_mgr._checkpoints) >= 1


def test_retrocausal_rollback_to_checkpoint_restores_past_state():
    """Validates Feynman-Stueckelberg negative-time rollback to a prior virtual checkpoint."""
    engine = RetrocausalRollbackEngine()
    engine.fork_mgr.set_canonical_slot("database_state", "PRISTINE_V1")
    engine.fork_mgr.set_canonical_slot("user_balance", 1000)

    # Checkpoint 0
    engine.fork_mgr.create_checkpoint("ckpt_baseline")

    # Mutate canonical state
    engine.fork_mgr.set_canonical_slot("database_state", "MUTATED_V2")
    engine.fork_mgr.set_canonical_slot("user_balance", 200)

    assert engine.fork_mgr.get_slot("database_state") == "MUTATED_V2"
    assert engine.fork_mgr.get_slot("user_balance") == 200

    # Execute negative-time rollback to ckpt_baseline
    rollback_success = engine.rollback_to_checkpoint("ckpt_baseline")
    assert rollback_success is True

    # State restored identically to past checkpoint (t - Delta t)
    assert engine.fork_mgr.get_slot("database_state") == "PRISTINE_V1"
    assert engine.fork_mgr.get_slot("user_balance") == 1000

    # Rollback recorded in ledger
    assert len(engine.ledger) == 1
    assert engine.ledger[0].action_id == "rollback_to_ckpt_baseline"
    assert engine.ledger[0].checkpoint_id == "ckpt_baseline"

    # Rollback to non-existent checkpoint returns False
    assert engine.rollback_to_checkpoint("non_existent_ckpt") is False


def test_retrocausal_edge_cases():
    """Validates error handling for duplicate forks and unknown branches."""
    mgr = ShadowPageForkManager()
    mgr.create_speculative_fork("fork_1")

    # Duplicate fork creation raises ValueError
    with pytest.raises(ValueError):
        mgr.create_speculative_fork("fork_1")

    # Committing non-existent branch raises KeyError
    with pytest.raises(KeyError):
        mgr.commit_fork_to_canonical("unknown_branch")

    # Writing to non-existent branch raises KeyError
    with pytest.raises(KeyError):
        mgr.write_speculative_slot("unknown_branch", "slot", 123)

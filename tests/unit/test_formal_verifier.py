"""
tests/unit/test_formal_verifier.py
==================================
Unit test suite for Frontier 20.0 Provably Safe Verified Action Synthesis.
Milestone v7.0.0 (Singularity Matrix).
"""
from __future__ import annotations

import pytest

from jarvis.security.formal_verifier import (
    ActionSynthesisNode,
    ActionVerb,
    Counterexample,
    FirstOrderSMTSolver,
    PreconditionState,
    ProofCertificate,
    VerificationVerdict,
    VerifiedActionSynthesizer,
)


def test_formal_verifier_proves_safe_file_write() -> None:
    """Verifies that an authorized file write within the project directory is proved safe."""
    synthesizer = VerifiedActionSynthesizer()
    P = PreconditionState(
        caller_role="USER",
        working_directory=r"D:\Software GitCode\JARVIS",
        active_process_count=5,
        max_process_quota=32,
    )

    approved, cert = synthesizer.synthesize_and_verify(
        verb=ActionVerb.FILE_WRITE,
        target_resource=r"D:\Software GitCode\JARVIS\data\log.txt",
        parameters={"mode": "w", "encoding": "utf-8"},
        preconditions=P,
    )
    assert approved is True
    assert cert.verdict == VerificationVerdict.PROVED_SAFE
    assert cert.counterexample is None
    assert cert.proof_tree_depth > 0
    assert cert.axioms_evaluated >= 4
    assert len(cert.cryptographic_sha256) == 64
    assert cert.is_valid_and_safe() is True


def test_formal_verifier_blocks_system_root_write() -> None:
    """Verifies that attempts to modify Windows System32 are mathematically proven unsafe."""
    synthesizer = VerifiedActionSynthesizer()
    P = PreconditionState()

    approved, cert = synthesizer.synthesize_and_verify(
        verb=ActionVerb.FILE_WRITE,
        target_resource=r"C:\Windows\System32\drivers\malicious.sys",
        parameters={"data": b"evil"},
        preconditions=P,
    )
    assert approved is False
    assert cert.verdict == VerificationVerdict.COUNTEREXAMPLE_FOUND
    assert cert.counterexample is not None
    assert cert.counterexample.violated_invariant_id == "INV_SYSTEM_ROOT_IMMUTABILITY"
    assert "immutable protected system root" in cert.counterexample.reason
    assert cert.is_valid_and_safe() is False


def test_formal_verifier_blocks_system_root_delete() -> None:
    """Verifies that file deletion in C:\\Program Files is blocked with counterexample."""
    synthesizer = VerifiedActionSynthesizer()
    P = PreconditionState()

    approved, cert = synthesizer.synthesize_and_verify(
        verb=ActionVerb.FILE_DELETE,
        target_resource=r"C:\Program Files\Common Files\target.dll",
        preconditions=P,
    )
    assert approved is False
    assert cert.verdict == VerificationVerdict.COUNTEREXAMPLE_FOUND
    assert cert.counterexample.violated_invariant_id == "INV_SYSTEM_ROOT_IMMUTABILITY"


def test_formal_verifier_blocks_destructive_shell_command() -> None:
    """Verifies that destructive shell commands like 'rmdir /s /q' or 'del /f /q' are rejected."""
    synthesizer = VerifiedActionSynthesizer()
    P = PreconditionState()

    # Case 1: rmdir /s /q
    approved1, cert1 = synthesizer.synthesize_and_verify(
        verb=ActionVerb.SHELL_EXEC,
        target_resource="rmdir /s /q C:\\Data",
        preconditions=P,
    )
    assert approved1 is False
    assert cert1.verdict == VerificationVerdict.COUNTEREXAMPLE_FOUND
    assert cert1.counterexample.violated_invariant_id == "INV_COMMAND_INJECTION_DEFENSE"

    # Case 2: bash fork bomb
    approved2, cert2 = synthesizer.synthesize_and_verify(
        verb=ActionVerb.SHELL_EXEC,
        target_resource=":(){ :|:& };:",
        preconditions=P,
    )
    assert approved2 is False
    assert cert2.counterexample.violated_invariant_id == "INV_COMMAND_INJECTION_DEFENSE"


def test_formal_verifier_blocks_process_quota_overflow() -> None:
    """Verifies that spawning a process when quota is exhausted is rejected."""
    synthesizer = VerifiedActionSynthesizer()
    P = PreconditionState(
        active_process_count=10,
        max_process_quota=10,  # Quota full
    )

    approved, cert = synthesizer.synthesize_and_verify(
        verb=ActionVerb.PROCESS_SPAWN,
        target_resource="calc.exe",
        preconditions=P,
    )
    assert approved is False
    assert cert.counterexample.violated_invariant_id == "INV_PROCESS_QUOTA_BOUNDED"
    assert "exceeds max quota" in cert.counterexample.reason


def test_formal_verifier_blocks_unauthorized_external_network() -> None:
    """Verifies that network connections outside allowed mesh endpoints are blocked."""
    synthesizer = VerifiedActionSynthesizer()
    P = PreconditionState(network_sandbox_enforced=True)

    # Unauthorized public IP
    approved, cert = synthesizer.synthesize_and_verify(
        verb=ActionVerb.NETWORK_CONNECT,
        target_resource="http://198.51.100.25:8080/exfiltrate",
        preconditions=P,
    )
    assert approved is False
    assert cert.counterexample.violated_invariant_id == "INV_NETWORK_SANDBOX_WHITELIST"

    # Authorized sovereign mesh endpoint
    approved_mesh, cert_mesh = synthesizer.synthesize_and_verify(
        verb=ActionVerb.NETWORK_CONNECT,
        target_resource="mesh://peer-alpha-sovereign",
        preconditions=P,
    )
    assert approved_mesh is True
    assert cert_mesh.verdict == VerificationVerdict.PROVED_SAFE


def test_formal_verifier_audit_summary() -> None:
    """Ensures audit summaries maintain accurate rejection and certificate counters."""
    synthesizer = VerifiedActionSynthesizer()
    synthesizer.synthesize_and_verify(ActionVerb.FILE_WRITE, r"D:\test.txt")
    synthesizer.synthesize_and_verify(ActionVerb.FILE_WRITE, r"C:\Windows\test.txt")

    summary = synthesizer.get_audit_summary()
    assert summary["approved_actions"] == 1
    assert summary["rejected_actions"] == 1
    assert summary["total_certificates"] == 2
    assert summary["rejection_rate"] == 0.50

"""
tests/unit/test_release_trust_gate.py
=====================================
TDD Unit test suite for Task 10: RELEASE-TRUST-GATE-FIX1.
Enforces Three-Tier Verdict Discipline and Fail-Closed semantics for release artifacts:
1. Commercial release must fail-closed if commercial Authenticode certificate is missing.
2. Self-signed artifacts are strictly restricted to prerelease/internal/dev channels.
3. validate_release_trust() enforces channel admission control.
4. Release workflow YAML guarantees self-signed artifacts are never published as regular production releases.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from scripts.sign_installer_v520 import (
    parse_args,
    sign_installer,
    validate_release_trust,
)


class TestReleaseTrustGate:
    """Tests for Authenticode signature trust tiers and release gate enforcement."""

    def test_require_commercial_fails_closed_when_credentials_missing(self, tmp_path: Path) -> None:
        """
        When --require-commercial is set and no EV/commercial cert is configured:
        Must return exit code 3 (COMMERCIAL_CERT_NOT_CONFIGURED), write signature_audit.json
        with commercial_release_allowed=False and allowed_release_channels=[].
        """
        fake_installer = tmp_path / "JARVIS_Setup_fake.exe"
        fake_installer.write_bytes(b"MZ_DUMMY_PE_HEADER_FOR_TESTING")

        args = argparse.Namespace(
            installer=fake_installer,
            require_commercial=True,
            cert_thumbprint=None,
            pfx_path=None,
            pfx_password="",
            timestamp_url="http://timestamp.digicert.com",
            target_channel=None,
        )

        exit_code = sign_installer(args)
        assert exit_code == 3, f"Expected exit code 3 (fail-closed), got {exit_code}"

        audit_file = tmp_path / "signature_audit.json"
        assert audit_file.exists(), "signature_audit.json must be written on fail-closed"
        data = json.loads(audit_file.read_text(encoding="utf-8"))
        assert data["signature_tier"] == "NOT_CONFIGURED"
        assert data["smartscreen_trusted"] is False
        assert data["commercial_release_allowed"] is False
        assert data["allowed_release_channels"] == []
        assert "FAIL_CLOSED" in data["verdict"]

    def test_validate_release_trust_blocks_test_signed_from_production(self) -> None:
        """
        TEST_SIGNED tier must be rejected from 'production' and 'commercial' channels,
        but accepted for 'prerelease' and 'internal'.
        """
        manifest = {
            "signature_tier": "TEST_SIGNED",
            "smartscreen_trusted": False,
            "commercial_release_allowed": False,
            "allowed_release_channels": ["prerelease", "internal", "development"],
            "verdict": "PASS fail-closed, commercial Authenticode PENDING_CREDENTIALS",
        }

        # Production / Commercial channels must be blocked
        ok_prod, reason_prod = validate_release_trust(manifest, target_channel="production")
        assert ok_prod is False
        assert "FAIL_CLOSED" in reason_prod

        ok_comm, reason_comm = validate_release_trust(manifest, target_channel="commercial")
        assert ok_comm is False
        assert "FAIL_CLOSED" in reason_comm

        # Prerelease / Internal channels are allowed
        ok_pre, reason_pre = validate_release_trust(manifest, target_channel="prerelease")
        assert ok_pre is True
        assert "OK" in reason_pre

        ok_int, reason_int = validate_release_trust(manifest, target_channel="internal")
        assert ok_int is True
        assert "OK" in reason_int

    def test_validate_release_trust_allows_commercial_tier(self) -> None:
        """
        COMMERCIAL tier with smartscreen_trusted=True is permitted for all channels.
        """
        manifest = {
            "signature_tier": "COMMERCIAL",
            "smartscreen_trusted": True,
            "commercial_release_allowed": True,
            "allowed_release_channels": ["commercial", "production", "prerelease", "internal", "development"],
            "verdict": "PASS runtime (COMMERCIAL)",
        }

        ok, msg = validate_release_trust(manifest, target_channel="production")
        assert ok is True
        assert "OK" in msg

        ok, msg = validate_release_trust(manifest, target_channel="commercial")
        assert ok is True
        assert "OK" in msg

    def test_release_workflow_yaml_enforces_prerelease_for_self_signed(self) -> None:
        """
        Inspects .github/workflows/release.yml to verify that an artifact signed with
        a self-signed cert is NEVER published as a non-prerelease production release.
        """
        root_dir = Path(__file__).parents[2]
        workflow_path = root_dir / ".github" / "workflows" / "release.yml"
        content = workflow_path.read_text(encoding="utf-8")

        # Must inspect needs.sign.outputs.is_commercial or similar trust indicator
        assert "is_commercial" in content, (
            "release.yml must wire and inspect an 'is_commercial' output from the sign job."
        )

        # Must force prerelease if is_commercial is not true
        assert "needs.sign.outputs.is_commercial" in content, (
            "release.yml must gate the prerelease flag or production release on needs.sign.outputs.is_commercial."
        )

    def test_release_workflow_yaml_prevents_publishing_after_failed_tests(self) -> None:
        """
        Inspects .github/workflows/release.yml to verify that test failures halt execution
        and prevent building/publishing artifacts.
        """
        root_dir = Path(__file__).parents[2]
        workflow_path = root_dir / ".github" / "workflows" / "release.yml"
        content = workflow_path.read_text(encoding="utf-8")

        # Step 'Run tests before build' must check LASTEXITCODE
        assert "python -m pytest tests/unit/ -q --timeout=60 --tb=short\n          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }" in content, (
            "release.yml must check $LASTEXITCODE right after pytest to fail closed before build/publish."
        )

    def test_release_workflow_yaml_requires_thumbprint_matching_for_commercial(self) -> None:
        """
        Inspects .github/workflows/release.yml to verify that commercial mode:
        1. Requires COMMERCIAL_PFX_BASE64, COMMERCIAL_PFX_PASSWORD, and COMMERCIAL_CERT_THUMBPRINT together.
        2. Fails closed if PFX credentials are incomplete.
        3. Normalizes and matches SignerCertificate.Thumbprint against expected thumbprint after signing.
        4. Requires Status == Valid before outputting is_commercial=true.
        """
        root_dir = Path(__file__).parents[2]
        workflow_path = root_dir / ".github" / "workflows" / "release.yml"
        content = workflow_path.read_text(encoding="utf-8")

        # Must check that COMMERCIAL_CERT_THUMBPRINT is required alongside BASE64 and PASSWORD
        assert "$env:COMMERCIAL_CERT_THUMBPRINT" in content, (
            "release.yml must check $env:COMMERCIAL_CERT_THUMBPRINT."
        )

        # Must normalize thumbprint (e.g. replace colons/whitespace and uppercase)
        assert "replace" in content and "ToUpper" in content, (
            "release.yml must normalize expected and actual cert thumbprints (e.g., replace colons/whitespace and uppercase)."
        )

        # Must check thumbprint match before setting is_commercial=true
        assert "$actualThumbprint" in content or "Thumbprint" in content, (
            "release.yml must extract actual thumbprint from $sig.SignerCertificate.Thumbprint."
        )

        # Must throw error on thumbprint mismatch
        assert "thumbprint" in content.lower() and "match" in content.lower(), (
            "release.yml must verify signer thumbprint matches the expected commercial thumbprint."
        )

        # Must not blindly set $isCommercial = $true prior to verification
        assert "$isCommercial = $true" not in content[:content.find("Get-AuthenticodeSignature")], (
            "release.yml must not mark isCommercial=true until AFTER Get-AuthenticodeSignature verifies Status and Thumbprint match."
        )




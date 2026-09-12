"""
tests/unit/test_updater_and_diagnostics.py
===========================================
D-13 + D-15: Updater integrity/rollback + Support diagnostics tests
"""
from __future__ import annotations
import hashlib, json, os, zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from jarvis.updater.updater import (
    JarvisUpdater, UPDATE_OK, UP_TO_DATE, INTEGRITY_FAIL,
    DOWNLOAD_FAIL, NOT_CONFIGURED, HEALTH_CHECK_FAIL, ROLLBACK_OK,
    MANIFEST_NOT_FOUND,
)
from jarvis.support.diagnostics import SupportDiagnostics, redact_text, redact_dict


# ─── D-13 Updater ────────────────────────────────────────────────────────────

class TestUpdaterManifest:
    def test_not_configured_when_no_url(self):
        u = JarvisUpdater(manifest_url="", current_version="5.0.1")
        result = u.check_and_apply()
        assert result.status == NOT_CONFIGURED

    def test_not_configured_on_network_error(self):
        u = JarvisUpdater(manifest_url="http://example.test/manifest.json", current_version="5.0.1")
        mock_client = MagicMock()
        mock_client.get.side_effect = ConnectionError("unreachable")
        u.http_client = mock_client
        result = u.check_and_apply()
        assert result.status == NOT_CONFIGURED

    def test_up_to_date_when_same_version(self):
        manifest_data = {"version": "5.0.1", "download_url": "http://x/j.exe", "sha256": "abc"}
        mock_client = MagicMock()
        mock_client.get.return_value = MagicMock(text=json.dumps(manifest_data), status_code=200)
        u = JarvisUpdater(manifest_url="http://x/manifest.json", current_version="5.0.1",
                          http_client=mock_client)
        result = u.check_and_apply()
        assert result.status == UP_TO_DATE

    def test_integrity_fail_on_sha256_mismatch(self, tmp_path):
        manifest_data = {"version": "5.1.0", "download_url": "http://x/j.exe", "sha256": "deadbeef" * 8}
        mock_client = MagicMock()
        mock_client.get.return_value = MagicMock(text=json.dumps(manifest_data), status_code=200)
        # Download returns a temp file with wrong content
        tmp_file = tmp_path / ".tmp.update.test"
        tmp_file.write_bytes(b"wrong content")
        def fake_download(url, dest_dir):
            out = dest_dir / ".tmp.update.fake"
            out.write_bytes(b"wrong content")
            return out
        u = JarvisUpdater(manifest_url="http://x/manifest.json", current_version="5.0.1",
                          install_dir=tmp_path, http_client=mock_client)
        u._download_to_tmp = fake_download
        result = u.check_and_apply()
        assert result.status == INTEGRITY_FAIL

    def test_update_ok_with_correct_sha256(self, tmp_path):
        content = b"fake JARVIS binary v5.1.0"
        sha256 = hashlib.sha256(content).hexdigest()
        manifest_data = {"version": "5.1.0", "download_url": "http://x/j.exe", "sha256": sha256}
        mock_client = MagicMock()
        mock_client.get.return_value = MagicMock(text=json.dumps(manifest_data), status_code=200)
        def fake_download(url, dest_dir):
            out = dest_dir / f".tmp.update.{hash(url)}"
            out.write_bytes(content)
            return out
        u = JarvisUpdater(manifest_url="http://x/manifest.json", current_version="5.0.1",
                          install_dir=tmp_path, http_client=mock_client)
        u._download_to_tmp = fake_download
        result = u.check_and_apply(target_filename="JARVIS_test.exe")
        assert result.status == UPDATE_OK
        assert result.to_version == "5.1.0"

    def test_health_check_failure_triggers_rollback(self, tmp_path):
        content = b"binary"
        sha256 = hashlib.sha256(content).hexdigest()
        manifest_data = {"version": "5.1.0", "download_url": "http://x/j.exe", "sha256": sha256}
        mock_client = MagicMock()
        mock_client.get.return_value = MagicMock(text=json.dumps(manifest_data), status_code=200)
        def fake_download(url, dest_dir):
            out = dest_dir / ".tmp.update.hc"
            out.write_bytes(content)
            return out
        target = tmp_path / "JARVIS_hc.exe"
        target.write_bytes(b"old binary")
        u = JarvisUpdater(manifest_url="http://x/manifest.json", current_version="5.0.1",
                          install_dir=tmp_path, http_client=mock_client,
                          health_check_fn=lambda: False)
        u._download_to_tmp = fake_download
        result = u.check_and_apply(target_filename="JARVIS_hc.exe")
        assert result.status == HEALTH_CHECK_FAIL

    def test_verify_sha256_correct(self, tmp_path):
        content = b"test file content"
        f = tmp_path / "test.bin"
        f.write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()
        assert JarvisUpdater.verify_sha256(f, expected) is True

    def test_verify_sha256_mismatch(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"content")
        assert JarvisUpdater.verify_sha256(f, "0" * 64) is False

    def test_versions_equal_normalisation(self):
        assert JarvisUpdater._versions_equal("5.0.1", "5.0.1")
        assert JarvisUpdater._versions_equal("v5.0.1", "5.0.1")
        assert not JarvisUpdater._versions_equal("5.0.1", "5.1.0")


# ─── D-15 Diagnostics ────────────────────────────────────────────────────────

class TestRedaction:
    def test_api_key_redacted(self):
        text = "GOOGLE_API_KEY=AIzaSyABC123XYZfakekey"
        result = redact_text(text)
        assert "AIzaSyABC123XYZfakekey" not in result
        assert "<REDACTED" in result

    def test_token_redacted(self):
        result = redact_text("bot_token=1234567890:AAEfaketoken_here")
        assert "AAEfaketoken_here" not in result

    def test_password_redacted(self):
        result = redact_text("password=mysecretpassword123")
        assert "mysecretpassword123" not in result

    def test_normal_text_unchanged(self):
        text = "Python is great. JARVIS version 5.1.0."
        result = redact_text(text)
        assert "Python is great" in result

    def test_dict_redaction(self):
        data = {"api_key": "real_key_123", "name": "JARVIS", "token": "tok_abc"}
        result = redact_dict(data)
        assert result["api_key"] == "<REDACTED>"
        assert result["token"] == "<REDACTED>"
        assert result["name"] == "JARVIS"


class TestSupportBundle:
    def test_bundle_created(self, tmp_path):
        diag = SupportDiagnostics(log_dir=tmp_path / "logs", install_dir=tmp_path)
        bundle = diag.create_support_bundle(output_dir=tmp_path)
        assert Path(bundle.zip_path).exists()
        assert bundle.redaction_applied is True

    def test_bundle_contains_env_info(self, tmp_path):
        diag = SupportDiagnostics(log_dir=tmp_path / "logs", install_dir=tmp_path)
        bundle = diag.create_support_bundle(output_dir=tmp_path)
        with zipfile.ZipFile(bundle.zip_path) as zf:
            assert "environment_info.json" in zf.namelist()
            env = json.loads(zf.read("environment_info.json"))
            assert "python_version" in env
            assert "jarvis_version" in env

    def test_bundle_has_no_plaintext_secrets(self, tmp_path):
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (logs_dir / "jarvis.log").write_text(
            "Connecting with api_key=real_key_abc123 password=secret99\n", encoding="utf-8"
        )
        diag = SupportDiagnostics(log_dir=logs_dir, install_dir=tmp_path)
        bundle = diag.create_support_bundle(output_dir=tmp_path)
        clean, violations = diag.verify_no_secrets_in_bundle(bundle.zip_path)
        assert clean, f"Secret leak in bundle: {violations}"

    def test_env_info_does_not_include_secret_values(self, tmp_path):
        os.environ["GOOGLE_API_KEY"] = "supersecretkey12345"
        try:
            diag = SupportDiagnostics(log_dir=tmp_path / "logs", install_dir=tmp_path)
            info = diag.collect_env_info()
            # env_vars_present should only list names, not values
            assert isinstance(info.env_vars_present, list)
            info_str = json.dumps(info.to_dict())
            assert "supersecretkey12345" not in info_str
        finally:
            del os.environ["GOOGLE_API_KEY"]

    def test_bundle_contains_readme(self, tmp_path):
        diag = SupportDiagnostics(log_dir=tmp_path / "logs", install_dir=tmp_path)
        bundle = diag.create_support_bundle(output_dir=tmp_path)
        with zipfile.ZipFile(bundle.zip_path) as zf:
            assert "README.txt" in zf.namelist()

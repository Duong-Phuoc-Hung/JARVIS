"""
tests/unit/test_updater_safety.py
===================================
Seam tests for Task 4: UPDATER-SAFETY-DESIGN.
Verifies:
1. AutoUpdater initializes update history log by default (no AttributeError).
2. AutoUpdater fails when dependency installation fails (pip install failure).
3. auto_updater skill delegates to JarvisUpdater with SHA-256 integrity check.
4. auto_updater skill fails-closed (NOT_CONFIGURED) when manifest is missing.
5. auto_updater skill rejects updates on integrity / checksum failure.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import jarvis.skills.auto_updater as skill_mod
from jarvis.updater.updater import (
    INTEGRITY_FAIL,
    NOT_CONFIGURED,
    UP_TO_DATE,
    UPDATE_OK,
    JarvisUpdater,
    UpdateResult,
)
from jarvis.workers.auto_updater import AutoUpdater, ReleaseInfo


class TestAutoUpdaterSafety:
    def test_auto_updater_history_log_initialized_by_default(self, tmp_path, monkeypatch):
        """AutoUpdater must have a valid log path by default and persist history without errors."""
        test_log = tmp_path / "logs" / "update_history.json"
        monkeypatch.setattr("jarvis.workers.auto_updater._UPDATE_LOG", test_log)
        
        updater = AutoUpdater(is_mock=True)
        status = updater.check_for_update()
        assert status is not None

        history = updater.get_update_history()
        assert isinstance(history, list)
        assert len(history) == 1
        assert history[0]["current_version"] == status.current_version
        assert history[0]["latest_version"] == status.latest_version

    def test_apply_update_fails_when_pip_install_fails(self, monkeypatch):
        """AutoUpdater.apply_update must return success=False if pip install fails."""
        updater = AutoUpdater(is_mock=False)
        release = ReleaseInfo(
            tag="v4.2.0",
            name="Release 4.2.0",
            body="New features",
            published_at="2026-10-10T00:00:00Z",
        )

        # Mock subprocess.run: git pull succeeds (0), but pip install fails (1)
        calls = []
        def fake_run(cmd, *args, **kwargs):
            calls.append(cmd)
            mock_proc = MagicMock()
            if cmd[:2] == ["git", "pull"]:
                mock_proc.returncode = 0
                mock_proc.stdout = "Already up to date."
                mock_proc.stderr = ""
            else:
                mock_proc.returncode = 1
                mock_proc.stdout = ""
                mock_proc.stderr = "ERROR: Failed to build dependency wheel"
            return mock_proc

        monkeypatch.setattr("subprocess.run", fake_run)
        monkeypatch.setattr(updater, "_backup_current", lambda: None)

        result = updater.apply_update(release)
        assert result["success"] is False
        assert "thất bại" in result["message"].lower() or "error" in result["message"].lower()


class TestSkillUpdaterWiring:
    def test_skill_check_fails_closed_when_manifest_unconfigured(self, monkeypatch):
        """When no manifest URL is configured, skill check must report fail-closed NOT_CONFIGURED."""
        monkeypatch.setenv("JARVIS_UPDATE_MANIFEST_URL", "")
        # Reset cached updater
        monkeypatch.setattr(skill_mod, "_UPDATER", None)

        res = skill_mod.execute(action="check")
        assert res["data"]["success"] is False
        assert res["data"]["status"] == NOT_CONFIGURED
        assert "NOT_CONFIGURED" in res["output"] or "chưa được cấu hình" in res["output"]

    def test_skill_update_aborts_on_sha256_integrity_failure(self, monkeypatch):
        """Skill update must abort with failure if SHA-256 verification fails."""
        mock_updater = MagicMock(spec=JarvisUpdater)
        mock_updater.check_and_apply.return_value = UpdateResult(
            status=INTEGRITY_FAIL,
            from_version="5.0.0",
            to_version="5.1.0",
            error="SHA-256 mismatch — update aborted",
        )
        monkeypatch.setattr(skill_mod, "_get_updater", lambda: mock_updater)

        res = skill_mod.execute(action="update", confirm=True)
        assert res["data"]["success"] is False
        assert res["data"]["status"] == INTEGRITY_FAIL
        assert "toàn vẹn" in res["output"] or "SHA-256" in res["output"]

    def test_skill_update_succeeds_when_sha256_verified(self, monkeypatch):
        """Skill update succeeds and reports success when JarvisUpdater succeeds."""
        mock_updater = MagicMock(spec=JarvisUpdater)
        mock_updater.check_and_apply.return_value = UpdateResult(
            status=UPDATE_OK,
            from_version="5.0.0",
            to_version="5.1.0",
        )
        monkeypatch.setattr(skill_mod, "_get_updater", lambda: mock_updater)

        res = skill_mod.execute(action="update", confirm=True)
        assert res["data"]["success"] is True
        assert res["data"]["status"] == UPDATE_OK
        assert "5.1.0" in res["output"]


class TestUpdaterSafetyDefects:
    def test_stable_release_is_newer_than_matching_prerelease(self):
        """SemVer precedence: 5.1.0 must upgrade 5.1.0-beta."""
        assert JarvisUpdater._is_newer("5.1.0", "5.1.0-beta") is True
        assert JarvisUpdater._is_newer("5.1.0-beta", "5.1.0") is False

        auto_updater = AutoUpdater(is_mock=True)
        assert auto_updater._version_newer("5.1.0", "5.1.0-beta") is True
        assert auto_updater._version_newer("5.1.0-beta", "5.1.0") is False

    def test_default_history_path_uses_central_data_directory(self, tmp_path, monkeypatch):
        """Installed builds must not write mutable history inside Program Files/repo cwd."""
        monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
        monkeypatch.setattr("jarvis.workers.auto_updater._UPDATE_LOG", None)

        from jarvis.workers.auto_updater import _get_update_log_path

        assert _get_update_log_path() == tmp_path / "logs" / "update_history.json"

    def test_version_comparison_older_manifest_not_treated_as_upgrade(self, tmp_path):
        """JarvisUpdater and AutoUpdater must not treat an older manifest version as an upgrade."""
        content = b"fake binary"
        sha256 = hashlib.sha256(content).hexdigest()
        manifest_data = {"version": "3.0.0", "download_url": "http://x/j.exe", "sha256": sha256}
        mock_client = MagicMock()
        mock_client.get.return_value = MagicMock(text=json.dumps(manifest_data), status_code=200)

        def fake_download(url, dest_dir):
            out = dest_dir / ".tmp.update.fake"
            out.write_bytes(content)
            return out

        updater = JarvisUpdater(
            manifest_url="http://x/manifest.json",
            current_version="3.1.0",
            install_dir=tmp_path,
            http_client=mock_client,
        )
        updater._download_to_tmp = fake_download
        result = updater.check_and_apply()
        assert result.status == UP_TO_DATE
        assert result.to_version == "3.0.0"

        auto_updater = AutoUpdater(is_mock=True)
        assert auto_updater._version_newer("3.0.0", "3.1.0") is False
        assert auto_updater._version_newer("3.1.0-beta", "3.1.0") is False
        assert auto_updater._version_newer("3.2.0", "3.1.0") is True

    def test_skill_update_requires_confirm(self, monkeypatch):
        """Skill update must require confirm=True and return pending status when confirm=False."""
        mock_updater = MagicMock(spec=JarvisUpdater)
        mock_updater.manifest_url = "http://x/manifest.json"
        mock_updater.current_version = "5.0.0"
        mock_updater.fetch_manifest.return_value = MagicMock(
            version="5.1.0",
            sha256="abc",
            release_notes="Notes",
        )
        mock_updater._versions_equal.return_value = False
        monkeypatch.setattr(skill_mod, "_get_updater", lambda: mock_updater)

        res = skill_mod.execute(action="update", confirm=False)
        assert res["data"].get("pending") is True
        assert res["data"].get("success") is True
        mock_updater.check_and_apply.assert_not_called()

    def test_skill_rollback_requires_confirm(self, monkeypatch):
        """Skill rollback must require confirm=True and return pending status when confirm=False."""
        mock_updater = MagicMock(spec=JarvisUpdater)
        monkeypatch.setattr(skill_mod, "_get_updater", lambda: mock_updater)

        res = skill_mod.execute(action="rollback", confirm=False)
        assert res["data"].get("pending") is True
        assert res["data"].get("success") is True
        mock_updater.rollback.assert_not_called()

    def test_skill_fails_closed_when_manifest_fails_or_unconfigured(self, monkeypatch):
        """Skill execute update with confirm=True must fail closed when manifest is unavailable."""
        mock_updater = MagicMock(spec=JarvisUpdater)
        mock_updater.check_and_apply.return_value = UpdateResult(
            status=NOT_CONFIGURED,
            error="Manifest unavailable",
        )
        monkeypatch.setattr(skill_mod, "_get_updater", lambda: mock_updater)

        res = skill_mod.execute(action="update", confirm=True)
        assert res["data"]["success"] is False
        assert res["data"]["status"] == NOT_CONFIGURED

    def test_rollback_truthful_on_failure(self, tmp_path, monkeypatch):
        """AutoUpdater.rollback and skill rollback must report success=False when rollback fails."""
        auto_updater = AutoUpdater(is_mock=False)
        monkeypatch.setattr("jarvis.workers.auto_updater._BACKUP_DIR", tmp_path)
        backup_file = tmp_path / "backup_v1.0.0_20261010.txt"
        backup_file.write_text("version=1.0.0\n")

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "error: pathspec '1.0.0' did not match any file(s) known to git"
        monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: mock_proc)

        res = auto_updater.rollback()
        assert res["success"] is False
        assert "thất bại" in res["message"].lower() or "error" in res["message"].lower()

        # Skill rollback with failed result
        mock_updater = MagicMock(spec=JarvisUpdater)
        mock_updater.install_dir = tmp_path
        mock_updater.BACKUP_SUFFIX = ".backup"
        target = tmp_path / "JARVIS.exe"
        backup = tmp_path / "JARVIS.exe.backup"
        backup.write_bytes(b"old binary")
        mock_updater.rollback.return_value = "ROLLBACK_FAILED"
        monkeypatch.setattr(skill_mod, "_get_updater", lambda: mock_updater)

        skill_res = skill_mod.execute(action="rollback", confirm=True)
        assert skill_res["data"]["success"] is False
        assert skill_res["data"]["status"] == "ROLLBACK_FAILED"

    def test_history_persistence_atomic_and_truthful_errors(self, tmp_path, monkeypatch):
        """AutoUpdater history log must be saved atomically and contain error records on failure."""
        log_file = tmp_path / "logs" / "update_history.json"
        monkeypatch.setattr("jarvis.workers.auto_updater._UPDATE_LOG", log_file)

        updater = AutoUpdater(is_mock=False)
        release = ReleaseInfo(
            tag="v4.2.0",
            name="Release 4.2.0",
            body="New features",
            published_at="2026-10-10T00:00:00Z",
        )

        mock_proc = MagicMock()
        mock_proc.returncode = 128
        mock_proc.stderr = "fatal: not a git repository"
        monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: mock_proc)
        monkeypatch.setattr(updater, "_backup_current", lambda: None)

        res = updater.apply_update(release)
        assert res["success"] is False

        history = updater.get_update_history()
        assert len(history) >= 1
        assert history[0]["applied"] is False
        assert "fatal" in history[0].get("error", "").lower() or "git" in history[0].get("error", "").lower()


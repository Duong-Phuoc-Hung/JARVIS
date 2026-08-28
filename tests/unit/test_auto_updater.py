"""
tests/unit/test_auto_updater.py
===================================
Unit tests for AutoUpdater daemon (mock mode — no real GitHub calls).
"""
from __future__ import annotations
from pathlib import Path
import pytest

from jarvis.workers.auto_updater import AutoUpdater, ReleaseInfo, UpdateStatus


@pytest.fixture
def updater():
    return AutoUpdater(is_mock=True)


class TestVersionDetection:
    def test_get_current_version_returns_string(self, updater):
        version = updater.get_current_version()
        assert isinstance(version, str)
        assert len(version) > 0

    def test_version_format_semver(self, updater):
        version = updater.get_current_version()
        parts = version.split(".")
        assert len(parts) >= 2

    def test_version_newer_comparison(self, updater):
        assert updater._version_newer("3.1.0", "3.0.0") is True
        assert updater._version_newer("3.0.0", "3.1.0") is False
        assert updater._version_newer("3.0.0", "3.0.0") is False

    def test_version_minor_comparison(self, updater):
        assert updater._version_newer("2.10.0", "2.9.0") is True


class TestFetchRelease:
    def test_mock_fetch_returns_release_info(self, updater):
        release = updater.fetch_latest_release()
        assert release is not None
        assert isinstance(release, ReleaseInfo)

    def test_mock_release_has_tag(self, updater):
        release = updater.fetch_latest_release()
        assert release.tag.startswith("v")

    def test_mock_release_has_body(self, updater):
        release = updater.fetch_latest_release()
        assert len(release.body) > 0


class TestCheckForUpdate:
    def test_check_returns_status(self, updater):
        status = updater.check_for_update()
        assert isinstance(status, UpdateStatus)

    def test_status_has_versions(self, updater):
        status = updater.check_for_update()
        assert isinstance(status.current_version, str)
        assert isinstance(status.latest_version, str)

    def test_status_has_checked_at(self, updater):
        status = updater.check_for_update()
        assert status.checked_at != ""

    def test_last_status_stored(self, updater):
        updater.check_for_update()
        assert updater.get_last_status() is not None


class TestApplyUpdate:
    def test_mock_apply_returns_success(self, updater):
        release = updater.fetch_latest_release()
        result = updater.apply_update(release)
        assert result["success"] is True

    def test_mock_apply_returns_new_version(self, updater):
        release = updater.fetch_latest_release()
        result = updater.apply_update(release)
        assert "v3" in result.get("new_version", "")


class TestRollback:
    def test_mock_rollback_returns_success(self, updater):
        result = updater.rollback()
        assert result["success"] is True


class TestHistory:
    def test_history_initially_list(self, updater):
        history = updater.get_update_history()
        assert isinstance(history, list)

    def test_check_creates_history_entry(self, updater, tmp_path, monkeypatch):
        import jarvis.workers.auto_updater as mod
        monkeypatch.setattr(mod, "_UPDATE_LOG", tmp_path / "history.json")
        monkeypatch.setattr(mod, "_BACKUP_DIR", tmp_path / "backups")
        (tmp_path / "backups").mkdir()
        updater2 = AutoUpdater(is_mock=True)
        updater2.check_for_update()
        history = updater2.get_update_history()
        assert len(history) >= 1
        assert "checked_at" in history[0]

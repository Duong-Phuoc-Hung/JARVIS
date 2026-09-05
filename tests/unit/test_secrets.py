"""
tests/unit/test_secrets.py
==========================
Unit tests for SecretsManager and .env migration to Windows Credential Manager.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jarvis.security.secrets import (
    KNOWN_SECRETS,
    get_secret,
    set_secret,
    delete_secret,
    migrate_from_dotenv,
)


class TestMigrateFromDotenvSlice1:
    """Slice 1: Test reading .env, dry-run, and migrating to keyring."""

    def test_migrate_from_dotenv_dry_run_does_not_call_set_secret(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "GEMINI_API_KEY=AIzaSyTestKey123\n"
            "TELEGRAM_BOT_TOKEN=987654:ABC-DEF1234\n"
            "OTHER_NON_SECRET=hello_world\n",
            encoding="utf-8",
        )

        with patch("jarvis.security.secrets.set_secret") as mock_set:
            results = migrate_from_dotenv(dotenv_path=env_file, dry_run=True)

            assert mock_set.call_count == 0
            assert "GEMINI_API_KEY" in results
            assert "would_migrate" in results["GEMINI_API_KEY"]
            assert "TELEGRAM_BOT_TOKEN" in results
            assert "would_migrate" in results["TELEGRAM_BOT_TOKEN"]
            assert "OTHER_NON_SECRET" not in results

    def test_migrate_from_dotenv_executes_set_secret(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "GEMINI_API_KEY=AIzaSyTestKey123\n"
            "# A comment\n"
            "DISCORD_BOT_TOKEN=MTA1M...testtoken\n",
            encoding="utf-8",
        )

        with patch("jarvis.security.secrets.set_secret", return_value=True) as mock_set:
            results = migrate_from_dotenv(dotenv_path=env_file, dry_run=False)

            assert mock_set.call_count == 2
            mock_set.assert_any_call("GEMINI_API_KEY", "AIzaSyTestKey123")
            mock_set.assert_any_call("DISCORD_BOT_TOKEN", "MTA1M...testtoken")
            assert results["GEMINI_API_KEY"] == "migrated"
            assert results["DISCORD_BOT_TOKEN"] == "migrated"

    def test_migrate_from_dotenv_nonexistent_file_raises(self, tmp_path):
        nonexistent = tmp_path / "does_not_exist.env"
        with pytest.raises(FileNotFoundError):
            migrate_from_dotenv(dotenv_path=nonexistent)


class TestMigrateFromDotenvSlice2Purge:
    """Slice 2: Purge plaintext secrets from .env after successful migration."""

    def test_purge_secrets_replaces_migrated_keys_with_comment(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# System Environment\n"
            "APP_ENV=production\n"
            "GEMINI_API_KEY=AIzaSyOriginalSecretKey\n"
            "PORT=8080\n",
            encoding="utf-8",
        )

        with patch("jarvis.security.secrets.set_secret", return_value=True):
            results = migrate_from_dotenv(
                dotenv_path=env_file,
                dry_run=False,
                purge_secrets=True,
            )

        assert results["GEMINI_API_KEY"] == "migrated"
        updated_content = env_file.read_text(encoding="utf-8")

        # The plaintext key must NO LONGER be in the file
        assert "AIzaSyOriginalSecretKey" not in updated_content
        # Non-secrets and comments must be preserved intact
        assert "# System Environment" in updated_content
        assert "APP_ENV=production" in updated_content
        assert "PORT=8080" in updated_content
        # Migration note is present
        assert "# GEMINI_API_KEY=<migrated to Windows Credential Manager>" in updated_content

    def test_purge_secrets_skipped_on_dry_run(self, tmp_path):
        env_file = tmp_path / ".env"
        initial_content = "GEMINI_API_KEY=Secret123\n"
        env_file.write_text(initial_content, encoding="utf-8")

        migrate_from_dotenv(dotenv_path=env_file, dry_run=True, purge_secrets=True)

        assert env_file.read_text(encoding="utf-8") == initial_content

    def test_purge_secrets_skipped_if_set_secret_fails(self, tmp_path):
        env_file = tmp_path / ".env"
        initial_content = "GEMINI_API_KEY=Secret123\n"
        env_file.write_text(initial_content, encoding="utf-8")

        with patch("jarvis.security.secrets.set_secret", return_value=False):
            results = migrate_from_dotenv(dotenv_path=env_file, dry_run=False, purge_secrets=True)

        assert results["GEMINI_API_KEY"] == "failed"
        # Since it failed, secret must not be purged!
        assert env_file.read_text(encoding="utf-8") == initial_content


class TestConfigManagerSecretsIntegrationSlice3:
    """Slice 3: ConfigManager loads secrets from SecretsManager / Windows Credential Manager."""

    def test_config_manager_loads_secret_from_secrets_manager(self, tmp_path, monkeypatch):
        from jarvis.core.config import ConfigManager

        # Ensure env vars are clean
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

        empty_env = tmp_path / ".env"
        empty_env.write_text("# No secrets here\n", encoding="utf-8")

        mock_secrets = {
            "GEMINI_API_KEY": "AIzaSyKeyringLoadedSecret999",
            "TELEGRAM_BOT_TOKEN": "112233:KeyringTelegramToken",
        }

        with patch("jarvis.security.secrets.get_secret", side_effect=lambda name, fallback_env=True: mock_secrets.get(name)):
            cfg_mgr = ConfigManager(env_file_path=empty_env)
            cfg = cfg_mgr.load()

            assert cfg_mgr.get("vision.gemini_api_key") == "AIzaSyKeyringLoadedSecret999"
            assert cfg_mgr.get("comms.telegram.bot_token") == "112233:KeyringTelegramToken"


class TestSecretsCLISlice4:
    """Slice 4: CLI interface for secrets management and dotenv migration."""

    def test_cli_migrate_dotenv_dry_run(self, tmp_path, capsys):
        from jarvis.security import secrets
        import sys

        env_file = tmp_path / ".env"
        env_file.write_text("GEMINI_API_KEY=AIzaSySecret123\n", encoding="utf-8")

        test_args = ["secrets.py", "migrate-dotenv", "--path", str(env_file), "--dry-run"]
        with patch.object(sys, "argv", test_args):
            with patch("jarvis.security.secrets.set_secret") as mock_set:
                # Call main entrypoint logic
                import argparse
                ap = argparse.ArgumentParser(description="JARVIS Secrets Manager")
                sub = ap.add_subparsers(dest="cmd")
                mig_dotenv = sub.add_parser("migrate-dotenv")
                mig_dotenv.add_argument("--path", default=".env")
                mig_dotenv.add_argument("--dry-run", action="store_true")
                mig_dotenv.add_argument("--purge", action="store_true")
                args = ap.parse_args(test_args[1:])

                results = secrets.migrate_from_dotenv(
                    dotenv_path=args.path,
                    dry_run=args.dry_run,
                    purge_secrets=args.purge,
                )
                assert "GEMINI_API_KEY" in results
                assert "would_migrate" in results["GEMINI_API_KEY"]
                assert mock_set.call_count == 0




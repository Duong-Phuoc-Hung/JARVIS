"""
Unit tests for CLI commands, argument parsing, and subcommand dispatching.
"""
from __future__ import annotations

import io
import sys
import unittest
from unittest.mock import patch

from jarvis import __version__
from jarvis.cli import build_parser, main, run_health_check
from jarvis.core.config import ConfigManager
from tests.mocks.win32_mocks import MockWinreg


class TestCLI(unittest.TestCase):

    def test_parser_run_subcommand(self) -> None:
        """Verify parsing 'run' subcommand and flags."""
        parser = build_parser()
        args = parser.parse_args(["run", "--headless", "--no-hot-reload"])
        self.assertEqual(args.command, "run")
        self.assertTrue(args.headless)
        self.assertTrue(args.no_hot_reload)

    def test_parser_health_subcommands(self) -> None:
        """Verify parsing 'health-check' and 'health' subcommands."""
        parser = build_parser()
        args1 = parser.parse_args(["health-check"])
        self.assertEqual(args1.command, "health-check")

        args2 = parser.parse_args(["health"])
        self.assertEqual(args2.command, "health")

    def test_parser_custom_config_and_log_level(self) -> None:
        """Verify parsing global options --config and --log-level."""
        parser = build_parser()
        args = parser.parse_args(["-c", "my_config.yaml", "--log-level", "DEBUG", "run"])
        self.assertEqual(args.config, "my_config.yaml")
        self.assertEqual(args.log_level, "DEBUG")
        self.assertEqual(args.command, "run")

    def test_run_health_check_execution(self) -> None:
        """Verify health check runs without exceptions and returns exit code 0."""
        cfg = ConfigManager()
        cfg.load()
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            exit_code = run_health_check(cfg)
            output = mock_out.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("JARVIS System Health Diagnostics", output)
        self.assertIn(f"v{__version__}", output)

    def test_cli_autostart_subcommands_mocked(self) -> None:
        """Verify install-autostart, autostart-status, and uninstall-autostart CLI commands."""
        mock_reg = MockWinreg()
        with patch.dict(sys.modules, {"winreg": mock_reg}):
            with patch("sys.platform", "win32"):
                # Install
                with patch("sys.stdout", new_callable=io.StringIO):
                    exit_code = main(["install-autostart"])
                    self.assertEqual(exit_code, 0)

                # Status
                with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                    exit_code = main(["autostart-status"])
                    self.assertEqual(exit_code, 0)
                    self.assertIn("ENABLED", mock_out.getvalue())

                # Uninstall
                with patch("sys.stdout", new_callable=io.StringIO):
                    exit_code = main(["uninstall-autostart"])
                    self.assertEqual(exit_code, 0)

                # Status after uninstall
                with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                    exit_code = main(["autostart-status"])
                    self.assertEqual(exit_code, 0)
                    self.assertIn("DISABLED", mock_out.getvalue())


if __name__ == "__main__":
    unittest.main()

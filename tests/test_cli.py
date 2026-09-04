"""
Unit tests for CLI commands, argument parsing, and subcommand dispatching.
"""
from __future__ import annotations

import io
import sys
import unittest
from unittest.mock import MagicMock, patch

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

    def test_parser_menu_subcommand(self) -> None:
        """Verify parsing the 'menu' subcommand (Terminal Control Center)."""
        parser = build_parser()
        args = parser.parse_args(["menu"])
        self.assertEqual(args.command, "menu")

    def test_version_flag_exits_zero_and_prints_version(self) -> None:
        """Verify --version prints the real package version and exits 0."""
        parser = build_parser()
        with self.assertRaises(SystemExit) as ctx:
            parser.parse_args(["--version"])
        self.assertEqual(ctx.exception.code, 0)

    def test_menu_command_routes_to_terminal_menu_without_starting_jarvis(self) -> None:
        """Verify `jarvis menu` routes to run_terminal_menu(), not to
        JarvisApp -- this must never construct the real voice/daemon core."""
        with patch("jarvis.ui.terminal.app.run_terminal_menu", return_value=0) as mock_menu:
            exit_code = main(["menu"])
        self.assertEqual(exit_code, 0)
        mock_menu.assert_called_once()

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


class TestSingleInstanceMutex(unittest.TestCase):
    """
    P0 runaway-hardening regression tests for jarvis.cli's OS-backed named
    Win32 mutex single-instance guard (jarvis/cli.py::
    _acquire_single_instance_mutex()/_release_single_instance_mutex()).
    Simulates contention entirely via mocked ctypes calls -- no real second
    JARVIS process is ever started, and JarvisApp/its heavy subsystems
    (STT/audio/GPU/tray/hotkeys) are never constructed by these tests.

    Pre-commit review correction: _acquire_single_instance_mutex() now
    returns a three-state SingleInstanceResult (ACQUIRED/ALREADY_RUNNING/
    CHECK_FAILED), not a bool -- every assertion below compares against the
    specific enum member, never a bare truthiness check (which would treat
    every non-None enum member as truthy regardless of which one it is).
    """

    def setUp(self) -> None:
        import jarvis.cli as cli_module
        self.cli_module = cli_module
        self.SingleInstanceResult = cli_module.SingleInstanceResult
        self._orig_mutex = cli_module._SINGLE_INSTANCE_MUTEX
        cli_module._SINGLE_INSTANCE_MUTEX = None

    def tearDown(self) -> None:
        self.cli_module._SINGLE_INSTANCE_MUTEX = self._orig_mutex

    def test_first_acquisition_succeeds(self) -> None:
        mock_kernel32 = MagicMock()
        mock_kernel32.CreateMutexW.return_value = 12345
        with patch("sys.platform", "win32"), \
             patch("ctypes.WinDLL", return_value=mock_kernel32), \
             patch("ctypes.get_last_error", return_value=0):
            result = self.cli_module._acquire_single_instance_mutex()
        self.assertEqual(result, self.SingleInstanceResult.ACQUIRED)
        self.assertEqual(self.cli_module._SINGLE_INSTANCE_MUTEX, 12345)

    def test_second_acquisition_rejected_as_already_running(self) -> None:
        """ERROR_ALREADY_EXISTS (183) must reject the second acquisition as ALREADY_RUNNING, not CHECK_FAILED."""
        mock_kernel32 = MagicMock()
        mock_kernel32.CreateMutexW.return_value = 6789
        with patch("sys.platform", "win32"), \
             patch("ctypes.WinDLL", return_value=mock_kernel32), \
             patch("ctypes.get_last_error", return_value=183), \
             patch("sys.stdout", new_callable=io.StringIO):
            result = self.cli_module._acquire_single_instance_mutex()
        self.assertEqual(result, self.SingleInstanceResult.ALREADY_RUNNING)
        # The duplicate handle Win32 still returns must be closed, not leaked.
        mock_kernel32.CloseHandle.assert_called_once_with(6789)

    def test_already_running_result_exits_zero_and_never_constructs_jarvisapp(self) -> None:
        with patch("jarvis.cli._acquire_single_instance_mutex", return_value=self.SingleInstanceResult.ALREADY_RUNNING), \
             patch("jarvis.core.app.JarvisApp") as mock_app_cls:
            exit_code = main(["run", "--headless"])
        self.assertEqual(exit_code, 0)
        mock_app_cls.assert_not_called()

    def test_check_failed_result_exits_nonzero_and_never_constructs_jarvisapp(self) -> None:
        """
        Pre-commit review correction: CHECK_FAILED must be distinguishable
        from ALREADY_RUNNING by a script/automation caller -- it exits
        non-zero (a real failure), never 0, and must never start JarvisApp.
        """
        with patch("jarvis.cli._acquire_single_instance_mutex", return_value=self.SingleInstanceResult.CHECK_FAILED), \
             patch("jarvis.core.app.JarvisApp") as mock_app_cls:
            exit_code = main(["run", "--headless"])
        self.assertNotEqual(exit_code, 0)
        mock_app_cls.assert_not_called()

    def test_lock_releases_cleanly(self) -> None:
        mock_kernel32 = MagicMock()
        with patch("sys.platform", "win32"), patch("ctypes.WinDLL", return_value=mock_kernel32):
            self.cli_module._SINGLE_INSTANCE_MUTEX = 42
            self.cli_module._release_single_instance_mutex()
        mock_kernel32.CloseHandle.assert_called_once_with(42)
        self.assertIsNone(self.cli_module._SINGLE_INSTANCE_MUTEX)

    def test_release_with_no_prior_acquisition_is_a_safe_no_op(self) -> None:
        self.cli_module._SINGLE_INSTANCE_MUTEX = None
        self.cli_module._release_single_instance_mutex()  # must not raise
        self.assertIsNone(self.cli_module._SINGLE_INSTANCE_MUTEX)

    def test_unexpected_ctypes_failure_fails_closed(self) -> None:
        """
        Pre-commit review correction: an inability to prove single-instance
        exclusivity must BLOCK startup, not silently allow it. A Win32 API
        exception (WinDLL binding failure, CreateMutexW raising, etc.) now
        fails CLOSED (CHECK_FAILED) rather than the previous fail-open
        tradeoff.
        """
        with patch("sys.platform", "win32"), \
             patch("ctypes.WinDLL", side_effect=OSError("simulated ctypes failure")), \
             patch("sys.stdout", new_callable=io.StringIO):
            result = self.cli_module._acquire_single_instance_mutex()
        self.assertEqual(result, self.SingleInstanceResult.CHECK_FAILED)
        self.assertIsNone(self.cli_module._SINGLE_INSTANCE_MUTEX)

    def test_create_mutex_raising_fails_closed(self) -> None:
        """CreateMutexW itself raising (not just WinDLL binding) must also fail closed."""
        mock_kernel32 = MagicMock()
        mock_kernel32.CreateMutexW.side_effect = OSError("simulated CreateMutexW failure")
        with patch("sys.platform", "win32"), \
             patch("ctypes.WinDLL", return_value=mock_kernel32), \
             patch("sys.stdout", new_callable=io.StringIO):
            result = self.cli_module._acquire_single_instance_mutex()
        self.assertEqual(result, self.SingleInstanceResult.CHECK_FAILED)
        self.assertIsNone(self.cli_module._SINGLE_INSTANCE_MUTEX)

    def test_null_handle_fails_closed(self) -> None:
        """
        CreateMutexW returning a NULL/0 handle for a reason OTHER than
        ERROR_ALREADY_EXISTS means exclusivity cannot be proven -- must
        BLOCK startup (CHECK_FAILED), never silently continue as if
        acquisition succeeded.
        """
        mock_kernel32 = MagicMock()
        mock_kernel32.CreateMutexW.return_value = None
        with patch("sys.platform", "win32"), \
             patch("ctypes.WinDLL", return_value=mock_kernel32), \
             patch("ctypes.get_last_error", return_value=5), \
             patch("sys.stdout", new_callable=io.StringIO):
            result = self.cli_module._acquire_single_instance_mutex()
        self.assertEqual(result, self.SingleInstanceResult.CHECK_FAILED)
        self.assertIsNone(self.cli_module._SINGLE_INSTANCE_MUTEX)
        # A NULL handle has nothing to close.
        mock_kernel32.CloseHandle.assert_not_called()

    def test_malformed_handle_fails_closed(self) -> None:
        """A returned handle that isn't a sane integer must not be trusted as a proven acquisition."""
        mock_kernel32 = MagicMock()
        mock_kernel32.CreateMutexW.return_value = object()  # not int()-convertible
        with patch("sys.platform", "win32"), \
             patch("ctypes.WinDLL", return_value=mock_kernel32), \
             patch("ctypes.get_last_error", return_value=0), \
             patch("sys.stdout", new_callable=io.StringIO):
            result = self.cli_module._acquire_single_instance_mutex()
        self.assertEqual(result, self.SingleInstanceResult.CHECK_FAILED)
        self.assertIsNone(self.cli_module._SINGLE_INSTANCE_MUTEX)

    def test_stale_last_error_before_call_does_not_misclassify_fresh_success(self) -> None:
        """
        ctypes.set_last_error(0) must run immediately before CreateMutexW so
        a genuinely fresh, successful creation is never misclassified as
        ERROR_ALREADY_EXISTS due to a stale value left over from an
        unrelated earlier ctypes call. Simulated here by making
        get_last_error() return ERROR_ALREADY_EXISTS (183) ONLY if
        set_last_error(0) was never called -- i.e. this test fails if the
        production code forgets to clear it first.
        """
        mock_kernel32 = MagicMock()
        mock_kernel32.CreateMutexW.return_value = 999
        state = {"cleared": False}

        def _fake_set_last_error(value):
            if value == 0:
                state["cleared"] = True

        def _fake_get_last_error():
            return 0 if state["cleared"] else 183

        with patch("sys.platform", "win32"), \
             patch("ctypes.WinDLL", return_value=mock_kernel32), \
             patch("ctypes.set_last_error", side_effect=_fake_set_last_error), \
             patch("ctypes.get_last_error", side_effect=_fake_get_last_error):
            result = self.cli_module._acquire_single_instance_mutex()
        self.assertEqual(result, self.SingleInstanceResult.ACQUIRED)

    def test_non_windows_platform_always_succeeds(self) -> None:
        with patch("sys.platform", "linux"):
            result = self.cli_module._acquire_single_instance_mutex()
        self.assertEqual(result, self.SingleInstanceResult.ACQUIRED)


if __name__ == "__main__":
    unittest.main()

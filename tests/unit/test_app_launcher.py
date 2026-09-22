"""Launcher evidence contracts; only native OS/process calls are replaced."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from jarvis.automation import app_launcher
from jarvis.automation.app_catalog import InstalledApp


@pytest.fixture(autouse=True)
def no_native_window_properties(monkeypatch):
    monkeypatch.setattr(app_launcher, "window_app_id", lambda hwnd: "", raising=False)


def test_host_window_requires_identity_of_its_child_process(monkeypatch):
    platform = MagicMock()
    platform.list_windows.return_value = [SimpleNamespace(hwnd=42, pid=10)]
    monkeypatch.setattr(app_launcher, "window_child_pids", lambda hwnd: (20,))
    monkeypatch.setattr(app_launcher, "process_identity", lambda pid: ("", "Vendor.Calculator!App" if pid == 20 else ""))
    proof = app_launcher.WindowsWindowProbe(platform).find(InstalledApp("Calculator", "Vendor.Calculator!App", "app_id"))
    assert proof["pid"] == 20
    assert proof["hwnd"] == 42
    assert proof["verification"] == "window_app_id"


def test_unrelated_host_child_is_never_proof(monkeypatch):
    platform = MagicMock()
    platform.list_windows.return_value = [SimpleNamespace(hwnd=42, pid=10)]
    monkeypatch.setattr(app_launcher, "window_child_pids", lambda hwnd: (20,))
    monkeypatch.setattr(app_launcher, "process_identity", lambda pid: ("", "Other!App"))
    assert app_launcher.WindowsWindowProbe(platform).find(InstalledApp("Calculator", "Vendor.Calculator!App", "app_id")) is None


def test_same_executable_basename_at_different_location_is_not_proof(monkeypatch, tmp_path):
    platform = MagicMock()
    platform.list_windows.return_value = [SimpleNamespace(hwnd=42, pid=10)]
    monkeypatch.setattr(app_launcher, "window_child_pids", lambda hwnd: ())
    monkeypatch.setattr(app_launcher, "process_identity", lambda pid: (str(tmp_path / "other" / "Editor.exe"), ""))
    assert app_launcher.WindowsWindowProbe(platform).find(InstalledApp("Editor", str(tmp_path / "Editor.exe"), "exe")) is None


def test_exact_executable_path_verifies_desktop_window(monkeypatch, tmp_path):
    path = str(tmp_path / "Editor.exe")
    platform = MagicMock()
    platform.list_windows.return_value = [SimpleNamespace(hwnd=42, pid=10)]
    monkeypatch.setattr(app_launcher, "window_child_pids", lambda hwnd: ())
    monkeypatch.setattr(app_launcher, "process_identity", lambda pid: (path, ""))
    assert app_launcher.WindowsWindowProbe(platform).find(InstalledApp("Editor", path, "exe"))["verification"] == "window_executable"


def test_already_open_application_is_not_spawned_again(monkeypatch):
    probe = MagicMock()
    probe.find.return_value = {"pid": 20, "hwnd": 42, "verification": "window_app_id"}
    launch = MagicMock()
    monkeypatch.setattr("os.startfile", launch, raising=False)
    result = app_launcher.WindowsApplicationLauncher(probe=probe).open(InstalledApp("Calculator", "Vendor!App", "app_id"))
    assert result["success"] is True
    assert result["already_running"] is True
    launch.assert_not_called()


def test_launch_waits_for_verified_window(monkeypatch):
    probe = MagicMock()
    probe.find.side_effect = [None, None, {"pid": 20, "hwnd": 42, "verification": "window_app_id"}]
    launched = []
    monkeypatch.setattr("os.startfile", launched.append, raising=False)
    result = app_launcher.WindowsApplicationLauncher(probe=probe, timeout=0.5, interval=0.001).open(InstalledApp("Calculator", "Vendor!App", "app_id"))
    assert launched == [r"shell:AppsFolder\Vendor!App"]
    assert result["success"] is True
    assert result["already_running"] is False


def test_acknowledgement_without_window_times_out(monkeypatch):
    """Fix 2 (2026-09-22): HWND timeout → success=True because os.startfile() was called.
    The app IS launching; 'launched' status means request dispatched but HWND unconfirmed.
    """
    probe = MagicMock()
    probe.find.return_value = None
    monkeypatch.setattr("os.startfile", lambda target: None, raising=False)
    result = app_launcher.WindowsApplicationLauncher(probe=probe, timeout=0).open(InstalledApp("Calculator", "Vendor!App", "app_id"))
    # Fix 2: launch dispatched → success=True; HWND unconfirmed → error_code for diagnostics
    assert result["success"] is True
    assert result["error_code"] == "APP_LAUNCH_UNVERIFIED"
    assert result["status"] == "launched"


def test_launch_os_error_is_reported(monkeypatch):
    probe = MagicMock()
    probe.find.return_value = None
    monkeypatch.setattr("os.startfile", MagicMock(side_effect=OSError("denied")), raising=False)
    result = app_launcher.WindowsApplicationLauncher(probe=probe).open(InstalledApp("Calculator", "Vendor!App", "app_id"))
    assert result["success"] is False
    assert result["error_code"] == "APP_LAUNCH_FAILED"


def test_missing_executable_is_not_spawned(monkeypatch, tmp_path):
    probe = MagicMock()
    probe.find.return_value = None
    launch = MagicMock()
    monkeypatch.setattr("subprocess.Popen", launch)
    result = app_launcher.WindowsApplicationLauncher(probe=probe).open(InstalledApp("Editor", str(tmp_path / "absent.exe"), "exe"))
    assert result["error_code"] == "APP_NOT_FOUND"
    launch.assert_not_called()


def test_controller_reports_success_for_verified_store_window(monkeypatch):
    from jarvis.automation.app_catalog import ApplicationCatalog
    from jarvis.automation.control import ComputerController
    from jarvis.core.runaway_guard import launch_dedupe_guard
    launch_dedupe_guard.reset()
    controller = ComputerController()
    controller.app_catalog = ApplicationCatalog(provider=lambda: [InstalledApp("Example", "Vendor!App", "app_id")])
    probe = MagicMock()
    probe.find.return_value = {"pid": 20, "hwnd": 42, "verification": "window_app_id"}
    controller.app_launcher = app_launcher.WindowsApplicationLauncher(probe=probe)
    monkeypatch.setattr("os.startfile", lambda target: None, raising=False)
    result = controller.open_installed_app("Example")
    assert result["success"] is True
    assert result["already_running"] is True
    launch_dedupe_guard.reset()


def test_dispatcher_retains_window_verification_timeout():
    from jarvis.core.app import JarvisApp
    from jarvis.core.dispatcher import ActionDispatcher
    app = object.__new__(JarvisApp)
    app.computer_controller = MagicMock()
    app.computer_controller.open_installed_app.return_value = {
        "success": False, "status": "timeout", "error_code": "APP_LAUNCH_UNVERIFIED", "message": "No window evidence"}
    dispatcher = ActionDispatcher()
    dispatcher.register_action("app_open", app._handle_app_open)
    result = dispatcher.dispatch_action("app_open", {"app_name": "Example", "installed_only": True})
    assert result.success is False
    assert result.status.value.upper() == "TIMEOUT"
    assert result.error_code == "APP_LAUNCH_UNVERIFIED"


def test_known_alias_resolves_catalog_executable_name(monkeypatch):
    from jarvis.automation.app_catalog import ApplicationCatalog
    from jarvis.automation.control import ComputerController
    from jarvis.core.runaway_guard import launch_dedupe_guard
    launch_dedupe_guard.reset()
    controller = ComputerController()
    controller.app_catalog = ApplicationCatalog(provider=lambda: [InstalledApp("code", "Vendor.Code!App", "app_id")])
    probe = MagicMock()
    probe.find.return_value = {"pid": 20, "hwnd": 42, "verification": "window_app_id"}
    controller.app_launcher = app_launcher.WindowsApplicationLauncher(probe=probe)
    assert controller.open_installed_app("vscode")["success"] is True
    launch_dedupe_guard.reset()


def test_suppressed_legacy_launch_remains_failure_at_dispatcher():
    from jarvis.core.app import JarvisApp
    from jarvis.core.dispatcher import ActionDispatcher
    app = object.__new__(JarvisApp)
    app.computer_controller = MagicMock()
    app.computer_controller.open_app.return_value = {
        "success": False, "status": "suppressed", "error_code": "LAUNCH_RATE_LIMITED", "message": "Repeated request"}
    dispatcher = ActionDispatcher()
    dispatcher.register_action("app_open", app._handle_app_open)
    result = dispatcher.dispatch_action("app_open", {"app_name": "settings"})
    assert result.success is False
    assert result.error_code == "LAUNCH_RATE_LIMITED"


def test_store_identity_cannot_fall_back_to_shared_executable(monkeypatch, tmp_path):
    path = str(tmp_path / "Shared.exe")
    app = InstalledApp("Tool A", "Vendor!A", "app_id", executable=path, app_id="Vendor!A")
    platform = MagicMock()
    platform.list_windows.return_value = [SimpleNamespace(hwnd=42, pid=10)]
    monkeypatch.setattr(app_launcher, "window_child_pids", lambda hwnd: ())
    monkeypatch.setattr(app_launcher, "process_identity", lambda pid: (path, ""))
    assert app_launcher.WindowsWindowProbe(platform).find(app) is None


def test_minimized_window_is_found_without_large_window_filter(monkeypatch, tmp_path):
    path = str(tmp_path / "Editor.exe")
    def list_windows(visible_only=True, min_size=(80, 80)):
        return [SimpleNamespace(hwnd=42, pid=10)] if min_size[1] <= 28 else []
    platform = SimpleNamespace(list_windows=list_windows)
    monkeypatch.setattr(app_launcher, "window_child_pids", lambda hwnd: ())
    monkeypatch.setattr(app_launcher, "process_identity", lambda pid: (path, ""))
    assert app_launcher.WindowsWindowProbe(platform).find(InstalledApp("Editor", path, "exe")) is not None


def test_detached_minimized_store_content_uses_exact_window_identity(monkeypatch):
    platform = MagicMock()
    platform.list_windows.return_value = [SimpleNamespace(hwnd=42, pid=10)]
    monkeypatch.setattr(app_launcher, "window_child_pids", lambda hwnd: ())
    monkeypatch.setattr(app_launcher, "process_identity", lambda pid: ("host.exe", ""))
    monkeypatch.setattr(app_launcher, "window_app_id", lambda hwnd: "Vendor.Calculator!App", raising=False)
    app = InstalledApp("Calculator", "Vendor.Calculator!App", "app_id")
    proof = app_launcher.WindowsWindowProbe(platform).find(app)
    assert proof is not None
    assert proof["hwnd"] == 42
    assert proof["verification"] == "window_app_id_property"


def test_other_window_identity_does_not_verify_detached_store_content(monkeypatch):
    platform = MagicMock()
    platform.list_windows.return_value = [SimpleNamespace(hwnd=42, pid=10)]
    monkeypatch.setattr(app_launcher, "window_child_pids", lambda hwnd: ())
    monkeypatch.setattr(app_launcher, "process_identity", lambda pid: ("host.exe", ""))
    monkeypatch.setattr(app_launcher, "window_app_id", lambda hwnd: "Vendor.Other!App", raising=False)
    app = InstalledApp("Calculator", "Vendor.Calculator!App", "app_id")
    assert app_launcher.WindowsWindowProbe(platform).find(app) is None


def test_user_requested_executable_is_not_forced_into_hidden_console(monkeypatch):
    probe = MagicMock()
    probe.find.return_value = None
    launch = MagicMock()
    monkeypatch.setattr(app_launcher.os.path, "isfile", lambda path: True)
    monkeypatch.setattr(app_launcher.subprocess, "Popen", launch)
    app_launcher.WindowsApplicationLauncher(probe=probe, timeout=0).open(InstalledApp("Editor", "editor.exe", "exe"))
    options = launch.call_args.kwargs
    assert "stdout" not in options and "stderr" not in options
    assert options["creationflags"] == getattr(app_launcher.subprocess, "CREATE_NEW_CONSOLE", 0)
    if app_launcher.sys.platform == "win32":
        assert options["startupinfo"].wShowWindow == 1
        assert options["startupinfo"].dwFlags & app_launcher.subprocess.STARTF_USESHOWWINDOW


def test_shared_desktop_executable_does_not_prove_specific_shortcut(monkeypatch, tmp_path):
    path = str(tmp_path / "browser.exe")
    app = SimpleNamespace(name="Profile A", target="Vendor.ProfileA", kind="app_id",
                          executable=path, app_id="Vendor.ProfileA", executable_shared=True)
    platform = MagicMock()
    platform.list_windows.return_value = [SimpleNamespace(hwnd=42, pid=10)]
    monkeypatch.setattr(app_launcher, "window_child_pids", lambda hwnd: ())
    monkeypatch.setattr(app_launcher, "process_identity", lambda pid: (path, ""))
    assert app_launcher.WindowsWindowProbe(platform).find(app) is None


def test_live_probe_requires_opt_in_before_importing_app():
    import subprocess
    import sys
    from pathlib import Path
    script = Path(__file__).resolve().parents[2] / "scripts" / "verify_installed_apps_live.py"
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert "--run is required" in result.stderr
    assert "Evidence:" not in result.stdout


@pytest.mark.parametrize("extra", [{}, {"installed_only": False}])
def test_catalog_miss_falls_back_to_legacy_open_app(extra):
    """Fix 1 (2026-09-22): APP_NOT_FOUND in catalog → fallback to open_app.
    Previously this test asserted catalog was authoritative. Now fallback is intended behavior
    so apps not in Windows Registry (Spotify, Firefox, etc.) still open via APP_MAP/PATH.
    """
    from jarvis.core.app import JarvisApp
    app = object.__new__(JarvisApp)
    app.computer_controller = MagicMock()
    app.computer_controller.open_app.return_value = {"success": True, "message": "opened via legacy path"}
    app.computer_controller.open_installed_app.return_value = {"success": False, "error_code": "APP_NOT_FOUND"}
    result = app._handle_app_open(app_name="Example", **extra)
    # Fix 1: catalog miss → fallback to open_app → returns open_app success
    assert result["success"] is True
    app.computer_controller.open_installed_app.assert_called_once()
    app.computer_controller.open_app.assert_called_once_with("Example")


def test_settings_uri_always_uses_specialized_route():
    """Fix 3 (2026-09-22): ms-settings: always routes to open_app, never to catalog.
    The installed_only override has been removed — settings URIs are always specialized.
    Catalog lookup for shell URIs is semantically wrong (registry has no ms-settings entries).
    """
    from jarvis.core.app import JarvisApp
    app = object.__new__(JarvisApp)
    app.computer_controller = MagicMock()
    app.computer_controller.open_app.return_value = {"success": True}
    app.computer_controller.open_installed_app.return_value = {"success": False, "error_code": "APP_NOT_FOUND"}
    result = app._handle_app_open(app="ms-settings:")
    assert result["success"] is True
    app.computer_controller.open_installed_app.assert_not_called()
    app.computer_controller.open_app.assert_called_once_with("ms-settings:")

"""Installed-app catalog behavior; discovery/launch OS boundaries are isolated."""
import pytest

from jarvis.automation import app_catalog


def test_exact_casefold_lookup_never_substring_launches():
    entry = app_catalog.InstalledApp("Ví dụ Editor", "Vendor.Editor!App", "app_id")
    catalog = app_catalog.ApplicationCatalog(provider=lambda: [entry])
    assert catalog.resolve("  VÍ DỤ   editor ") == (entry,)
    assert catalog.resolve("Editor") == ()


def test_duplicate_target_dedupes_but_versions_are_ambiguous():
    first = app_catalog.InstalledApp("Editor", "Vendor.Editor!One", "app_id")
    second = app_catalog.InstalledApp("Editor", "Vendor.Editor!Two", "app_id")
    catalog = app_catalog.ApplicationCatalog(provider=lambda: [first, first, second])
    assert catalog.resolve("Editor") == (first, second)


@pytest.mark.parametrize("name", ["Uninstall Editor", "Editor Updater", "Gỡ cài đặt Editor"])
def test_maintenance_entries_not_launchable_by_catalog(name):
    catalog = app_catalog.ApplicationCatalog(provider=lambda: [app_catalog.InstalledApp(name, "X!Y", "app_id")])
    assert catalog.resolve(name) == ()


def test_provider_failure_is_visible_and_does_not_use_stale_inventory():
    def broken():
        raise OSError("denied")
    catalog = app_catalog.ApplicationCatalog(provider=broken)
    assert catalog.resolve("Editor") == ()
    assert catalog.errors


def test_transient_discovery_failure_recovers_without_waiting_full_ttl():
    attempts = 0
    entry = app_catalog.InstalledApp("RecoveredApp", "C:\\App.exe", "exe")

    def flaky_provider():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("Transient WMI lock")
        return [entry]

    catalog = app_catalog.ApplicationCatalog(provider=flaky_provider, ttl=300)
    # Attempt 1: fails due to transient error
    assert catalog.resolve("RecoveredApp") == ()
    assert catalog.errors == ("OSError",)

    # Attempt 2: must recover on next resolve rather than staying locked for 300s
    results = catalog.resolve("RecoveredApp")
    assert results == (entry,)
    assert catalog.errors == ()


def test_legitimate_empty_scan_is_cached_for_ttl():
    calls = []
    def empty_provider():
        calls.append(1)
        return []

    catalog = app_catalog.ApplicationCatalog(provider=empty_provider, ttl=300)
    assert catalog.resolve("AnyApp") == ()
    assert catalog.errors == ()
    assert len(calls) == 1

    # Second call within TTL must use cached empty scan (no re-invoking provider)
    assert catalog.resolve("AnyApp") == ()
    assert len(calls) == 1




def test_cache_prevents_discovery_for_every_command():
    calls = []
    def provider():
        calls.append(1)
        return [app_catalog.InstalledApp("Editor", "X!Y", "app_id")]
    catalog = app_catalog.ApplicationCatalog(provider=provider)
    catalog.resolve("Editor")
    catalog.resolve("Missing")
    assert len(calls) == 1
    catalog.refresh()
    assert len(calls) == 2


def test_explicit_installed_app_command_routes_without_fixed_alias():
    from jarvis.llm.router import LLMIntentRouter
    intent = LLMIntentRouter(llm_client=None).parse_intent("mở ứng dụng Example Editor")
    assert intent.action_name == "app_open"
    assert intent.parameters == {"app_name": "Example Editor", "installed_only": True}


def test_ambiguous_installed_app_is_not_launched():
    from jarvis.automation.control import ComputerController
    catalog = app_catalog.ApplicationCatalog(provider=lambda: [
        app_catalog.InstalledApp("Editor", "X!One", "app_id"),
        app_catalog.InstalledApp("Editor", "X!Two", "app_id"),
    ])
    controller = ComputerController()
    controller.app_catalog = catalog
    result = controller.open_installed_app("Editor")
    assert result["success"] is False
    assert result["error_code"] == "APP_AMBIGUOUS"
    assert len(result["candidates"]) == 2


def test_discovery_failure_distinct_from_app_missing():
    from jarvis.automation.control import ComputerController
    def unavailable():
        raise OSError("denied")
    controller = ComputerController()
    controller.app_catalog = app_catalog.ApplicationCatalog(provider=unavailable)
    assert controller.open_installed_app("Example")["error_code"] == "APP_DISCOVERY_UNAVAILABLE"


def test_catalog_shares_launch_cooldown_with_existing_app_path():
    from jarvis.automation.control import ComputerController
    from jarvis.core.runaway_guard import canonical_app_key, launch_dedupe_guard
    launch_dedupe_guard.reset()
    controller = ComputerController()
    controller.app_catalog = app_catalog.ApplicationCatalog(provider=lambda: [
        app_catalog.InstalledApp("Cursor", "Vendor.Cursor!App", "app_id")])
    assert launch_dedupe_guard.should_allow("app_launch", canonical_app_key("cursor"))
    assert controller.open_installed_app("Cursor")["error_code"] == "LAUNCH_RATE_LIMITED"
    launch_dedupe_guard.reset()


def test_store_launch_acknowledgement_is_not_verified_success(monkeypatch):
    """APP_LAUNCH_UNVERIFIED: launch WAS dispatched but HWND unconfirmed within timeout.

    Fix 2 (2026-09-22): success=True because os.startfile() was called and the
    app IS opening — reporting success=False misleads the user into thinking the
    app failed to open. error_code=APP_LAUNCH_UNVERIFIED is still set for diagnostics.
    """
    from jarvis.automation.control import ComputerController
    from jarvis.core.runaway_guard import launch_dedupe_guard
    launch_dedupe_guard.reset()
    controller = ComputerController()
    from unittest.mock import MagicMock

    from jarvis.automation.app_launcher import WindowsApplicationLauncher
    probe = MagicMock()
    probe.find.return_value = None
    controller.app_launcher = WindowsApplicationLauncher(probe=probe, timeout=0)
    controller.app_catalog = app_catalog.ApplicationCatalog(provider=lambda: [
        app_catalog.InstalledApp("Editor", "X!One", "app_id")])
    launched = []
    monkeypatch.setattr("os.startfile", launched.append, raising=False)
    result = controller.open_installed_app("Editor")
    # Launch was dispatched to the OS
    assert launched == [r"shell:AppsFolder\X!One"]
    # TRUTHFUL-LAUNCH-FIX1: HWND timeout is an unverified failure (success=False).
    assert result["success"] is False
    assert result["status"] == "timeout"
    assert result["error_code"] == "APP_LAUNCH_UNVERIFIED"
    launch_dedupe_guard.reset()


@pytest.mark.parametrize("window_pid,verified", [(123, True), (999, False)])
def test_executable_requires_matching_visible_window(monkeypatch, tmp_path, window_pid, verified):
    """Test exe launch verification via HWND + process identity.

    window_pid=123 → process_identity matches executable → verified success (window_executable).
    window_pid=999 → process_identity mismatch → unverified: returns success=False with APP_LAUNCH_UNVERIFIED.
    """
    import subprocess
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from jarvis.automation.control import ComputerController
    from jarvis.core.runaway_guard import launch_dedupe_guard
    launch_dedupe_guard.reset()
    executable = tmp_path / "Example.exe"
    executable.touch()
    platform = MagicMock()
    platform.list_windows.return_value = [SimpleNamespace(pid=window_pid, hwnd=42)]
    monkeypatch.setattr("jarvis.automation.app_launcher.window_child_pids", lambda hwnd: ())
    monkeypatch.setattr("jarvis.automation.app_launcher.process_identity", lambda pid: (str(executable) if pid == 123 else str(tmp_path / "Other.exe"), ""))
    controller = ComputerController(win32=platform)
    from jarvis.automation.app_launcher import WindowsApplicationLauncher, WindowsWindowProbe
    controller.app_launcher = WindowsApplicationLauncher(probe=WindowsWindowProbe(platform), timeout=0)
    controller.app_catalog = app_catalog.ApplicationCatalog(provider=lambda: [
        app_catalog.InstalledApp("Example", str(executable), "exe")])
    process = MagicMock(pid=123)
    process.wait.side_effect = subprocess.TimeoutExpired("Example", 0.5)
    monkeypatch.setattr("subprocess.Popen", lambda argv, **kwargs: process)
    result = controller.open_installed_app("Example")
    if verified:
        # window_pid=123 matches executable PID → confirmed success via HWND
        assert result["success"] is True
        assert result["verification"] == "window_executable"
    else:
        # window_pid=999 doesn't match our exe — HWND unconfirmed within timeout → success=False
        assert result["success"] is False
        assert result["error_code"] == "APP_LAUNCH_UNVERIFIED"
        assert result["status"] == "timeout"
    launch_dedupe_guard.reset()


def test_transient_provider_runtime_error_retries_immediately():
    """Generic Exception from provider must set errors, clear _updated, and retry on next resolve."""
    attempts = 0
    entry = app_catalog.InstalledApp("TestApp", "C:\\TestApp.exe", "exe")

    def failing_provider():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("Provider failed transiently")
        return [entry]

    catalog = app_catalog.ApplicationCatalog(provider=failing_provider, ttl=300)
    assert catalog.resolve("TestApp") == ()
    assert catalog.errors == ("RuntimeError",)

    # Next resolve must retry without waiting for 300s TTL
    results = catalog.resolve("TestApp")
    assert results == (entry,)
    assert catalog.errors == ()


def test_concurrent_catalog_refresh_and_resolve_thread_safety():
    """Concurrent resolve and refresh calls must be thread-safe."""
    import threading

    entry = app_catalog.InstalledApp("ThreadApp", "C:\\ThreadApp.exe", "exe")
    catalog = app_catalog.ApplicationCatalog(provider=lambda: [entry], ttl=300)

    def worker():
        for _ in range(20):
            catalog.resolve("ThreadApp")
            catalog.refresh()

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert catalog.resolve("ThreadApp") == (entry,)
    assert catalog.errors == ()

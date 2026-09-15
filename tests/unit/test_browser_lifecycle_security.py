"""Lifecycle verification and secret-safe logging contracts for browser control."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import jarvis.browser.session as session_module
from jarvis.browser.cdp_controller import BrowserCDPController
from jarvis.browser.driver import (
    CDPBrowserDriver,
    MockBrowserDriver,
    PlaywrightBrowserDriver,
)
from jarvis.browser.models import BrowserResultStatus
from jarvis.browser.session import BrowserSessionManager


def _attach_playwright_resources(driver: PlaywrightBrowserDriver) -> None:
    """Give a driver observable stand-ins for each external Playwright handle."""

    driver._page = MagicMock()
    driver._context = MagicMock()
    driver._browser = MagicMock()
    driver._playwright = MagicMock()
    driver._is_running = True
    driver._has_started = True


def test_playwright_close_returns_true_when_every_resource_is_released() -> None:
    driver = PlaywrightBrowserDriver()
    _attach_playwright_resources(driver)

    assert driver.close() is True
    assert driver.is_running() is False


def test_playwright_close_returns_false_when_cleanup_cannot_be_verified(
    caplog,
) -> None:
    secret = "pw-close-token=never-log-this"
    driver = PlaywrightBrowserDriver()
    _attach_playwright_resources(driver)
    driver._page.close.side_effect = RuntimeError(secret)
    caplog.set_level(logging.DEBUG, logger="jarvis.browser.driver")

    assert driver.close() is False
    assert driver.is_running() is False
    assert secret not in caplog.text


def test_cdp_close_returns_false_when_attached_browser_cleanup_fails(caplog) -> None:
    secret = "cdp-authorization=never-log-this"
    driver = CDPBrowserDriver()
    _attach_playwright_resources(driver)
    driver._browser.close.side_effect = RuntimeError(secret)
    caplog.set_level(logging.DEBUG, logger="jarvis.browser.driver")

    assert driver.close() is False
    assert driver.is_running() is False
    assert secret not in caplog.text


def test_controller_close_honors_false_driver_cleanup_report(monkeypatch) -> None:
    controller = BrowserCDPController(is_mock=True)
    assert controller.launch() is True

    def fail_closed(driver: MockBrowserDriver) -> bool:
        driver._is_running = False
        return False

    monkeypatch.setattr(MockBrowserDriver, "close", fail_closed)

    assert controller.close() is False
    assert controller.last_status is BrowserResultStatus.ERROR
    assert controller.last_error_code == "BROWSER_CLOSE_FAILED"


def test_legacy_controller_launch_log_does_not_echo_exception_secret(
    monkeypatch,
    caplog,
) -> None:
    secret = "proxy-password=never-log-this"
    controller = BrowserCDPController(is_mock=False)
    caplog.set_level(logging.DEBUG, logger="jarvis.browser.cdp")

    def raise_secret(driver: PlaywrightBrowserDriver) -> bool:
        raise RuntimeError(secret)

    monkeypatch.setattr(PlaywrightBrowserDriver, "launch", raise_secret)

    assert controller.launch() is False
    assert secret not in caplog.text


def test_legacy_controller_close_log_does_not_echo_exception_secret(
    monkeypatch,
    caplog,
) -> None:
    secret = "cookie-session=never-log-this"
    controller = BrowserCDPController(is_mock=True)
    assert controller.launch() is True
    caplog.set_level(logging.DEBUG, logger="jarvis.browser.cdp")

    def raise_secret(driver: MockBrowserDriver) -> bool:
        raise RuntimeError(secret)

    monkeypatch.setattr(MockBrowserDriver, "close", raise_secret)

    assert controller.close() is False
    assert secret not in caplog.text


def test_session_json_write_log_does_not_echo_exception_secret(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    secret = "cookie-value=never-log-this"
    manager = BrowserSessionManager(
        storage_dir=str(tmp_path / "sessions"),
        db_path="",
    )
    caplog.set_level(logging.DEBUG, logger="jarvis.browser.session")

    def raise_secret(*args, **kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(Path, "write_text", raise_secret)

    assert manager.save_session("example.test", []) is False
    assert secret not in caplog.text


def test_session_sqlite_initialization_log_does_not_echo_exception_secret(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    secret = "sqlite-password=never-log-this"
    caplog.set_level(logging.DEBUG, logger="jarvis.browser.session")

    def raise_secret(*args, **kwargs):
        raise sqlite3.OperationalError(secret)

    monkeypatch.setattr(session_module.sqlite3, "connect", raise_secret)

    manager = BrowserSessionManager(
        storage_dir=str(tmp_path / "sessions"),
        db_path=str(tmp_path / "sessions.db"),
    )

    assert manager.list_sessions() == []
    assert secret not in caplog.text

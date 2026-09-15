"""Truthful health-check reporting for the selected browser tier."""

from __future__ import annotations

from unittest.mock import patch

from jarvis.browser.models import BrowserDriverType
from jarvis.cli import _browser_health_exit_code, _browser_health_line


def test_browser_health_reports_http_fallback_as_limited() -> None:
    with patch(
        "jarvis.browser.driver.DriverFactory.detect_best_driver",
        return_value=BrowserDriverType.HTTP_SCRAPER,
    ):
        line = _browser_health_line()

    assert "LIMITED" in line
    assert "http_scraper" in line
    assert "READY" not in line


def test_browser_health_reports_real_interactive_driver_as_ready() -> None:
    with patch(
        "jarvis.browser.driver.DriverFactory.detect_best_driver",
        return_value=BrowserDriverType.PLAYWRIGHT,
    ):
        line = _browser_health_line()

    assert "READY" in line
    assert "playwright" in line


def test_browser_health_exit_code_distinguishes_ready_limited_and_error() -> None:
    assert _browser_health_exit_code(
        "[+] Browser Automation Agent: READY (Driver=playwright)"
    ) == 0
    assert _browser_health_exit_code(
        "[!] Browser Automation Agent: LIMITED (Driver=http_scraper)"
    ) == 2
    assert _browser_health_exit_code(None) == 1

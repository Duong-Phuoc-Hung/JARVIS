"""
tests/unit/test_browser_control.py
=====================================
Unit tests for Browser CDP Controller (mock mode — no real browser).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jarvis.browser.cdp_controller import BrowserCDPController, BrowserConfig, PageInfo
from jarvis.browser.models import BrowserDriverType, BrowserResultStatus
from jarvis.skills import browser_control as browser_skill


@pytest.fixture
def browser():
    ctrl = BrowserCDPController(is_mock=True)
    yield ctrl
    ctrl.close()


@pytest.fixture
def unavailable_browser():
    """Real-mode controller with its process boundary forced unavailable."""
    with patch(
        "jarvis.browser.cdp_controller.PlaywrightBrowserDriver.launch",
        return_value=False,
    ):
        yield BrowserCDPController(is_mock=False)


class TestAvailability:
    def test_mock_is_available(self, browser):
        assert browser.is_available() is True

    def test_launch_mock_returns_true(self, browser):
        assert browser.launch() is True

    def test_close_no_exception(self, browser):
        browser.launch()
        assert browser.close() is True

    def test_close_driver_exception_fails_closed(self, browser):
        assert browser.launch() is True
        with patch(
            "jarvis.browser.driver.MockBrowserDriver.close",
            side_effect=RuntimeError("close failed"),
        ):
            assert browser.close() is False

        assert browser.last_status is BrowserResultStatus.ERROR
        assert browser.last_error_code == "BROWSER_CLOSE_FAILED"

    def test_close_propagates_driver_false_even_after_resources_stop(self, browser):
        assert browser.launch() is True

        def failed_close(driver):
            driver._is_running = False
            return False

        with patch(
            "jarvis.browser.driver.MockBrowserDriver.close",
            new=failed_close,
        ):
            assert browser.close() is False

        assert browser.last_status is BrowserResultStatus.ERROR
        assert browser.last_error_code == "BROWSER_CLOSE_FAILED"

    def test_action_after_close_reports_disconnected(self, browser):
        assert browser.launch() is True
        browser.close()

        assert browser.click("#button") is False
        assert browser.last_status is BrowserResultStatus.DISCONNECTED
        assert browser.last_error_code == "BROWSER_DISCONNECTED"

    def test_explicit_cdp_endpoint_selects_cdp_without_fallback(self):
        ctrl = BrowserCDPController(
            config=BrowserConfig(cdp_endpoint="http://127.0.0.1:9333"),
            is_mock=False,
        )
        with patch(
            "jarvis.browser.cdp_controller.CDPBrowserDriver.launch",
            return_value=False,
        ):
            assert ctrl.launch() is False

        assert ctrl.driver_type is BrowserDriverType.CDP
        assert ctrl.last_status is BrowserResultStatus.UNAVAILABLE
        assert ctrl.last_error_code == "BROWSER_DRIVER_UNAVAILABLE"

    def test_cdp_availability_requires_playwright_dependency(self):
        ctrl = BrowserCDPController(
            config=BrowserConfig(cdp_endpoint="http://127.0.0.1:9333"),
            is_mock=False,
        )

        def dependency(name):
            return None if name == "playwright" else object()

        with patch(
            "jarvis.browser.cdp_controller.importlib.util.find_spec",
            side_effect=dependency,
        ):
            assert ctrl.is_available() is False

    def test_cdp_availability_requires_a_live_endpoint(self):
        ctrl = BrowserCDPController(
            config=BrowserConfig(cdp_endpoint="http://127.0.0.1:1"),
            is_mock=False,
        )

        with (
            patch(
                "jarvis.browser.cdp_controller.CDPBrowserDriver.launch",
                return_value=False,
            ),
            patch(
                "jarvis.browser.cdp_controller.CDPBrowserDriver.close",
                return_value=True,
            ),
        ):
            assert ctrl.is_available() is False

    def test_cdp_availability_rejects_http_200_without_verified_attach(self):
        ctrl = BrowserCDPController(
            config=BrowserConfig(cdp_endpoint="http://127.0.0.1:9333"),
            is_mock=False,
        )
        response = MagicMock(status_code=200)

        with (
            patch("requests.get", return_value=response) as request_get,
            patch(
                "jarvis.browser.cdp_controller.CDPBrowserDriver.launch",
                return_value=False,
            ),
            patch(
                "jarvis.browser.cdp_controller.CDPBrowserDriver.close",
                return_value=True,
            ),
        ):
            assert ctrl.is_available() is False

        request_get.assert_not_called()

    def test_cdp_availability_requires_verified_attach_and_close(self):
        ctrl = BrowserCDPController(
            config=BrowserConfig(cdp_endpoint="http://127.0.0.1:9333"),
            is_mock=False,
        )

        with (
            patch(
                "jarvis.browser.cdp_controller.CDPBrowserDriver.launch",
                return_value=True,
            ) as launch,
            patch(
                "jarvis.browser.cdp_controller.CDPBrowserDriver.close",
                return_value=True,
            ) as close,
        ):
            assert ctrl.is_available() is True

        launch.assert_called_once()
        close.assert_called_once()

    def test_none_cdp_endpoint_keeps_default_playwright_mode(self):
        ctrl = BrowserCDPController(
            config=BrowserConfig(cdp_endpoint=None),
            is_mock=False,
        )

        assert ctrl.driver_type is BrowserDriverType.PLAYWRIGHT


class TestNavigation:
    def test_page_info_without_page_evidence_cannot_be_success(self):
        page = PageInfo(
            url="",
            title="",
            success=True,
            status=BrowserResultStatus.SUCCESS,
        )

        assert page.success is False
        assert page.status is BrowserResultStatus.ERROR
        assert page.error_code == "BROWSER_ERROR"

    def test_error_title_cannot_be_success(self):
        page = PageInfo(
            url="https://example.test/",
            title="Error",
            success=True,
            status=BrowserResultStatus.SUCCESS,
        )

        assert page.success is False
        assert page.status is BrowserResultStatus.ERROR

    def test_page_info_rejects_mixed_success_outcome(self):
        page = PageInfo(
            url="https://example.test/",
            title="Loaded",
            success=False,
            status=BrowserResultStatus.SUCCESS,
        )

        assert page.success is False
        assert page.status is BrowserResultStatus.ERROR
        assert page.error_code == "BROWSER_ERROR"

    def test_navigate_returns_page_info(self, browser):
        page = browser.navigate("https://www.google.com")
        assert isinstance(page, PageInfo)
        assert page.url != ""
        assert page.success is True
        assert page.status is BrowserResultStatus.SUCCESS
        assert page.driver_type is BrowserDriverType.MOCK

    def test_legacy_user_data_dir_persists_cookies_across_controllers(self, tmp_path):
        config = BrowserConfig(user_data_dir=str(tmp_path / "browser-profile"))
        first = BrowserCDPController(config=config, is_mock=True)
        second = BrowserCDPController(config=config, is_mock=True)
        cookie = {
            "name": "session",
            "value": "persisted",
            "domain": "example.test",
            "path": "/",
        }

        try:
            assert first.launch() is True
            assert first._driver is not None
            first._driver.set_cookies([cookie])
            assert first.navigate("https://example.test/private").success is True
            assert first.close() is True

            assert second.launch() is True
            assert second.navigate("https://example.test/private").success is True
            assert second._driver is not None
            assert second._driver.get_cookies() == [cookie]
        finally:
            if first._driver is not None:
                first.close()
            if second._driver is not None:
                second.close()

    def test_legacy_user_data_dirs_do_not_share_sqlite_fallback(
        self,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "global-app-data"))
        first = BrowserCDPController(
            config=BrowserConfig(user_data_dir=str(tmp_path / "profile-a")),
            is_mock=True,
        )
        second = BrowserCDPController(
            config=BrowserConfig(user_data_dir=str(tmp_path / "profile-b")),
            is_mock=True,
        )
        cookie = {
            "name": "profile-secret",
            "value": "must-not-cross-profile-boundary",
            "domain": "example.test",
            "path": "/",
        }

        try:
            assert first.launch() is True
            assert first._driver is not None
            first._driver.set_cookies([cookie])
            assert first.navigate("https://example.test/private").success is True
            assert first.close() is True

            assert second.launch() is True
            assert second.navigate("https://example.test/private").success is True
            assert second._driver is not None
            assert second._driver.get_cookies() == []
        finally:
            if first._driver is not None:
                first.close()
            if second._driver is not None:
                second.close()

    def test_navigate_without_scheme_uses_search(self, browser):
        # Bare keyword → Google search URL
        page = browser.navigate("python tutorial")
        assert "google" in page.url or "python" in page.url

    def test_get_current_url_returns_string(self, browser):
        url = browser.get_current_url()
        assert isinstance(url, str)

    def test_search_google_returns_page(self, browser):
        page = browser.search_google("JARVIS AI assistant")
        assert page.url != ""
        assert "JARVIS" in page.content_md

    def test_failed_search_does_not_replace_error_with_progress_text(self):
        ctrl = BrowserCDPController(is_mock=False)
        with patch(
            "jarvis.browser.cdp_controller.PlaywrightBrowserDriver.launch",
            return_value=False,
        ):
            page = ctrl.search_google("private search")

        assert page.success is False
        assert page.status is BrowserResultStatus.UNAVAILABLE
        assert "Đang tìm kiếm" not in page.content_md

    def test_navigation_timeout_status_is_preserved(self, browser):
        def time_out(driver, url, wait_until="domcontentloaded"):
            driver._record_failure(
                BrowserResultStatus.TIMEOUT,
                "BROWSER_TIMEOUT",
                "Browser navigation timed out.",
            )
            return False

        with patch(
            "jarvis.browser.driver.MockBrowserDriver.navigate",
            new=time_out,
        ):
            page = browser.navigate("https://example.test/slow")

        assert page.success is False
        assert page.status is BrowserResultStatus.TIMEOUT
        assert page.error_code == "BROWSER_TIMEOUT"

    def test_navigation_without_result_url_fails_verification(self, browser):
        with patch(
            "jarvis.browser.driver.MockBrowserDriver.get_current_url",
            return_value="",
        ):
            page = browser.navigate("https://example.test/")

        assert page.success is False
        assert page.status is BrowserResultStatus.ERROR
        assert page.error_code == "BROWSER_NAVIGATION_UNVERIFIED"
        assert page.title == ""


class TestInteraction:
    def test_click_returns_true_mock(self, browser):
        assert browser.click("button.submit") is True

    def test_type_text_returns_true_mock(self, browser):
        assert browser.type_text("#input", "xin chào JARVIS") is True

    def test_press_key_returns_true_mock(self, browser):
        assert browser.press_key("Enter") is True

    def test_scroll_down_returns_true_mock(self, browser):
        assert browser.scroll("down", 300) is True

    def test_scroll_up_returns_true_mock(self, browser):
        assert browser.scroll("up", 200) is True

    def test_invalid_scroll_direction_fails_closed(self, browser):
        assert browser.scroll("sideways", 200) is False
        assert browser.last_status is BrowserResultStatus.ERROR
        assert browser.last_error_code == "BROWSER_INVALID_SCROLL_DIRECTION"

    @pytest.mark.parametrize("amount", [-1, "500", True])
    def test_invalid_scroll_distance_fails_closed(self, browser, amount):
        assert browser.scroll("down", amount) is False
        assert browser.last_status is BrowserResultStatus.ERROR
        assert browser.last_error_code == "BROWSER_INVALID_SCROLL_DISTANCE"

    def test_wait_for_selector_uses_canonical_status(self, browser):
        assert browser.wait_for_selector("#ready", timeout_ms=25) is True
        assert browser.last_status is BrowserResultStatus.SUCCESS

    def test_disconnected_driver_is_not_silently_relaunched(self, browser):
        assert browser.launch() is True
        with patch(
            "jarvis.browser.driver.MockBrowserDriver.is_running",
            return_value=False,
        ):
            assert browser.click("#button") is False

        assert browser.last_status is BrowserResultStatus.DISCONNECTED
        assert browser.last_error_code == "BROWSER_DISCONNECTED"


class TestScreenshot:
    def test_screenshot_creates_file(self, browser, tmp_path):
        browser.config.screenshot_dir = str(tmp_path)
        path = browser.screenshot("test_shot.png")
        assert path != ""
        assert Path(path).exists()

    def test_screenshot_is_valid_png(self, browser, tmp_path):
        browser.config.screenshot_dir = str(tmp_path)
        path = browser.screenshot("valid.png")
        content = Path(path).read_bytes()
        assert content[:4] == b"\x89PNG"

    def test_empty_capture_does_not_create_screenshot(self, browser, tmp_path):
        browser.config.screenshot_dir = str(tmp_path)
        with patch(
            "jarvis.browser.driver.MockBrowserDriver.capture_page_screenshot",
            return_value=b"",
        ):
            path = browser.screenshot("empty.png")

        assert path == ""
        assert not (tmp_path / "empty.png").exists()
        assert browser.last_status is BrowserResultStatus.ERROR


class TestExtract:
    def test_extract_returns_string(self, browser):
        content = browser.extract_content_as_markdown()
        assert isinstance(content, str)
        assert len(content) > 0

    def test_empty_sanitized_content_fails_closed(self, browser):
        sanitized = MagicMock(clean_text="")
        with patch(
            "jarvis.browser.cdp_controller.PromptGuard.sanitize",
            return_value=sanitized,
        ):
            content = browser.extract_content_as_markdown()

        assert content == ""
        assert browser.last_status is BrowserResultStatus.ERROR
        assert browser.last_error_code == "BROWSER_EMPTY_DOCUMENT"

    def test_get_links_returns_list(self, browser):
        links = browser.get_page_links()
        assert isinstance(links, list)

    def test_get_links_are_strings(self, browser):
        links = browser.get_page_links()
        for link in links:
            assert isinstance(link, str)

    def test_get_links_uses_canonical_page_evaluation(self, browser):
        evaluated = [
            "https://example.test/one",
            "javascript:alert(1)",
            "http://example.test/two",
        ]
        with patch(
            "jarvis.browser.driver.MockBrowserDriver.evaluate_script",
            return_value=evaluated,
        ):
            links = browser.get_page_links(limit=1)

        assert links == ["https://example.test/one"]

    def test_get_links_does_not_replace_driver_failure_with_success(self, browser):
        assert browser.launch() is True

        def fail_evaluation(script, *args):
            browser._driver._record_failure(
                BrowserResultStatus.DISCONNECTED,
                "BROWSER_DISCONNECTED",
                "The browser session is disconnected.",
            )
            return None

        with patch.object(browser._driver, "evaluate_script", side_effect=fail_evaluation):
            links = browser.get_page_links()

        assert links == []
        assert browser.last_status is BrowserResultStatus.DISCONNECTED
        assert browser.last_error_code == "BROWSER_DISCONNECTED"


class TestTabManagement:
    def test_new_tab_returns_true_mock(self, browser):
        assert browser.new_tab() is True

    def test_close_tab_returns_true_mock(self, browser):
        assert browser.close_tab() is True


class TestBrowserSkillContract:
    def test_close_without_active_session_is_disconnected(self, monkeypatch):
        monkeypatch.setattr(browser_skill, "_BROWSER", None)

        result = browser_skill.execute(action="close")

        assert result["success"] is False
        assert result["status"] == "DISCONNECTED"
        assert result["error_code"] == "BROWSER_NO_ACTIVE_SESSION"

    @pytest.mark.parametrize(
        ("direction", "expected_label"),
        [
            ("top", "lên đầu trang"),
            ("bottom", "xuống cuối trang"),
        ],
    )
    def test_scroll_extreme_directions_have_truthful_labels(
        self,
        monkeypatch,
        direction,
        expected_label,
    ):
        ctrl = BrowserCDPController(is_mock=True)
        assert ctrl.launch() is True
        monkeypatch.setattr(browser_skill, "_BROWSER", ctrl)

        result = browser_skill.execute(
            action="scroll",
            direction=direction,
            amount=500,
        )

        assert result["success"] is True
        assert expected_label in result["output"]

    def test_close_propagates_controller_failure(self, monkeypatch):
        failed_browser = MagicMock()
        failed_browser.driver_type = BrowserDriverType.MOCK
        failed_browser.close.return_value = False
        failed_browser.last_status = BrowserResultStatus.ERROR
        failed_browser.last_error_code = "BROWSER_CLOSE_FAILED"
        monkeypatch.setattr(browser_skill, "_BROWSER", failed_browser)

        result = browser_skill.execute(action="close")

        assert result["success"] is False
        assert result["status"] == "ERROR"
        assert result["error_code"] == "BROWSER_CLOSE_FAILED"

    def test_false_action_cannot_keep_success_status(self, monkeypatch):
        failed_browser = MagicMock()
        failed_browser.driver_type = BrowserDriverType.MOCK
        failed_browser.last_status = BrowserResultStatus.SUCCESS
        failed_browser.last_error_code = None
        failed_browser.click.return_value = False
        monkeypatch.setattr(browser_skill, "_BROWSER", failed_browser)

        result = browser_skill.execute(action="click", selector="#missing")

        assert result["success"] is False
        assert result["status"] == "ERROR"
        assert result["error_code"] == "BROWSER_ACTION_FAILED"

    def test_type_returns_top_level_status_without_echoing_text(self, monkeypatch):
        ctrl = BrowserCDPController(is_mock=True)
        assert ctrl.launch() is True
        monkeypatch.setattr(browser_skill, "_BROWSER", ctrl)
        secret = "do-not-echo-this-secret"

        result = browser_skill.execute(
            action="type",
            selector="#input",
            text=secret,
        )

        assert result["success"] is True
        assert result["status"] == "SUCCESS"
        assert result["error_code"] is None
        assert result["driver_type"] == "mock"
        assert secret not in repr(result)

    def test_selector_values_are_not_echoed_in_skill_response(self, monkeypatch):
        ctrl = BrowserCDPController(is_mock=True)
        assert ctrl.launch() is True
        monkeypatch.setattr(browser_skill, "_BROWSER", ctrl)
        secret = "selector-secret-do-not-echo"

        result = browser_skill.execute(
            action="click",
            selector=f'[data-token="{secret}"]',
        )

        assert result["success"] is True
        assert secret not in repr(result)

    def test_failed_click_has_failure_flavored_output(self, monkeypatch):
        ctrl = BrowserCDPController(is_mock=True)
        assert ctrl.launch() is True
        monkeypatch.setattr(browser_skill, "_BROWSER", ctrl)

        with patch(
            "jarvis.browser.driver.MockBrowserDriver.click",
            return_value=False,
        ):
            result = browser_skill.execute(action="click", selector="#missing")

        assert result["success"] is False
        assert result["status"] == "ERROR"
        assert result["error_code"] == "BROWSER_ERROR"
        assert result["output"].startswith("❌")

    def test_open_does_not_relabel_navigation_timeout_as_success(self, monkeypatch):
        ctrl = BrowserCDPController(is_mock=True)
        assert ctrl.launch() is True
        monkeypatch.setattr(browser_skill, "_BROWSER", ctrl)

        def time_out(driver, url, wait_until="domcontentloaded"):
            driver._record_failure(
                BrowserResultStatus.TIMEOUT,
                "BROWSER_TIMEOUT",
                "Browser navigation timed out.",
            )
            return False

        with patch(
            "jarvis.browser.driver.MockBrowserDriver.navigate",
            new=time_out,
        ):
            result = browser_skill.execute(action="open", url="https://example.test/slow")

        assert result["success"] is False
        assert result["status"] == "TIMEOUT"
        assert result["error_code"] == "BROWSER_TIMEOUT"
        assert result["output"].startswith("❌")

    def test_failed_launch_is_not_cached(self, monkeypatch):
        failed = MagicMock()
        failed.launch.return_value = False
        ready = BrowserCDPController(is_mock=True)
        assert ready.launch() is True
        monkeypatch.setattr(browser_skill, "_BROWSER", None)

        with patch(
            "jarvis.browser.cdp_controller.BrowserCDPController",
            side_effect=[failed, ready],
        ):
            assert browser_skill._get_browser() is None
            assert browser_skill._BROWSER is None
            assert browser_skill._get_browser() is ready

        failed.close.assert_called_once_with()

    def test_launch_failure_preserves_not_configured_status(self, monkeypatch):
        failed = MagicMock()
        failed.launch.return_value = False
        failed.last_status = BrowserResultStatus.NOT_CONFIGURED
        failed.last_error_code = "BROWSER_PLAYWRIGHT_NOT_CONFIGURED"
        failed.driver_type = BrowserDriverType.PLAYWRIGHT
        monkeypatch.setattr(browser_skill, "_BROWSER", None)

        with patch(
            "jarvis.browser.cdp_controller.BrowserCDPController",
            return_value=failed,
        ):
            result = browser_skill.execute(action="click", selector="#button")

        assert browser_skill._BROWSER is None
        assert result["success"] is False
        assert result["status"] == "NOT_CONFIGURED"
        assert result["error_code"] == "BROWSER_PLAYWRIGHT_NOT_CONFIGURED"
        assert result["driver_type"] == "playwright"


class TestRealFailClosed:
    """D-04: Real (non-mock) BrowserCDPController without a running session must fail closed."""

    def test_playwright_launch_failure_returns_unavailable_page_info(self):
        ctrl = BrowserCDPController(config=BrowserConfig(headless=True), is_mock=False)
        with patch(
            "jarvis.browser.cdp_controller.PlaywrightBrowserDriver.launch",
            return_value=False,
        ), patch(
            "jarvis.browser.cdp_controller.PlaywrightBrowserDriver.close"
        ) as close_driver:
            page = ctrl.navigate("https://example.test/")

        close_driver.assert_called_once_with()
        assert page.success is False
        assert page.status is BrowserResultStatus.UNAVAILABLE
        assert page.error_code == "BROWSER_DRIVER_UNAVAILABLE"
        assert page.error_message == "The browser driver is unavailable."
        assert page.driver_type is BrowserDriverType.PLAYWRIGHT

    def test_unlaunched_real_controller_clicks_fail_closed(self, unavailable_browser):
        assert unavailable_browser.click("#btn") is False
        assert unavailable_browser.last_status is BrowserResultStatus.UNAVAILABLE

    def test_unlaunched_real_controller_type_fails_closed(self, unavailable_browser):
        assert unavailable_browser.type_text("#input", "hello") is False
        assert unavailable_browser.last_status is BrowserResultStatus.UNAVAILABLE

    def test_unlaunched_real_controller_screenshot_fails_closed(self, unavailable_browser):
        assert unavailable_browser.screenshot("test.png") == ""
        assert unavailable_browser.last_status is BrowserResultStatus.UNAVAILABLE

    def test_unlaunched_real_controller_navigate_fails_closed(self):
        ctrl = BrowserCDPController(is_mock=False)
        with patch.object(ctrl, "_ensure_launched", return_value=False):
            page = ctrl.navigate("http://127.0.0.1:65432/nonexistent")
            assert page.title == "Error"
            assert "không khởi động được" in page.content_md

